#!/usr/bin/env python3
"""Generate one QR code per hotel room and register the rooms with the backend."""
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

LABEL_W, LABEL_H = 640, 1020
A4_W, A4_H = 2480, 3508

GOLD   = "#C9A84C"
DARK   = "#0A0A0A"
SILVER = "#AAAAAA"


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


def font(size, bold=True):
    candidates = (
        "arialbd.ttf", "Arial Bold.ttf", "calibrib.ttf",
        "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
    ) if bold else (
        "arial.ttf", "calibri.ttf", "DejaVuSans.ttf",
    )
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def centered(draw, y, text, fnt, fill):
    width = draw.textlength(text, font=fnt)
    draw.text(((LABEL_W - width) / 2, y), text, font=fnt, fill=fill)


def _icon(draw, idx, cx, cy, r, color):
    """Draw simple icon inside a circle for the three service labels."""
    if idx == 0:  # Bottle (minibar)
        bw = max(2, r // 3)
        draw.rectangle([cx - bw, cy - r, cx + bw, cy + r], outline=color, width=1)
        draw.rectangle([cx - bw + 1, cy - r - 5, cx + bw - 1, cy - r], outline=color, width=1)
        draw.line([(cx - bw, cy - r // 3), (cx + bw, cy - r // 3)], fill=color, width=1)
    elif idx == 1:  # Luggage
        draw.rectangle([cx - r, cy - r // 3, cx + r, cy + r], outline=color, width=1)
        draw.rectangle([cx - r // 2, cy - r, cx + r // 2, cy - r // 3], outline=color, width=1)
        draw.line([(cx, cy - r // 3), (cx, cy + r)], fill=color, width=1)
    else:  # Bell / front desk
        draw.arc([cx - r, cy - r // 2, cx + r, cy + r // 2], start=180, end=0, fill=color, width=1)
        draw.line([(cx - r, cy + r // 2), (cx + r, cy + r // 2)], fill=color, width=2)
        draw.line([(cx - 2, cy - r), (cx + 2, cy - r)], fill=color, width=2)


def make_label(url, hotel_name, number, logo_path=None):
    img  = Image.new("RGB", (LABEL_W, LABEL_H), DARK)
    draw = ImageDraw.Draw(img)

    # ── Double gold border ────────────────────────────────────
    for off, w in [(10, 2), (18, 1)]:
        draw.rectangle([off, off, LABEL_W - off, LABEL_H - off], outline=GOLD, width=w)

    # ── Hotel logo circle (only if logo provided) ─────────────
    lx, ly, lr = LABEL_W // 2, 108, 52
    if logo_path:
        for gap, w in [(10, 2), (6, 1)]:  # double ring
            draw.ellipse([lx-lr-gap, ly-lr-gap, lx+lr+gap, ly+lr+gap], outline=GOLD, width=w)
        draw.ellipse([lx-lr, ly-lr, lx+lr, ly+lr], fill=DARK)
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_img = logo_img.resize((lr * 2, lr * 2), Image.LANCZOS)
            mask = Image.new("L", (lr * 2, lr * 2), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, lr * 2 - 1, lr * 2 - 1], fill=255)
            img.paste(logo_img, (lx - lr, ly - lr), mask)
        except Exception:
            pass
        y = ly + lr + 22
    else:
        y = 40  # no logo — start content higher

    # ── Hotel name ────────────────────────────────────────────
    centered(draw, y, hotel_name.upper()[:24], font(32), GOLD)
    y += 44
    centered(draw, y, "H O T E L", font(14), GOLD)
    y += 26

    # Thin divider line
    draw.line([(LABEL_W // 2 - 55, y + 4), (LABEL_W // 2 + 55, y + 4)], fill=GOLD, width=1)
    y += 26

    # ── Headline ──────────────────────────────────────────────
    centered(draw, y, "Y O U R   C H E C K - O U T", font(15), GOLD)
    y += 32
    centered(draw, y, "Made Simple.", font(54), "#FFFFFF")
    y += 70

    # ── Description ──────────────────────────────────────────
    centered(draw, y, "Scan the QR code to complete", font(18, bold=False), SILVER)
    y += 28
    centered(draw, y, "your check-out process.", font(18, bold=False), SILVER)
    y += 28

    # Room number (subtle, centered)
    centered(draw, y, f"Room  {number}", font(14), GOLD)
    y += 28

    # ── QR code in white box with gold border ─────────────────
    TARGET = 258
    qr_obj = qrcode.QRCode(error_correction=ERROR_CORRECT_Q, box_size=10, border=2)
    qr_obj.add_data(url)
    qr_obj.make(fit=True)
    qr_raw = qr_obj.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_raw = qr_raw.resize((TARGET, TARGET), Image.LANCZOS)

    pad = 16
    bx  = LABEL_W // 2 - TARGET // 2 - pad
    bw  = TARGET + pad * 2
    draw.rectangle([bx, y, bx + bw, y + bw], fill="#FFFFF8", outline=GOLD, width=3)
    img.paste(qr_raw, (bx + pad, y + pad))
    y += bw + 28

    # ── Three service icons ───────────────────────────────────
    col    = LABEL_W // 3
    icon_r = 26
    labels = ["MINIBAR\nDECLARATION", "LUGGAGE\nPICKUP", "NOTIFY\nFRONT DESK"]
    ifnt   = font(12)

    for i, lbl in enumerate(labels):
        cx = col * i + col // 2
        cy = y + icon_r + 4
        draw.ellipse([cx - icon_r, cy - icon_r, cx + icon_r, cy + icon_r], outline=GOLD, width=2)
        _icon(draw, i, cx, cy, icon_r - 8, GOLD)
        ty = cy + icon_r + 6
        for line in lbl.split("\n"):
            lw = draw.textlength(line, font=ifnt)
            draw.text(((col * i + (col - lw) / 2), ty), line, font=ifnt, fill=GOLD)
            ty += 15
        if i > 0:  # vertical divider
            draw.line([(col * i, y + 4), (col * i, y + icon_r * 2 + 38)], fill=GOLD, width=1)

    y += icon_r * 2 + 56

    # ── Footer ────────────────────────────────────────────────
    draw.line([(28, y), (LABEL_W - 28, y)], fill=GOLD, width=1)
    y += 14
    centered(draw, y, "P O W E R E D   B Y", font(11, bold=False), "#777777")
    y += 20
    centered(draw, y, "✦  P A C K - C H E C K", font(18), GOLD)

    return img


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


def register(api_url, hotel_id, hotel_name, rooms):
    body = json.dumps({
        "hotel_id": hotel_id,
        "hotel_name": hotel_name,
        "rooms": [{"floor": r["floor"], "room_number": r["room_number"], "token": r["token"]} for r in rooms],
    }).encode()
    req = urllib.request.Request(
        api_url.rstrip("/") + "/api/admin/rooms/bulk",
        data=body,
        headers={"Content-Type": "application/json"},
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
    p.add_argument("--base-url", default=os.getenv("QR_BASE_URL", "https://packcheckqrbg.vercel.app"), help="Public URL guests will open")
    p.add_argument("--api-url", default=os.getenv("BACKEND_API_URL", "https://packcheckqrbg.vercel.app"), help="Backend URL for registration (default: base URL)")
    p.add_argument("--out", default="qr_codes")
    p.add_argument("--no-register", action="store_true", help="Only write files; register later")
    p.add_argument("--no-pdf", action="store_true")
    p.add_argument("--register-only", metavar="rooms.json", help="Register an existing manifest without making new QR codes")
    args = p.parse_args()

    if args.register_only:
        data = json.loads(Path(args.register_only).read_text())
        api_url = args.api_url or args.base_url or ask("Backend URL", "http://localhost:8000")
        result = register(api_url, data["hotel_id"], data["hotel_name"], data["rooms"])
        print(f"Registered {result['registered']} rooms with {api_url}")
        return

    hotel_name = args.hotel_name or ask("Hotel name")
    hotel_id = args.hotel_id or slugify(hotel_name)
    floors = args.floors or ask("Number of floors", cast=int)
    per_floor = args.rooms_per_floor or ask("Rooms on each floor", cast=int)
    base_url = (args.base_url or ask("Public base URL for the QR codes", "http://localhost:8000")).rstrip("/")
    if floors < 1 or per_floor < 1 or per_floor > 99:
        sys.exit("Floors must be at least 1 and rooms per floor between 1 and 99.")

    import re
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', hotel_name).strip()
    folder_name = safe_name if safe_name else hotel_id
    out_dir = Path(args.out) / folder_name
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
    try:
        result = register(api_url, hotel_id, hotel_name, rooms)
        print(f"Registered {result['registered']} rooms with {api_url}")
    except (urllib.error.URLError, OSError) as exc:
        sys.exit(f"QR files are saved, but registration failed: {exc}\n"
                 f"Once the backend is reachable, run: python generate_qr.py --register-only {manifest}")


if __name__ == "__main__":
    main()
