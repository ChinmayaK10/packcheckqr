# Deployment and Operations

This project has three parts:

- `backend/`: FastAPI service used by guest QR links and reception staff.
- `qr_generator/`: desktop/CLI tool for creating room QR stickers.
- `demo_main_backend/`: temporary receiver used only while the real hotel backend is not connected.

## Local Windows Use

Double-click `Open QR Generator.bat` to open the QR generator desktop app. It creates or reuses a virtual environment automatically and installs the QR generator dependencies.

To run the QR backend locally:

```bat
scripts\run_backend.bat
```

To run the demo receiver:

```bat
scripts\run_demo_backend.bat
```

Then open `http://127.0.0.1:9100/` to view the live demo receiver dashboard.

## GitHub Deployment

This project is ready for direct GitHub-based deployment without Docker.

You can deploy two separate web services from the same GitHub repository:

- QR backend: guest page, staff page, room verification, request queue.
- Demo main backend: temporary receiver that stands in for your real hotel backend.

### Service 1: QR Backend

1. Push the `hotel-qr` folder to GitHub.
2. Create a web service on your hosting provider.
3. Select the GitHub repository.
4. Set the service/root directory to:

```text
backend
```

5. Use this build command:

```text
pip install -r requirements.txt
```

6. Use this start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

7. Add the required environment variables from the section below.

### Service 2: Demo Main Backend

Create another web service from the same GitHub repository.

Set the service/root directory to:

```text
demo_main_backend
```

Use this build command:

```text
pip install -r requirements.txt
```

Use this start command:

```text
python demo_main_backend.py --host 0.0.0.0 --port $PORT
```

After this service is deployed, copy its public URL and set the QR backend environment variable:

```env
MAIN_BACKEND_URL=https://your-demo-main-backend-url/in
```

Open the demo backend public URL without `/in` to see the received-request dashboard.

When your real backend is ready, replace `MAIN_BACKEND_URL` with your real backend endpoint.

For Render, the included `render.yaml` can create both services as a blueprint. For Railway, Heroku-style platforms, or similar Python hosts, the included `Procfile` files provide the web process commands.

## Backend Environment

Copy `backend/.env.example` to `backend/.env` and set real values before deployment.

Required production values:

```env
SECRET_KEY=<long random value>
STAFF_API_KEY=<staff password/key>
ADMIN_API_KEY=<admin registration key>
```

Optional forwarding values:

```env
MAIN_BACKEND_URL=https://your-real-backend.example.com/room-requests
MAIN_BACKEND_API_KEY=<shared key if required>
```

## Production Notes

- Put the backend behind HTTPS before using real QR codes.
- Do not commit or share `backend/.env`, `backend/hotel.db`, or generated `rooms.json` files.
- Replace `demo_main_backend` with your real backend by changing `MAIN_BACKEND_URL`.
- SQLite is fine for a controlled demo, but some hosts erase local files during redeploys. For real production, use PostgreSQL or a host with persistent disk storage.
- For multi-hotel or high-traffic usage, move from SQLite to PostgreSQL and store verify-attempt limits in Redis.
