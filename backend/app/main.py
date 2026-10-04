import asyncio
import hmac
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import parse_qsl, unquote, urlencode

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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0f172a;--surface:rgba(30,41,59,0.7);--ink:#f8fafc;--muted:#94a3b8;--line:rgba(255,255,255,0.1);--accent:#3b82f6;--gold:#f59e0b;--err:#ef4444;--ok:#10b981;--glow:rgba(59,130,246,0.5)}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 100%);color:var(--ink);font:400 16px/1.5 'Inter',system-ui,sans-serif}
main{width:min(100%,520px);margin:0 auto;padding:24px 18px 40px}
.top{padding:14px 0 22px;text-align:center}.eyebrow{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);font-weight:700}
h1{font-size:36px;line-height:1.1;margin:8px 0;background:linear-gradient(to right,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:800}h2{font-size:24px;line-height:1.2;margin:0 0 12px;color:#fff}p{margin:0 0 16px;color:var(--muted)}
.panel{background:var(--surface);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--line);border-radius:16px;padding:24px;box-shadow:0 20px 40px rgba(0,0,0,0.4);transition:transform 0.3s ease;animation:fadeUp 0.5s ease-out}
@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
label{display:block;font-weight:600;margin:0 0 8px;color:var(--ink)}input,textarea{width:100%;font:inherit;color:var(--ink);background:rgba(15,23,42,0.6);border:1px solid var(--line);border-radius:8px;padding:14px;transition:all 0.2s}
input:focus,textarea:focus,button:focus-visible{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--glow)}.room-input{font-size:42px;text-align:center;font-weight:800;letter-spacing:.15em;color:#fff;padding:16px 8px;background:rgba(0,0,0,0.2)}
textarea{min-height:128px;resize:vertical}button{font:600 16px 'Inter',system-ui,sans-serif;border-radius:8px;cursor:pointer;min-height:50px;padding:0 20px;border:none;transition:all 0.2s;display:inline-flex;align-items:center;justify-content:center}
.primary{background:linear-gradient(135deg,#3b82f6,#2563eb);color:#fff;width:100%;margin-top:16px;box-shadow:0 4px 14px var(--glow)}.primary:hover{transform:translateY(-2px);box-shadow:0 6px 20px var(--glow)}.primary:active{transform:translateY(1px)}.primary:disabled{opacity:.6;cursor:wait;transform:none}
.ghost{background:transparent;color:var(--muted);min-height:34px;padding:0;margin-bottom:16px}.ghost:hover{color:#fff}
.mic{background:rgba(255,255,255,0.05);color:#fff;border:1px solid var(--line);width:100%;margin-top:10px}.mic:hover{background:rgba(255,255,255,0.1)}.mic[aria-pressed=true]{background:var(--err);border-color:var(--err);box-shadow:0 0 15px rgba(239,68,68,0.4);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(239,68,68,0.4)}70%{box-shadow:0 0 0 10px rgba(239,68,68,0)}100%{box-shadow:0 0 0 0 rgba(239,68,68,0)}}
.menu{display:grid;gap:12px}.service{width:100%;text-align:left;background:rgba(255,255,255,0.03);color:var(--ink);border:1px solid var(--line);border-radius:12px;padding:18px;display:grid;gap:6px}.service strong{font-size:18px;color:#fff}.service span{color:var(--muted);font-weight:400}.service:hover{background:rgba(255,255,255,0.08);border-color:var(--accent);transform:translateX(4px)}
.err{color:var(--err);min-height:24px;margin:10px 0 0;font-size:14px}
.done{border-left:4px solid var(--ok);padding-left:16px;background:rgba(16,185,129,0.1);border-radius:0 8px 8px 0;padding:16px}.done strong{display:block;font-size:20px;color:var(--ok);margin-bottom:4px}.history{margin-top:24px}
.req{border-top:1px solid var(--line);padding:16px 0;display:flex;justify-content:space-between;gap:14px}.req:first-child{border-top:none}.req small{color:var(--muted);display:block;margin-top:4px;font-size:14px}.status{font-weight:700;font-size:14px;padding:4px 10px;border-radius:20px;background:rgba(255,255,255,0.1);color:#fff;height:fit-content;white-space:nowrap}
[hidden]{display:none!important}.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media(max-width:420px){main{padding:16px 12px}.panel{padding:20px}h1{font-size:32px}.room-input{font-size:36px}}
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0f172a;--surface:rgba(30,41,59,0.7);--ink:#f8fafc;--muted:#94a3b8;--line:rgba(255,255,255,0.1);--accent:#3b82f6;--gold:#f59e0b;--err:#ef4444;--ok:#10b981;--glow:rgba(59,130,246,0.5)}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 100%);color:var(--ink);font:400 15px/1.5 'Inter',system-ui,sans-serif}
header{background:rgba(15,23,42,0.8);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:18px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;position:sticky;top:0;z-index:10}
h1{font-size:24px;margin:0;font-weight:800;background:linear-gradient(to right,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}.connect{display:flex;gap:8px;align-items:center}
main{max-width:1120px;margin:0 auto;padding:32px 24px 44px}
input,button{font:inherit;border-radius:8px;border:1px solid var(--line);padding:10px 14px;background:rgba(255,255,255,0.05);color:var(--ink);transition:all 0.2s}
button{cursor:pointer;font-weight:600;background:rgba(255,255,255,0.1)}button:hover{background:rgba(255,255,255,0.15)}button:focus-visible,input:focus-visible{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--glow)}
.tabs{display:flex;gap:8px;margin-bottom:24px;flex-wrap:wrap}.tab[aria-pressed=true]{background:var(--accent);color:#fff;border-color:var(--accent);box-shadow:0 4px 12px var(--glow)}
.status-line{min-height:24px;color:var(--muted);margin-bottom:16px;font-weight:500}.grid{display:grid;gap:16px}
.card{background:var(--surface);backdrop-filter:blur(8px);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:12px;padding:20px;display:grid;grid-template-columns:96px 1fr auto;gap:16px;align-items:start;box-shadow:0 10px 25px rgba(0,0,0,0.2);animation:fadeUp 0.4s ease-out;transition:transform 0.2s}
.card:hover{transform:translateY(-2px)}
@keyframes fadeUp{from{opacity:0;transform:translateY(15px)}to{opacity:1;transform:translateY(0)}}
.card.new{border-left-color:var(--gold)}.card.in_progress{border-left-color:var(--accent)}.card.done{opacity:.6;filter:grayscale(0.5)}
.room{font-size:36px;font-weight:800;color:#fff;line-height:1}.room small{display:block;font-size:13px;font-weight:500;color:var(--muted);margin-top:6px}
.type{font-weight:700;font-size:18px;color:#fff}.msg{color:var(--ink);margin-top:6px;white-space:pre-wrap;word-break:break-word;font-size:15px}.meta{color:var(--muted);font-size:13px;margin-top:8px}
.actions{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end}.actions button{padding:8px 12px;font-size:13px}.actions button[aria-pressed=true]{background:var(--ok);color:#fff;border-color:var(--ok);box-shadow:0 4px 10px rgba(16,185,129,0.3)}
.empty{border:2px dashed var(--line);border-radius:12px;background:rgba(255,255,255,0.02);padding:40px;text-align:center;color:var(--muted);font-size:16px;font-weight:500}
@media(max-width:720px){header,main{padding-left:16px;padding-right:16px}.connect{width:100%}.connect input{min-width:0;flex:1}.card{grid-template-columns:1fr;padding:16px}.actions{justify-content:flex-start}}
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


class VercelPathRewriteMiddleware:
    """ASGI Middleware to recover original request path when deployed on Vercel."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            current_path = scope.get("path", "")

            raw_qs = scope.get("query_string", b"").decode("utf-8")
            qsl = parse_qsl(raw_qs, keep_blank_values=True)
            qp = dict(qsl)

            recovered_path = None

            # 1. Query parameter 'path', 'nxt_path', or '0' (from Vercel /:path* rewrite)
            for key in ("path", "nxt_path", "0"):
                if key in qp and qp[key]:
                    val = unquote(qp[key]).lstrip("/")
                    if val and not val.endswith(".py"):
                        recovered_path = "/" + val
                    break

            # 2. Vercel HTTP headers
            if not recovered_path:
                headers = dict(scope.get("headers", []))

                rm = headers.get(b"x-now-route-matches", b"").decode("utf-8")
                if rm:
                    rm_dict = dict(parse_qsl(rm))
                    for key in ("path", "nxt_path", "0"):
                        if key in rm_dict and rm_dict[key]:
                            val = unquote(rm_dict[key]).lstrip("/")
                            if val:
                                recovered_path = "/" + val
                            break

                if not recovered_path:
                    mp = headers.get(b"x-matched-path", b"").decode("utf-8")
                    if mp and not mp.endswith(".py") and mp != "/":
                        recovered_path = mp

                if not recovered_path:
                    for h_name in (b"x-forwarded-uri", b"x-original-url", b"x-invoke-path"):
                        val = headers.get(h_name, b"").decode("utf-8")
                        if val and not val.endswith(".py") and val != "/":
                            recovered_path = val.split("?")[0]
                            break

            if recovered_path and recovered_path != current_path:
                scope["path"] = recovered_path
                scope["raw_path"] = recovered_path.encode("utf-8")
                # Remove synthetic path param from query string if present
                if "path" in qp:
                    cleaned = [(k, v) for k, v in qsl if k not in ("path", "nxt_path")]
                    scope["query_string"] = urlencode(cleaned).encode("utf-8")

        await self.app(scope, receive, send)


app = FastAPI(title="Hotel room service backend", lifespan=lifespan)

app.add_middleware(VercelPathRewriteMiddleware)
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
async def create_request(
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
        await forward_request(request_id)
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
