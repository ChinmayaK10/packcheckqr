import asyncio
import hmac
import os
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field

load_dotenv()

BASE = Path(__file__).parent
STATIC = BASE / "static"
DB_PATH = os.getenv("DB_PATH", str(BASE.parent / "hotel.db"))
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
STAFF_API_KEY = os.getenv("STAFF_API_KEY", "staff-secret")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-secret")
MAIN_BACKEND_URL = os.getenv("MAIN_BACKEND_URL", "")
MAIN_BACKEND_API_KEY = os.getenv("MAIN_BACKEND_API_KEY", "")
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "1800"))

MAX_VERIFY_ATTEMPTS = 5
VERIFY_WINDOW = 600
MAX_REQUESTS_PER_HOUR = 10
MAX_FORWARD_ATTEMPTS = 10

RequestType = Literal["checkout", "cart", "room_service"]
Status = Literal["new", "in_progress", "done", "cancelled"]

signer = URLSafeTimedSerializer(SECRET_KEY, salt="guest-session")
_verify_attempts: dict[str, list[float]] = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
  token TEXT PRIMARY KEY,
  hotel_id TEXT NOT NULL,
  hotel_name TEXT NOT NULL,
  floor INTEGER NOT NULL,
  room_number TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE (hotel_id, room_number)
);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hotel_id TEXT NOT NULL,
  room_number TEXT NOT NULL,
  type TEXT NOT NULL,
  message TEXT NOT NULL DEFAULT '',
  preferred_time TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'new',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  forward_status TEXT NOT NULL DEFAULT 'pending',
  forward_attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_requests_room
  ON requests (hotel_id, room_number, created_at);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if SECRET_KEY == "change-me" or STAFF_API_KEY == "staff-secret" or ADMIN_API_KEY == "admin-secret":
        print("WARNING: default secrets in use. Set SECRET_KEY, STAFF_API_KEY and ADMIN_API_KEY in .env")
    task = asyncio.create_task(retry_loop()) if MAIN_BACKEND_URL else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Hotel room service backend", lifespan=lifespan)


def norm(value: str) -> str:
    return "".join(value.split()).upper()


def require_staff(x_api_key: Optional[str] = Header(None)):
    ok = x_api_key and (
        hmac.compare_digest(x_api_key, STAFF_API_KEY) or hmac.compare_digest(x_api_key, ADMIN_API_KEY)
    )
    if not ok:
        raise HTTPException(401, "Invalid API key")


def require_admin(x_api_key: Optional[str] = Header(None)):
    if not x_api_key or not hmac.compare_digest(x_api_key, ADMIN_API_KEY):
        raise HTTPException(401, "Invalid admin API key")


def room_from_session(session: Optional[str]) -> sqlite3.Row:
    if not session:
        raise HTTPException(401, "Please confirm your room number first.")
    try:
        data = signer.loads(session, max_age=SESSION_TTL)
    except SignatureExpired:
        raise HTTPException(401, "Your session expired. Please scan the QR code again.")
    except BadSignature:
        raise HTTPException(401, "Invalid session.")
    with db() as conn:
        room = conn.execute(
            "SELECT * FROM rooms WHERE token = ? AND active = 1", (data["t"],)
        ).fetchone()
    if not room:
        raise HTTPException(401, "This QR code is no longer active.")
    return room


class VerifyIn(BaseModel):
    token: str
    room_number: str = Field(min_length=1, max_length=10)


class RequestIn(BaseModel):
    type: RequestType
    message: str = Field(default="", max_length=1000)
    preferred_time: str = Field(default="", max_length=40)


class StatusIn(BaseModel):
    status: Status


class RoomIn(BaseModel):
    floor: int
    room_number: str
    token: str


class BulkRoomsIn(BaseModel):
    hotel_id: str
    hotel_name: str
    rooms: list[RoomIn]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/r/{token}")
def guest_page(token: str):
    return FileResponse(STATIC / "guest.html")


@app.get("/staff")
def staff_page():
    return FileResponse(STATIC / "staff.html")


@app.get("/api/room/{token}")
def room_info(token: str):
    with db() as conn:
        room = conn.execute(
            "SELECT hotel_name FROM rooms WHERE token = ? AND active = 1", (token,)
        ).fetchone()
    if not room:
        raise HTTPException(404, "This QR code is not valid.")
    return {"hotel_name": room["hotel_name"]}


@app.post("/api/verify")
def verify(body: VerifyIn):
    with db() as conn:
        room = conn.execute(
            "SELECT * FROM rooms WHERE token = ? AND active = 1", (body.token,)
        ).fetchone()
    if not room:
        raise HTTPException(404, "This QR code is not valid.")

    now = time.time()
    hits = [t for t in _verify_attempts.get(body.token, []) if now - t < VERIFY_WINDOW]
    if len(hits) >= MAX_VERIFY_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Please try again in a few minutes or call reception.")

    if not hmac.compare_digest(norm(body.room_number), norm(room["room_number"])):
        hits.append(now)
        _verify_attempts[body.token] = hits
        raise HTTPException(400, "That room number does not match this room.")

    _verify_attempts.pop(body.token, None)
    return {"session": signer.dumps({"t": body.token}), "expires_in": SESSION_TTL}


@app.post("/api/requests", status_code=201)
def create_request(
    body: RequestIn,
    background: BackgroundTasks,
    x_session: Optional[str] = Header(None),
):
    room = room_from_session(x_session)
    message = body.message.strip()
    if body.type == "room_service" and len(message) < 2:
        raise HTTPException(422, "Please tell us what you need.")

    now = time.time()
    with db() as conn:
        recent = conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE hotel_id = ? AND room_number = ? AND created_at > ?",
            (room["hotel_id"], room["room_number"], now - 3600),
        ).fetchone()["n"]
        if recent >= MAX_REQUESTS_PER_HOUR:
            raise HTTPException(429, "Too many requests from this room. Please call reception.")
        forward_status = "pending" if MAIN_BACKEND_URL else "disabled"
        cur = conn.execute(
            "INSERT INTO requests (hotel_id, room_number, type, message, preferred_time,"
            " created_at, updated_at, forward_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (room["hotel_id"], room["room_number"], body.type, message,
             body.preferred_time.strip(), now, now, forward_status),
        )
        request_id = cur.lastrowid

    if MAIN_BACKEND_URL:
        background.add_task(forward_request, request_id)
    return {"id": request_id, "status": "new"}


@app.get("/api/requests/mine")
def my_requests(x_session: Optional[str] = Header(None)):
    room = room_from_session(x_session)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, type, message, preferred_time, status, created_at FROM requests"
            " WHERE hotel_id = ? AND room_number = ? AND created_at > ? ORDER BY id DESC",
            (room["hotel_id"], room["room_number"], time.time() - 86400),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/staff/requests", dependencies=[Depends(require_staff)])
def staff_list(status: Optional[Status] = None, hotel_id: Optional[str] = None, limit: int = 100):
    query = (
        "SELECT r.id, r.hotel_id, r.room_number, rm.floor, r.type, r.message, r.preferred_time,"
        " r.status, r.created_at, r.updated_at, r.forward_status"
        " FROM requests r LEFT JOIN rooms rm ON rm.hotel_id = r.hotel_id AND rm.room_number = r.room_number"
        " WHERE 1 = 1"
    )
    params: list = []
    if status:
        query += " AND r.status = ?"
        params.append(status)
    if hotel_id:
        query += " AND r.hotel_id = ?"
        params.append(hotel_id)
    query += " ORDER BY r.id DESC LIMIT ?"
    params.append(min(limit, 500))
    with db() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


@app.patch("/api/staff/requests/{request_id}", dependencies=[Depends(require_staff)])
def staff_update(request_id: int, body: StatusIn):
    with db() as conn:
        cur = conn.execute(
            "UPDATE requests SET status = ?, updated_at = ? WHERE id = ?",
            (body.status, time.time(), request_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Request not found")
    return {"id": request_id, "status": body.status}


@app.post("/api/admin/rooms/bulk", dependencies=[Depends(require_admin)])
def bulk_rooms(body: BulkRoomsIn):
    with db() as conn:
        for r in body.rooms:
            conn.execute(
                "INSERT INTO rooms (token, hotel_id, hotel_name, floor, room_number) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (hotel_id, room_number) DO UPDATE SET"
                " token = excluded.token, hotel_name = excluded.hotel_name,"
                " floor = excluded.floor, active = 1",
                (r.token, body.hotel_id, body.hotel_name, r.floor, r.room_number),
            )
    return {"registered": len(body.rooms)}


@app.delete("/api/admin/rooms/{hotel_id}/{room_number}", dependencies=[Depends(require_admin)])
def deactivate_room(hotel_id: str, room_number: str):
    with db() as conn:
        cur = conn.execute(
            "UPDATE rooms SET active = 0 WHERE hotel_id = ? AND room_number = ?",
            (hotel_id, room_number),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Room not found")
    return {"deactivated": room_number}


async def forward_request(request_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT r.*, rm.floor, rm.hotel_name FROM requests r"
            " LEFT JOIN rooms rm ON rm.hotel_id = r.hotel_id AND rm.room_number = r.room_number"
            " WHERE r.id = ?",
            (request_id,),
        ).fetchone()
    if not row or row["forward_status"] != "pending":
        return
    payload = {
        "id": row["id"],
        "hotel_id": row["hotel_id"],
        "hotel_name": row["hotel_name"],
        "room_number": row["room_number"],
        "floor": row["floor"],
        "type": row["type"],
        "message": row["message"],
        "preferred_time": row["preferred_time"],
        "created_at": row["created_at"],
    }
    headers = {"Authorization": f"Bearer {MAIN_BACKEND_API_KEY}"} if MAIN_BACKEND_API_KEY else {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(MAIN_BACKEND_URL, json=payload, headers=headers)
            resp.raise_for_status()
        outcome = "sent"
    except Exception as exc:
        print(f"Forwarding request {request_id} failed: {exc}")
        outcome = "pending"
    with db() as conn:
        attempts = row["forward_attempts"] + 1
        if outcome == "pending" and attempts >= MAX_FORWARD_ATTEMPTS:
            outcome = "failed"
        conn.execute(
            "UPDATE requests SET forward_status = ?, forward_attempts = ? WHERE id = ?",
            (outcome, attempts, request_id),
        )


async def retry_loop():
    while True:
        await asyncio.sleep(60)
        with db() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM requests WHERE forward_status = 'pending' ORDER BY id LIMIT 50"
            ).fetchall()]
        for request_id in ids:
            await forward_request(request_id)
