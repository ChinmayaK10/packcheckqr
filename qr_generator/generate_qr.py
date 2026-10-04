#!/usr/bin/env python3
"""Generate one QR code per hotel room and register the rooms with the backend.

Run with no arguments to be asked for the details, or pass them as flags.
Each QR encodes https://<base-url>/r/<random token>. The room number is not in
the URL: the backend maps the token to a room, so guests never see it.
"""
import argparse
import csv
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_Q

LABEL_W, LABEL_H = 640, 820
A4_W, A4_H = 2480, 3508


def ask(prompt, default=None, cast=str):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            return cast(raw)
        except ValueError:
            print("Please enter a valid value.")


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "hotel"


def room_number(floor, index):
    return f"{floor}{index:02d}"


def font(size):
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def centered(draw, y, text, fnt, fill):
    width = draw.textlength(text, font=fnt)
    draw.text(((LABEL_W - width) / 2, y), text, font=fnt, fill=fill)


def make_label(url, hotel_name, number):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_Q, box_size=12, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr.box_size = max(1, 520 // (qr.modules_count + 2 * qr.border))
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    label = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(label)
    draw.rectangle([0, 0, LABEL_W - 1, LABEL_H - 1], outline="#bbbbbb", width=2)
    centered(draw, 36, hotel_name[:28], font(34), "#123a34")
    label.paste(qr_img, ((LABEL_W - qr_img.width) // 2, 100 + (520 - qr_img.height) // 2))
    centered(draw, 650, f"Room {number}", font(56), "black")
    centered(draw, 735, "Scan for room service", font(28), "#555555")
    return label


def build_pdf(labels, pdf_path):
    cols, rows = 3, 4
    cell_w, cell_h = A4_W // cols, A4_H // rows
    pages = []
    for start in range(0, len(labels), cols * rows):
        page = Image.new("RGB", (A4_W, A4_H), "white")
        for i, label in enumerate(labels[start:start + cols * rows]):
            r, c = divmod(i, cols)
            x = c * cell_w + (cell_w - LABEL_W) // 2
            y = r * cell_h + (cell_h - LABEL_H) // 2
            page.paste(label, (x, y))
        pages.append(page)
    pages[0].save(pdf_path, "PDF", resolution=300, save_all=True, append_images=pages[1:])


def register(api_url, admin_key, hotel_id, hotel_name, rooms):
    body = json.dumps({
        "hotel_id": hotel_id,
        "hotel_name": hotel_name,
        "rooms": [{"floor": r["floor"], "room_number": r["room_number"], "token": r["token"]} for r in rooms],
    }).encode()
    req = urllib.request.Request(
        api_url.rstrip("/") + "/api/admin/rooms/bulk",
        data=body,
        headers={"Content-Type": "application/json", "X-API-Key": admin_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hotel-name")
    p.add_argument("--hotel-id", help="Short slug, e.g. grand-palace (default: from hotel name)")
    p.add_argument("--floors", type=int)
    p.add_argument("--rooms-per-floor", type=int)
    p.add_argument("--start-floor", type=int, default=1)
    p.add_argument("--base-url", default=os.getenv("QR_BASE_URL"), help="Public URL guests will open")
    p.add_argument("--api-url", default=os.getenv("BACKEND_API_URL"), help="Backend URL for registration (default: base URL)")
    p.add_argument("--admin-key", default=os.getenv("ADMIN_API_KEY"))
    p.add_argument("--out", default="qr_codes")
    p.add_argument("--no-register", action="store_true", help="Only write files; register later")
    p.add_argument("--no-pdf", action="store_true")
    p.add_argument("--register-only", metavar="rooms.json", help="Register an existing manifest without making new QR codes")
    args = p.parse_args()

    if args.register_only:
        data = json.loads(Path(args.register_only).read_text())
        api_url = args.api_url or args.base_url or ask("Backend URL", "http://localhost:8000")
        admin_key = args.admin_key or ask("Backend admin key")
        result = register(api_url, admin_key, data["hotel_id"], data["hotel_name"], data["rooms"])
        print(f"Registered {result['registered']} rooms with {api_url}")
        return

    hotel_name = args.hotel_name or ask("Hotel name")
    hotel_id = args.hotel_id or slugify(hotel_name)
    floors = args.floors or ask("Number of floors", cast=int)
    per_floor = args.rooms_per_floor or ask("Rooms on each floor", cast=int)
    base_url = (args.base_url or ask("Public base URL for the QR codes", "http://localhost:8000")).rstrip("/")
    if floors < 1 or per_floor < 1 or per_floor > 99:
        sys.exit("Floors must be at least 1 and rooms per floor between 1 and 99.")

    out_dir = Path(args.out) / hotel_id
    rooms, labels = [], []
    for floor in range(args.start_floor, args.start_floor + floors):
        floor_dir = out_dir / f"floor_{floor:02d}"
        floor_dir.mkdir(parents=True, exist_ok=True)
        for idx in range(1, per_floor + 1):
            number = room_number(floor, idx)
            token = secrets.token_urlsafe(9)
            label = make_label(f"{base_url}/r/{token}", hotel_name, number)
            label.save(floor_dir / f"room_{number}.png")
            labels.append(label)
            rooms.append({"floor": floor, "room_number": number, "token": token})

    manifest = out_dir / "rooms.json"
    manifest.write_text(json.dumps({"hotel_id": hotel_id, "hotel_name": hotel_name, "rooms": rooms}, indent=2))
    with open(out_dir / "rooms.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["floor", "room_number", "token"])
        writer.writeheader()
        writer.writerows(rooms)
    if not args.no_pdf:
        build_pdf(labels, out_dir / "print_sheet.pdf")
    print(f"Created {len(rooms)} QR codes in {out_dir}")

    if args.no_register:
        print(f"Skipped registration. Later, run: python generate_qr.py --register-only {manifest}")
        return
    api_url = args.api_url or base_url
    admin_key = args.admin_key or ask("Backend admin key")
    try:
        result = register(api_url, admin_key, hotel_id, hotel_name, rooms)
        print(f"Registered {result['registered']} rooms with {api_url}")
    except (urllib.error.URLError, OSError) as exc:
        sys.exit(f"QR files are saved, but registration failed: {exc}\n"
                 f"Once the backend is reachable, run: python generate_qr.py --register-only {manifest}")


if __name__ == "__main__":
    main()
