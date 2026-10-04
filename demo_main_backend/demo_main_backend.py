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
<style>
:root{--bg:#f4f6f5;--panel:#fff;--ink:#17211f;--muted:#66736f;--line:#d8dfdc;--pine:#123a34;--gold:#a47e2f;--bad:#9b2c2c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:400 15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
header{background:var(--pine);color:#f6faf8;padding:18px 28px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
h1{margin:0;font-size:22px;font-weight:700}
main{max-width:1120px;margin:0 auto;padding:24px}
.summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:18px}
.metric{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px}
.metric strong{display:block;font-size:26px;color:var(--pine)}
.metric span{color:var(--muted)}
.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:8px 0 14px;color:var(--muted)}
.list{display:grid;gap:10px}
.request{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:6px;padding:14px 16px;display:grid;grid-template-columns:100px 1fr auto;gap:12px;align-items:start}
.room{font-size:30px;font-weight:800;line-height:1;color:var(--pine)}
.room small{display:block;font-size:12px;font-weight:500;color:var(--muted);margin-top:5px}
.type{font-weight:700}
.msg{margin-top:4px;white-space:pre-wrap}
.meta{color:var(--muted);font-size:13px;margin-top:5px}
.badge{border:1px solid var(--line);border-radius:999px;padding:4px 10px;background:#fafafa;color:var(--muted);white-space:nowrap}
.empty{border:1px dashed var(--line);border-radius:6px;padding:28px;text-align:center;color:var(--muted);background:#fff}
button{font:inherit;border:1px solid var(--line);background:#fff;border-radius:4px;padding:8px 12px;cursor:pointer;color:var(--ink)}
button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
@media(max-width:720px){main{padding:16px}.summary{grid-template-columns:1fr}.request{grid-template-columns:1fr}.badge{justify-self:start}}
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
