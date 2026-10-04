# Hotel room QR service

Production-shaped demo for hotel room QR service. It has three separate parts:

1. `qr_generator/` creates one QR code per room (and registers the rooms with the backend).
2. `backend/` is the FastAPI app guests and reception use.
3. `demo_main_backend/` is a temporary receiver until your real backend is connected.

For GitHub-based deployment and Windows launchers, see `DEPLOYMENT.md`.

## Quick Windows demo

- Double-click `Open QR Generator.bat` to open the desktop QR generator.
- Run `scripts\run_backend.bat` to start the QR backend at `http://127.0.0.1:8000`.
- Run `scripts\run_demo_backend.bat` to start the temporary receiver at `http://127.0.0.1:9100/in`.
- Open `http://127.0.0.1:9100/` to see forwarded requests in the demo backend dashboard.

For deployment, create two web services from the same GitHub repo: one with root directory `backend`, and one with root directory `demo_main_backend`. Set the QR backend `MAIN_BACKEND_URL` to the demo or real backend URL ending in `/in`.

## How it works

- Each QR encodes `https://your-domain/r/<random token>`. The room number is **not** in the URL; the backend maps the token to a room.
- The guest page asks for the room number. It must match the room behind the QR, otherwise the guest cannot continue (5 wrong tries, then a 10 minute lock).
- After a match the guest gets a 30 minute session and can send: checkout, luggage cart, or room service / other (typed or spoken).
- Every request is saved first, then forwarded to your main backend (retried every minute, up to 10 attempts).
- Reception opens `/staff`, enters the staff key, and sees a live queue (refreshes every 5 seconds, beeps on new requests).

## Run the backend

    cd backend
    pip install -r requirements.txt
    cp .env.example .env        # then set real secrets
    uvicorn app.main:app --host 0.0.0.0 --port 8000

Set `MAIN_BACKEND_URL` in `.env` to forward requests. Each request is POSTed as JSON
(`id, hotel_id, hotel_name, room_number, floor, type, message, preferred_time, created_at`)
with `Authorization: Bearer <MAIN_BACKEND_API_KEY>` if a key is set.

## Generate QR codes

    cd qr_generator
    pip install -r requirements.txt
    python generate_qr.py

It asks for hotel name, floors, rooms per floor, the public base URL and the admin key. Or use flags:

    python generate_qr.py --hotel-name "Grand Palace" --floors 10 --rooms-per-floor 10 \
        --base-url https://rooms.example.com --admin-key YOUR_ADMIN_KEY

Output in `qr_codes/<hotel-id>/`: one labelled PNG per room (`floor_03/room_304.png`),
`print_sheet.pdf` (12 labels per A4 page), and `rooms.json` / `rooms.csv`.

- Room numbers are floor + two digits: floor 3, room 4 is `304`; floor 10, room 4 is `1004`. Use `--start-floor 0` to include a ground floor.
- `--no-register` only writes files. Register later with `python generate_qr.py --register-only qr_codes/<hotel-id>/rooms.json`.
- Running the generator again for the same hotel creates NEW tokens and replaces the old ones, so the old stickers stop working. Use this to replace a stolen or damaged QR.
- Keep `rooms.json` private: the tokens are what identify each room.

## Try it without a main backend (demo receiver)

`demo_main_backend/demo_main_backend.py` stands in for your hotel application and prints every forwarded request in the terminal. No extra packages needed.

    # terminal 1
    python demo_main_backend/demo_main_backend.py

    # terminal 2: set MAIN_BACKEND_URL=http://127.0.0.1:9100/in in backend/.env, then
    cd backend && uvicorn app.main:app --port 8000

Open a room's QR link (or `http://localhost:8000/r/<token>` from `rooms.json`), confirm the room number, send a request, and it appears in terminal 1 and on `/staff`.

## Before going live

- Serve over HTTPS (needed for the microphone and expected for QR links). Put the app behind nginx or Caddy.
- Set long random `SECRET_KEY`, `STAFF_API_KEY`, `ADMIN_API_KEY`.
- SQLite is fine for one hotel. For several hotels or several server processes, move to PostgreSQL and keep the verify-attempt counter in Redis (it is in memory now).
- Voice input uses the browser's speech recognition (works in Chrome and Safari, not every phone). The guest can always type.
