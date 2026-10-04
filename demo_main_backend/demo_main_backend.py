#!/usr/bin/env python3
"""Demo stand-in for your main hotel application.

It receives the requests forwarded by the room service backend and prints them
in the terminal. No extra packages needed.

    python demo_main_backend.py            # listens on http://127.0.0.1:9100/in
    python demo_main_backend.py --port 9200

Then set MAIN_BACKEND_URL=http://127.0.0.1:9100/in in backend/.env and restart the backend.
If you set MAIN_BACKEND_API_KEY there, run this with the same value in the
MAIN_BACKEND_API_KEY environment variable to check the Authorization header.
"""
import argparse
import json
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tempfile

TYPES = {"checkout": "CHECK OUT", "cart": "LUGGAGE CART", "room_service": "ROOM SERVICE"}
API_KEY = os.getenv("MAIN_BACKEND_API_KEY", "")
lock = threading.Lock()

DB_PATH = os.path.join(tempfile.gettempdir(), "demo_vercel_db.json")

def load_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"count": 0, "requests": []}

def save_db(data):
    try:
        with open(DB_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Demo backend requests</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0f172a;--surface:rgba(30,41,59,0.7);--ink:#f8fafc;--muted:#94a3b8;--line:rgba(255,255,255,0.1);--accent:#3b82f6;--gold:#f59e0b;--err:#ef4444;--ok:#10b981;--glow:rgba(59,130,246,0.5)}
*{box-sizing:border-box;margin:0}
body{min-height:100vh;background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 100%);color:var(--ink);font:400 15px/1.5 'Inter',system-ui,sans-serif}
header{background:rgba(15,23,42,0.85);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border-bottom:1px solid var(--line);padding:18px 28px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;position:sticky;top:0;z-index:10}
h1{font-size:24px;font-weight:800;background:linear-gradient(to right,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
#status{color:var(--muted);font-weight:500}
main{max-width:1120px;margin:0 auto;padding:32px 24px 44px}
.summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:24px}
.metric{background:var(--surface);backdrop-filter:blur(8px);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 10px 25px rgba(0,0,0,0.2);transition:transform 0.2s;animation:fadeUp 0.5s ease-out}
.metric:hover{transform:translateY(-3px)}
.metric strong{display:block;font-size:32px;font-weight:800;background:linear-gradient(to right,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px}
.metric span{color:var(--muted);font-weight:500}
@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:8px 0 18px;color:var(--muted);font-weight:500}
.list{display:grid;gap:14px}
.request{background:var(--surface);backdrop-filter:blur(8px);border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:14px;padding:20px;display:grid;grid-template-columns:100px 1fr auto;gap:16px;align-items:start;box-shadow:0 8px 20px rgba(0,0,0,0.2);animation:fadeUp 0.4s ease-out;transition:transform 0.2s}
.request:hover{transform:translateY(-2px)}
.room{font-size:32px;font-weight:800;line-height:1;color:#fff}
.room small{display:block;font-size:13px;font-weight:500;color:var(--muted);margin-top:6px}
.type{font-weight:700;font-size:17px;color:#fff}
.msg{margin-top:6px;white-space:pre-wrap;color:var(--ink);word-break:break-word}
.meta{color:var(--muted);font-size:13px;margin-top:8px}
.badge{border:1px solid var(--line);border-radius:999px;padding:6px 14px;background:rgba(255,255,255,0.05);color:var(--muted);white-space:nowrap;font-weight:600;font-size:13px}
.empty{border:2px dashed var(--line);border-radius:14px;padding:40px;text-align:center;color:var(--muted);background:rgba(255,255,255,0.02);font-size:16px;font-weight:500}
button{font:600 14px 'Inter',system-ui,sans-serif;border:1px solid var(--line);background:rgba(255,255,255,0.08);border-radius:10px;padding:10px 18px;cursor:pointer;color:var(--ink);transition:all 0.2s}
button:hover{background:rgba(255,255,255,0.15);transform:translateY(-1px)}
button:focus-visible{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--glow)}
@media(max-width:720px){header,main{padding-left:16px;padding-right:16px}.summary{grid-template-columns:1fr}.request{grid-template-columns:1fr;padding:16px}.badge{justify-self:start}}
</style>
</head>
<body>
<header>
  <h1>Demo backend requests</h1>
  <div id="status">Waiting for forwarded requests</div>
</header>
<main>
  <section class="summary">
    <div class="metric"><strong id="total">0</strong><span>Total received</span></div>
    <div class="metric"><strong id="latest">-</strong><span>Latest room</span></div>
    <div class="metric"><strong id="updated">-</strong><span>Last update</span></div>
  </section>
  <div class="toolbar"><span>Incoming request feed</span><button id="refresh">Refresh</button></div>
  <div id="list" class="list"></div>
</main>
<script>
const TYPES={checkout:"Check out",cart:"Luggage cart",room_service:"Room service"};
const $=id=>document.getElementById(id);
async function load(){
  const res=await fetch("/api/requests");
  const data=await res.json();
  $("total").textContent=data.count;
  $("latest").textContent=data.requests[0]?.room_number||"-";
  $("updated").textContent=new Date().toLocaleTimeString([], {hour:"2-digit", minute:"2-digit", second:"2-digit"});
  $("status").textContent=data.count?`${data.count} request${data.count===1?"":"s"} received`:"Waiting for forwarded requests";
  const list=$("list"); list.innerHTML="";
  if(!data.requests.length){list.innerHTML='<div class="empty">No forwarded requests yet.</div>';return;}
  data.requests.forEach(r=>{
    const item=document.createElement("article"); item.className="request";
    const room=document.createElement("div"); room.className="room"; room.textContent=r.room_number||"-";
    const floor=document.createElement("small"); floor.textContent=r.floor!=null?`Floor ${r.floor}`:r.hotel_id||"Hotel"; room.append(floor);
    const body=document.createElement("div");
    const type=document.createElement("div"); type.className="type"; type.textContent=TYPES[r.type]||r.type||"Request"; body.append(type);
    if(r.message){const msg=document.createElement("div"); msg.className="msg"; msg.textContent=r.message; body.append(msg);}
    const meta=document.createElement("div"); meta.className="meta"; meta.textContent=`#${r.id ?? "-"} from ${r.hotel_name || r.hotel_id || "hotel"}${r.preferred_time?", preferred "+r.preferred_time:""}`; body.append(meta);
    const badge=document.createElement("div"); badge.className="badge"; badge.textContent=r.received_at||"Received";
    item.append(room,body,badge); list.append(item);
  });
}
$("refresh").onclick=load;
load();
setInterval(load,3000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _html(self, code, body):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/in", "/index.py"):
            return self._html(200, DASHBOARD)
        if path == "/api/requests":
            with lock:
                db = load_db()
                return self._reply(200, {"count": db["count"], "requests": list(reversed(db["requests"][-100:]))})
        return self._reply(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/in", "/index.py"):
            return self._reply(404, {"error": "use POST /in"})
        if API_KEY and self.headers.get("Authorization") != f"Bearer {API_KEY}":
            print("Rejected a request with a wrong or missing API key")
            return self._reply(401, {"error": "bad key"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self._reply(400, {"error": "invalid JSON"})

        with lock:
            db = load_db()
            db["count"] += 1
            data["received_at"] = datetime.now().strftime("%H:%M:%S")
            db["requests"].append(data)
            save_db(db)
            
        count = db["count"]
        created = datetime.fromtimestamp(data.get("created_at", 0)).strftime("%H:%M:%S")
        print("\n" + "=" * 52)
        print(f"  NEW REQUEST #{data.get('id')}   (received: {count})")
        print("=" * 52)
        print(f"  Hotel   : {data.get('hotel_name')} ({data.get('hotel_id')})")
        print(f"  Room    : {data.get('room_number')}   Floor: {data.get('floor')}")
        print(f"  Service : {TYPES.get(data.get('type'), data.get('type'))}")
        if data.get("preferred_time"):
            print(f"  Time    : {data['preferred_time']}")
        if data.get("message"):
            print(f"  Message : {data['message']}")
        print(f"  Sent at : {created}")
        print("=" * 52, flush=True)
        self._reply(200, {"ok": True})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"Demo main backend listening on http://{args.host}:{args.port}/in")
    print("Waiting for requests. Press Ctrl+C to stop.")
    try:
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
