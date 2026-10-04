import asyncio
import hmac
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field

load_dotenv()

BASE = Path(__file__).parent
STATIC = BASE / "static"

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

# In-memory database storage (No SQLite / DB needed)
rooms_db: dict[str, dict] = {
    "demo": {
        "token": "demo",
        "hotel_id": "demo-hotel",
        "hotel_name": "Grand Palace Demo",
        "floor": 3,
        "room_number": "304",
        "active": True
    }
}
requests_db: list[dict] = []
next_request_id: int = 1
STATIC_CACHE: dict[str, str] = {}


def read_static(filename: str) -> str:
    if filename in STATIC_CACHE:
        return STATIC_CACHE[filename]
    paths = [
        STATIC / filename,
        Path.cwd() / "backend" / "app" / "static" / filename,
        Path.cwd() / "app" / "static" / filename,
        Path.cwd() / "static" / filename,
    ]
    for p in paths:
        if p.is_file():
            content = p.read_text(encoding="utf-8")
            STATIC_CACHE[filename] = content
            return content
    raise HTTPException(404, f"Static template '{filename}' not found.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if SECRET_KEY == "change-me" or STAFF_API_KEY == "staff-secret" or ADMIN_API_KEY == "admin-secret":
        print("WARNING: default secrets in use. Set SECRET_KEY, STAFF_API_KEY and ADMIN_API_KEY in .env")
    task = asyncio.create_task(retry_loop()) if MAIN_BACKEND_URL else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Hotel room service backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def vercel_path_rewrite(request: Request, call_next):
    raw_path = request.scope.get("path", "")
    if raw_path in ("/index.py", "/index", "/api/index.py"):
        matched = (
            request.headers.get("x-matched-path")
            or request.headers.get("x-forwarded-uri")
            or request.headers.get("x-original-uri")
        )
        if matched:
            clean_path = matched.split("?")[0]
            if clean_path not in ("/index.py", "/index", "/api/index.py"):
                request.scope["path"] = clean_path
            else:
                request.scope["path"] = "/"
        else:
            request.scope["path"] = "/"
    return await call_next(request)


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


def room_from_session(session: Optional[str]) -> dict:
    if not session:
        raise HTTPException(401, "Please confirm your room number first.")
    try:
        data = signer.loads(session, max_age=SESSION_TTL)
    except SignatureExpired:
        raise HTTPException(401, "Your session expired. Please scan the QR code again.")
    except BadSignature:
        raise HTTPException(401, "Invalid session.")

    token = data.get("t")
    room = rooms_db.get(token)
    if not room or not room.get("active", True):
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


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "Hotel QR backend",
        "routes": ["/health", "/staff", "/r/{token}", "/api/room/{token}"]
    }



@app.get("/health")
def health():
    return {"ok": True}


@app.api_route("/in", methods=["GET", "POST"])
def in_endpoint():
    return {
        "ok": True,
        "message": "Hotel QR Backend is active. (Webhooks are forwarded to demo_main_backend)."
    }


@app.get("/r/{token}")
def guest_page(token: str):
    html = read_static("guest.html")
    return HTMLResponse(content=html)


@app.get("/staff")
def staff_page():
    html = read_static("staff.html")
    return HTMLResponse(content=html)


@app.get("/api/room/{token}")
def room_info(token: str):
    room = rooms_db.get(token)
    if not room or not room.get("active", True):
        raise HTTPException(404, "This QR code is not valid.")
    return {"hotel_name": room["hotel_name"]}


@app.post("/api/verify")
def verify(body: VerifyIn):
    room = rooms_db.get(body.token)
    if not room or not room.get("active", True):
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
    global next_request_id
    room = room_from_session(x_session)
    message = body.message.strip()
    if body.type == "room_service" and len(message) < 2:
        raise HTTPException(422, "Please tell us what you need.")

    now = time.time()
    recent = sum(
        1 for r in requests_db
        if r["hotel_id"] == room["hotel_id"]
        and r["room_number"] == room["room_number"]
        and r["created_at"] > now - 3600
    )
    if recent >= MAX_REQUESTS_PER_HOUR:
        raise HTTPException(429, "Too many requests from this room. Please call reception.")

    forward_status = "pending" if MAIN_BACKEND_URL else "disabled"
    request_id = next_request_id
    next_request_id += 1

    req_obj = {
        "id": request_id,
        "hotel_id": room["hotel_id"],
        "room_number": room["room_number"],
        "type": body.type,
        "message": message,
        "preferred_time": body.preferred_time.strip(),
        "status": "new",
        "created_at": now,
        "updated_at": now,
        "forward_status": forward_status,
        "forward_attempts": 0,
    }
    requests_db.append(req_obj)

    if MAIN_BACKEND_URL:
        background.add_task(forward_request, request_id)
    return {"id": request_id, "status": "new"}


@app.get("/api/requests/mine")
def my_requests(x_session: Optional[str] = Header(None)):
    room = room_from_session(x_session)
    now = time.time()
    rows = [
        {
            "id": r["id"],
            "type": r["type"],
            "message": r["message"],
            "preferred_time": r["preferred_time"],
            "status": r["status"],
            "created_at": r["created_at"],
        }
        for r in reversed(requests_db)
        if r["hotel_id"] == room["hotel_id"]
        and r["room_number"] == room["room_number"]
        and r["created_at"] > now - 86400
    ]
    return rows


@app.get("/api/staff/requests", dependencies=[Depends(require_staff)])
def staff_list(status: Optional[Status] = None, hotel_id: Optional[str] = None, limit: int = 100):
    results = []
    for r in reversed(requests_db):
        if status and r["status"] != status:
            continue
        if hotel_id and r["hotel_id"] != hotel_id:
            continue

        floor = None
        for rm in rooms_db.values():
            if rm["hotel_id"] == r["hotel_id"] and rm["room_number"] == r["room_number"]:
                floor = rm.get("floor")
                break

        results.append({
            "id": r["id"],
            "hotel_id": r["hotel_id"],
            "room_number": r["room_number"],
            "floor": floor,
            "type": r["type"],
            "message": r["message"],
            "preferred_time": r["preferred_time"],
            "status": r["status"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "forward_status": r["forward_status"],
        })
        if len(results) >= min(limit, 500):
            break
    return results


@app.patch("/api/staff/requests/{request_id}", dependencies=[Depends(require_staff)])
def staff_update(request_id: int, body: StatusIn):
    for r in requests_db:
        if r["id"] == request_id:
            r["status"] = body.status
            r["updated_at"] = time.time()
            return {"id": request_id, "status": body.status}
    raise HTTPException(404, "Request not found")


@app.post("/api/admin/rooms/bulk", dependencies=[Depends(require_admin)])
def bulk_rooms(body: BulkRoomsIn):
    count = 0
    for r in body.rooms:
        for rm in list(rooms_db.values()):
            if rm["hotel_id"] == body.hotel_id and rm["room_number"] == r.room_number:
                rm["active"] = False

        rooms_db[r.token] = {
            "token": r.token,
            "hotel_id": body.hotel_id,
            "hotel_name": body.hotel_name,
            "floor": r.floor,
            "room_number": r.room_number,
            "active": True,
        }
        count += 1
    return {"registered": count}


@app.delete("/api/admin/rooms/{hotel_id}/{room_number}", dependencies=[Depends(require_admin)])
def deactivate_room(hotel_id: str, room_number: str):
    deactivated = False
    for rm in rooms_db.values():
        if rm["hotel_id"] == hotel_id and rm["room_number"] == room_number:
            rm["active"] = False
            deactivated = True
    if not deactivated:
        raise HTTPException(404, "Room not found")
    return {"deactivated": room_number}


async def forward_request(request_id: int):
    row = None
    for r in requests_db:
        if r["id"] == request_id:
            row = r
            break
    if not row or row["forward_status"] != "pending":
        return

    hotel_name = row["hotel_id"]
    floor = None
    for rm in rooms_db.values():
        if rm["hotel_id"] == row["hotel_id"] and rm["room_number"] == row["room_number"]:
            hotel_name = rm.get("hotel_name", row["hotel_id"])
            floor = rm.get("floor")
            break

    payload = {
        "id": row["id"],
        "hotel_id": row["hotel_id"],
        "hotel_name": hotel_name,
        "room_number": row["room_number"],
        "floor": floor,
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

    attempts = row["forward_attempts"] + 1
    if outcome == "pending" and attempts >= MAX_FORWARD_ATTEMPTS:
        outcome = "failed"
    row["forward_status"] = outcome
    row["forward_attempts"] = attempts


async def retry_loop():
    while True:
        await asyncio.sleep(60)
        pending_ids = [r["id"] for r in requests_db if r.get("forward_status") == "pending"][:50]
        for request_id in pending_ids:
            await forward_request(request_id)
