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

rooms_db: dict[str, dict] = {}
requests_db: list[dict] = []
next_request_id: int = 1
EMBEDDED_HTML: dict[str, str] = {
    "guest.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Room service</title>
<style>
:root{--bg:#f5f7f6;--surface:#fff;--ink:#17211f;--muted:#65736f;--line:#d6dedb;--pine:#123a34;--gold:#a47e2f;--err:#9b2c2c;--ok:#1f6f52}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:linear-gradient(180deg,#eef3f1 0,#f8faf9 48%,#f3f5f4 100%);color:var(--ink);font:400 16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{width:min(100%,520px);margin:0 auto;padding:24px 18px 40px}
.top{padding:14px 0 22px}.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--gold);font-weight:800}
h1{font-size:34px;line-height:1.05;margin:4px 0 8px;color:var(--pine)}h2{font-size:24px;line-height:1.15;margin:0 0 8px;color:var(--pine)}p{margin:0 0 14px;color:var(--muted)}
.panel{background:rgba(255,255,255,.92);border:1px solid var(--line);border-radius:8px;padding:20px;box-shadow:0 18px 45px rgba(18,58,52,.08)}
label{display:block;font-weight:700;margin:0 0 8px}input,textarea{width:100%;font:inherit;color:var(--ink);background:#fbfcfc;border:1px solid var(--line);border-radius:6px;padding:12px}
input:focus,textarea:focus,button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}.room-input{font-size:40px;text-align:center;font-weight:800;letter-spacing:.12em;color:var(--pine);padding:12px 8px}
textarea{min-height:128px;resize:vertical}button{font:700 15px system-ui,-apple-system,Segoe UI,sans-serif;border-radius:6px;cursor:pointer;min-height:48px;padding:0 18px;border:1px solid transparent}
.primary{background:var(--pine);color:#fff;width:100%;margin-top:14px}.primary:disabled{opacity:.6;cursor:wait}.ghost{background:transparent;color:var(--pine);border-color:transparent;padding:0;min-height:34px}
.mic{background:#fff;color:var(--pine);border-color:var(--pine);width:100%;margin-top:10px}.mic[aria-pressed=true]{background:var(--pine);color:#fff}
.menu{display:grid;gap:10px}.service{width:100%;text-align:left;background:#fff;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:16px;display:grid;gap:3px;min-height:auto}
.service strong{font-size:17px}.service span{color:var(--muted);font-weight:500}.service:hover{border-color:var(--gold)}.err{color:var(--err);min-height:24px;margin:8px 0 0}
.done{border-left:4px solid var(--ok);padding-left:14px}.done strong{display:block;font-size:19px;color:var(--pine)}.history{margin-top:18px}
.req{border-top:1px solid var(--line);padding:12px 0;display:flex;justify-content:space-between;gap:14px}.req small{color:var(--muted);display:block}.status{font-weight:800;color:var(--pine);white-space:nowrap}
[hidden]{display:none!important}.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media(max-width:420px){main{padding:18px 12px 32px}.panel{padding:16px}h1{font-size:30px}.room-input{font-size:34px}}
</style>
</head>
<body>
<main>
  <header class="top"><div class="eyebrow">Guest requests</div><h1 id="hotel">Welcome</h1><p>Fast service from your room to the front desk.</p></header>
  <section id="invalid" class="panel" hidden><h2>QR not active</h2><p>This QR code is not active. Please call reception and we will help you.</p></section>
  <section id="s-room" class="panel" hidden><h2>Confirm your room</h2><p>Enter the room number printed on your door or key card.</p><label for="room" class="sr">Room number</label><input id="room" class="room-input" autocomplete="off" autocapitalize="characters" maxlength="10" aria-describedby="room-err"><p id="room-err" class="err" role="alert"></p><button id="room-go" class="primary">Continue</button></section>
  <section id="s-menu" class="panel" hidden><h2>How can we help?</h2><div class="menu"><button class="service" data-svc="checkout"><strong>Check out</strong><span>Share your departure time</span></button><button class="service" data-svc="cart"><strong>Luggage cart</strong><span>Ask for a cart at your door</span></button><button class="service" data-svc="room_service"><strong>Room service and other requests</strong><span>Food, towels, amenities, or anything else</span></button></div></section>
  <section id="s-form" class="panel" hidden><button id="back" class="ghost">Back</button><h2 id="f-title"></h2><div id="f-time-wrap" style="margin-bottom:14px"><label for="f-time" id="f-time-label"></label><input id="f-time" type="time"></div><label for="f-msg" id="f-msg-label">Details</label><textarea id="f-msg"></textarea><button id="mic" class="mic" aria-pressed="false" hidden>Speak request</button><p id="f-err" class="err" role="alert"></p><button id="send" class="primary">Send request</button></section>
  <section id="s-done" class="panel" hidden><div class="done" role="status"><strong id="done-title"></strong><span id="done-note"></span></div><button id="again" class="primary">Make another request</button></section>
  <section id="s-mine" class="panel history" hidden><h2>Your requests</h2><div id="mine"></div></section>
</main>
<script>
const token=location.pathname.split("/").filter(Boolean).pop();let session=null;const $=id=>document.getElementById(id);
const show=(...ids)=>["s-room","s-menu","s-form","s-done","s-mine","invalid"].forEach(i=>$(i).hidden=!ids.includes(i));
const SERVICES={checkout:{title:"Check out",time:"Departure time",ph:"Anything we should know, such as help with luggage",required:false},cart:{title:"Luggage cart",time:"Cart needed at",ph:"Optional note for our team",required:false},room_service:{title:"Room service and other requests",time:null,ph:"What would you like? You can type or speak.",required:true}};
const LABELS={new:"Received",in_progress:"In progress",done:"Completed",cancelled:"Cancelled"};const TYPES={checkout:"Check out",cart:"Luggage cart",room_service:"Room service"};let current=null;
async function api(path,opts={}){const headers={"Content-Type":"application/json"};if(session)headers["X-Session"]=session;const res=await fetch(path,{...opts,headers});const data=await res.json().catch(()=>({}));if(res.status===401&&session){session=null;show("s-room");$("room-err").textContent=data.detail||"Please confirm your room number again."}if(!res.ok)throw new Error(data.detail||"Something went wrong. Please try again.");return data}
async function init(){try{const info=await api("/api/room/"+encodeURIComponent(token));$("hotel").textContent=info.hotel_name;document.title=info.hotel_name+" room service";show("s-room");$("room").focus()}catch{show("invalid")}}
$("room-go").onclick=async()=>{const value=$("room").value.trim();$("room-err").textContent="";if(!value){$("room-err").textContent="Enter your room number.";return}$("room-go").disabled=true;try{const res=await api("/api/verify",{method:"POST",body:JSON.stringify({token,room_number:value})});session=res.session;show("s-menu","s-mine");loadMine()}catch(e){$("room-err").textContent=e.message}$("room-go").disabled=false};
$("room").addEventListener("keydown",e=>{if(e.key==="Enter")$("room-go").click()});
document.querySelectorAll("[data-svc]").forEach(b=>b.onclick=()=>{current=b.dataset.svc;const s=SERVICES[current];$("f-title").textContent=s.title;$("f-time-wrap").hidden=!s.time;$("f-time-label").textContent=s.time||"";$("f-time").value="";$("f-msg").value="";$("f-msg").placeholder=s.ph;$("f-msg-label").textContent=s.required?"What do you need?":"Notes";$("f-err").textContent="";show("s-form")});
$("back").onclick=()=>{stopMic();show("s-menu","s-mine")};$("again").onclick=()=>show("s-menu","s-mine");
$("send").onclick=async()=>{stopMic();const s=SERVICES[current];const message=$("f-msg").value.trim();if(s.required&&message.length<2){$("f-err").textContent="Please tell us what you need.";return}$("send").disabled=true;try{const res=await api("/api/requests",{method:"POST",body:JSON.stringify({type:current,message,preferred_time:s.time?$("f-time").value:""})});$("done-title").textContent="Request received";$("done-note").textContent="Reference "+res.id+". Our team has been notified.";show("s-done","s-mine");loadMine()}catch(e){$("f-err").textContent=e.message}$("send").disabled=false};
async function loadMine(){if(!session)return;try{const list=await api("/api/requests/mine");$("mine").innerHTML="";list.forEach(r=>{const row=document.createElement("div");row.className="req";const left=document.createElement("div");const name=document.createElement("strong");name.textContent=TYPES[r.type]||r.type;left.append(name);if(r.message){const m=document.createElement("small");m.textContent=r.message;left.append(m)}const st=document.createElement("div");st.className="status";st.textContent=LABELS[r.status]||r.status;row.append(left,st);$("mine").append(row)});if(!list.length)$("mine").textContent="Nothing yet."}catch{}}
setInterval(loadMine,10000);
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;let rec=null,listening=false;function stopMic(){if(rec&&listening)rec.stop()}
if(SR){$("mic").hidden=false;$("mic").onclick=()=>{if(listening){rec.stop();return}rec=new SR();rec.lang=navigator.language||"en-US";rec.interimResults=true;const base=$("f-msg").value.trim();rec.onresult=e=>{let text="";for(const r of e.results)text+=r[0].transcript;$("f-msg").value=(base?base+" ":"")+text};rec.onend=()=>{listening=false;$("mic").textContent="Speak request";$("mic").setAttribute("aria-pressed","false")};rec.onerror=()=>{$("f-err").textContent="Microphone unavailable. You can type your request instead."};rec.start();listening=true;$("mic").textContent="Listening. Tap to stop";$("mic").setAttribute("aria-pressed","true")}}
init();
</script>
</body>
</html>""",
    "staff.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reception queue</title>
<style>
:root{--bg:#f4f6f5;--surface:#fff;--ink:#17211f;--muted:#66736f;--line:#d8dfdc;--pine:#123a34;--gold:#a47e2f;--blue:#275d8c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:400 15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
header{background:var(--pine);color:#f7fbf9;padding:18px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
h1{font-size:22px;margin:0;font-weight:800}.connect{display:flex;gap:8px;align-items:center}
main{max-width:1120px;margin:0 auto;padding:22px 24px 44px}
input,button{font:inherit;border-radius:6px;border:1px solid var(--line);padding:9px 12px;background:#fff;color:var(--ink)}
button{cursor:pointer;font-weight:700}button:focus-visible,input:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}.tab[aria-pressed=true]{background:var(--pine);color:#fff;border-color:var(--pine)}
.status-line{min-height:24px;color:#8a5a00;margin-bottom:10px}.grid{display:grid;gap:10px}
.card{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:8px;padding:14px 16px;display:grid;grid-template-columns:96px 1fr auto;gap:14px;align-items:start}
.card.new{border-left-color:var(--gold)}.card.in_progress{border-left-color:var(--blue)}.card.done{opacity:.78}
.room{font-size:30px;font-weight:800;color:var(--pine);line-height:1}.room small{display:block;font-size:12px;font-weight:600;color:var(--muted);margin-top:5px}
.type{font-weight:800}.msg{color:var(--ink);margin-top:3px;white-space:pre-wrap;word-break:break-word}.meta{color:var(--muted);font-size:13px;margin-top:5px}
.actions{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}.actions button{padding:7px 10px}.actions button[aria-pressed=true]{background:var(--pine);color:#fff;border-color:var(--pine)}
.empty{border:1px dashed var(--line);border-radius:8px;background:#fff;padding:30px;text-align:center;color:var(--muted)}
@media(max-width:720px){header,main{padding-left:16px;padding-right:16px}.connect{width:100%}.connect input{min-width:0;flex:1}.card{grid-template-columns:1fr}.actions{justify-content:flex-start}}
</style>
</head>
<body>
<header><h1>Reception queue</h1><div class="connect"><input id="key" type="password" placeholder="Staff key" aria-label="Staff key"><button id="save">Connect</button></div></header>
<main>
  <div class="tabs" role="group" aria-label="Filter"><button class="tab" data-f="open" aria-pressed="true">Open</button><button class="tab" data-f="done" aria-pressed="false">Completed</button><button class="tab" data-f="all" aria-pressed="false">All</button></div>
  <div id="msg" class="status-line" role="status"></div>
  <div id="list" class="grid"></div>
</main>
<script>
const $=id=>document.getElementById(id);const TYPES={checkout:"Check out",cart:"Luggage cart",room_service:"Room service"};const STATUSES=[["new","New"],["in_progress","In progress"],["done","Done"],["cancelled","Cancel"]];
let key=sessionStorage.getItem("staffKey")||"";let filter="open",seen=new Set(),first=true;$("key").value=key;
function beep(){try{const c=new(window.AudioContext||window.webkitAudioContext)();const o=c.createOscillator();o.frequency.value=880;o.connect(c.destination);o.start();o.stop(c.currentTime+.15)}catch{}}
async function call(path,opts={}){const res=await fetch(path,{...opts,headers:{"Content-Type":"application/json","X-API-Key":key}});if(!res.ok)throw new Error(res.status===401?"Wrong staff key.":"Could not reach the server.");return res.json()}
async function load(){if(!key){$("msg").textContent="Enter the staff key to see requests.";$("list").innerHTML="";return}try{let items=await call("/api/staff/requests?limit=200");const fresh=items.filter(r=>r.status==="new"&&!seen.has(r.id));items.forEach(r=>seen.add(r.id));if(fresh.length&&!first)beep();first=false;if(filter==="open")items=items.filter(r=>r.status==="new"||r.status==="in_progress");if(filter==="done")items=items.filter(r=>r.status==="done"||r.status==="cancelled");$("msg").textContent=items.length+" request"+(items.length===1?"":"s");render(items)}catch(e){$("msg").textContent=e.message}}
function render(items){const list=$("list");list.innerHTML="";if(!items.length){list.innerHTML='<div class="empty">No requests here.</div>';return}items.forEach(r=>{const card=document.createElement("article");card.className="card "+r.status;const room=document.createElement("div");room.className="room";room.textContent=r.room_number;const small=document.createElement("small");small.textContent=r.floor!=null?"Floor "+r.floor:r.hotel_id;room.append(small);const body=document.createElement("div");const type=document.createElement("div");type.className="type";type.textContent=TYPES[r.type]||r.type;body.append(type);if(r.message){const m=document.createElement("div");m.className="msg";m.textContent=r.message;body.append(m)}const meta=document.createElement("div");meta.className="meta";const t=new Date(r.created_at*1000).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});meta.textContent="#"+r.id+" at "+t+(r.preferred_time?", preferred "+r.preferred_time:"")+(r.forward_status==="failed"?", not delivered to main system":"");body.append(meta);const actions=document.createElement("div");actions.className="actions";STATUSES.forEach(([value,label])=>{const b=document.createElement("button");b.textContent=label;b.setAttribute("aria-pressed",String(r.status===value));b.onclick=async()=>{await call("/api/staff/requests/"+r.id,{method:"PATCH",body:JSON.stringify({status:value})});load()};actions.append(b)});card.append(room,body,actions);list.append(card)})}
$("save").onclick=()=>{key=$("key").value.trim();sessionStorage.setItem("staffKey",key);first=true;seen.clear();load()};$("key").addEventListener("keydown",e=>{if(e.key==="Enter")$("save").click()});
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{filter=b.dataset.f;document.querySelectorAll(".tab").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));load()});
load();setInterval(load,5000);
</script>
</body>
</html>"""
}

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
    if filename in EMBEDDED_HTML:
        return EMBEDDED_HTML[filename]
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


@app.post("/api/admin/rooms/bulk")
@app.post("/api/admin/rooms/bulk/")
async def bulk_rooms(request: Request, x_api_key: Optional[str] = Header(None)):
    require_admin(x_api_key)
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    hotel_id = str(data.get("hotel_id", ""))
    hotel_name = str(data.get("hotel_name", ""))
    rooms = data.get("rooms", [])

    count = 0
    for r in rooms:
        token = str(r.get("token", ""))
        floor = int(r.get("floor", 1))
        room_number = str(r.get("room_number", ""))

        for rm in list(rooms_db.values()):
            if rm["hotel_id"] == hotel_id and rm["room_number"] == room_number:
                rm["active"] = False

        rooms_db[token] = {
            "token": token,
            "hotel_id": hotel_id,
            "hotel_name": hotel_name,
            "floor": floor,
            "room_number": room_number,
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
