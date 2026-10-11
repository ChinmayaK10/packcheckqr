#!/usr/bin/env python3
"""
Seed Hotel rooms and initial requests directly into Firebase Realtime Database.
Usage:
    python seed_firebase.py
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE = Path(__file__).parent
cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase_key.json")
cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON", "")
db_url = os.getenv("FIREBASE_DATABASE_URL") or os.getenv("firebase_database_url", "")

if not db_url:
    print("Error: FIREBASE_DATABASE_URL is not set in .env")
    exit(1)

import firebase_admin
from firebase_admin import credentials, db

cred = None
if cred_json:
    cred = credentials.Certificate(json.loads(cred_json))
else:
    candidates = [
        Path(cred_path),
        BASE / cred_path,
        BASE / "firebase_key.json",
        BASE.parent / "firebase_key.json",
    ]
    for c in candidates:
        if c.is_file():
            cred = credentials.Certificate(str(c))
            break

if not cred:
    print(f"Error: Firebase credentials file not found at '{cred_path}'.")
    print("Please place your Firebase service account JSON key in the backend folder.")
    exit(1)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {"databaseURL": db_url})

# Exact initial hotel dataset requested
HOTEL_DATA = {
  "Hotels": {
    "RoyalRitis": {
      "Floor 1": {
        "room101": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "yes"},
        "room102": {"Floor": 1, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room103": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "no"},
        "room104": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "no"},
        "room105": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "yes"},
        "room106": {"Floor": 1, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room107": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "yes"},
        "room108": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "no"},
        "room109": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "yes"},
        "room110": {"Floor": 1, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room111": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "no"},
        "room112": {"Floor": 1, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room113": {"Floor": 1, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room114": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "no"},
        "room115": {"Floor": 1, "Request": "Checkout Only", "MiniBar": "no"}
      },
      "Floor 2": {
        "room201": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room202": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "yes"},
        "room203": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "yes"},
        "room204": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "yes"},
        "room205": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room206": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "no"},
        "room207": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "yes"},
        "room208": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "no"},
        "room209": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room210": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room211": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "no"},
        "room212": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room213": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room214": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room215": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "no"},
        "room216": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room217": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "no"},
        "room218": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "yes"},
        "room219": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room220": {"Floor": 2, "Request": "Checkout Only", "MiniBar": "no"},
        "room221": {"Floor": 2, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"}
      },
      "Floor 3": {
        "room301": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room302": {"Floor": 3, "Request": "Checkout Only", "MiniBar": "yes"},
        "room303": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room304": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room305": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room306": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room307": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room308": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room309": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room310": {"Floor": 3, "Request": "Checkout Only", "MiniBar": "no"},
        "room311": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room312": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room313": {"Floor": 3, "Request": "Checkout Only", "MiniBar": "yes"},
        "room314": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room315": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room316": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room317": {"Floor": 3, "Request": "Checkout Only", "MiniBar": "no"},
        "room318": {"Floor": 3, "Request": "Checkout Only", "MiniBar": "yes"},
        "room319": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room320": {"Floor": 3, "Request": "Checkout Only", "MiniBar": "no"},
        "room321": {"Floor": 3, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"}
      },
      "Floor 4": {
        "room401": {"Floor": 4, "Request": "Checkout Only", "MiniBar": "no"},
        "room402": {"Floor": 4, "Request": "Checkout Only", "MiniBar": "no"},
        "room403": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room404": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room405": {"Floor": 4, "Request": "Checkout Only", "MiniBar": "no"},
        "room406": {"Floor": 4, "Request": "Checkout Only", "MiniBar": "yes"},
        "room407": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room408": {"Floor": 4, "Request": "Checkout Only", "MiniBar": "yes"},
        "room409": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room410": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room411": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room412": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room413": {"Floor": 4, "Request": "Checkout Only", "MiniBar": "no"},
        "room414": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room415": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room416": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room417": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room418": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"},
        "room419": {"Floor": 4, "Request": "Checkout Only", "MiniBar": "no"},
        "room420": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "yes"},
        "room421": {"Floor": 4, "Request": "Checkout & Cart Assistance", "MiniBar": "no"}
      }
    }
  }
}

ref = db.reference("Hotels/RoyalRitis")
ref.set(HOTEL_DATA["Hotels"]["RoyalRitis"])
print("Successfully seeded all 73 rooms of RoyalRitis into Firebase Realtime Database!")
