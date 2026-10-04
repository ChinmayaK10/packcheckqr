#!/usr/bin/env python3
"""Desktop app for generating and registering hotel QR codes."""
import csv
import json
import queue
import secrets
import threading
import tkinter as tk
import sys
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from generate_qr import build_pdf, make_label, register, room_number, slugify

import customtkinter as ctk

APP_TITLE = "Hotel QR Generator"
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

def get_default_out_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / "qr_codes"
    return Path.cwd() / "qr_codes"


class QRGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x650")
        self.minsize(700, 600)
        self.events = queue.Queue()

        self.hotel_name = ctk.StringVar()
        self.hotel_id = ctk.StringVar()
        self.floors = ctk.IntVar(value=3)
        self.rooms_per_floor = ctk.IntVar(value=2)
        self.start_floor = ctk.IntVar(value=1)
        self.base_url = ctk.StringVar(value="https://packcheckqrbg.vercel.app")
        self.api_url = ctk.StringVar(value="https://packcheckqrbg.vercel.app")
        self.admin_key = ctk.StringVar(value="admin-secret")
        self.out_dir = ctk.StringVar(value=str(get_default_out_dir()))
        self.make_pdf = ctk.BooleanVar(value=True)
        self.do_register = ctk.BooleanVar(value=True)

        self._build_ui()
        self.after(150, self._drain_events)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        main_frame = ctk.CTkFrame(self, corner_radius=15)
        main_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        main_frame.grid_columnconfigure(1, weight=1)

        heading = ctk.CTkLabel(main_frame, text="Hotel QR Generator", font=ctk.CTkFont(size=24, weight="bold"))
        heading.grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(20, 15))

        self._entry(main_frame, 1, "Hotel name", self.hotel_name)
        self._entry(main_frame, 2, "Hotel ID", self.hotel_id, hint="Optional. Auto-created if empty.")
        
        # Spinboxes (Using Entries for customtkinter simplicity)
        self._entry(main_frame, 3, "Floors", self.floors)
        self._entry(main_frame, 4, "Rooms per floor", self.rooms_per_floor)
        self._entry(main_frame, 5, "Start floor", self.start_floor)
        
        self._entry(main_frame, 6, "Public QR base URL", self.base_url)
        self._entry(main_frame, 7, "Backend API URL", self.api_url)
        self._entry(main_frame, 8, "Admin key", self.admin_key, show="*")

        # Output folder row
        ctk.CTkLabel(main_frame, text="Output folder").grid(row=9, column=0, sticky="w", padx=20, pady=5)
        ctk.CTkEntry(main_frame, textvariable=self.out_dir).grid(row=9, column=1, sticky="ew", padx=10, pady=5)
        ctk.CTkButton(main_frame, text="Browse", command=self._browse, width=80).grid(row=9, column=2, sticky="ew", padx=(0, 20), pady=5)

        # Checkboxes
        checks_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        checks_frame.grid(row=10, column=1, columnspan=2, sticky="w", padx=10, pady=15)
        ctk.CTkCheckBox(checks_frame, text="Create print-sheet PDF", variable=self.make_pdf).pack(side="left", padx=(0, 20))
        ctk.CTkCheckBox(checks_frame, text="Register rooms with backend", variable=self.do_register).pack(side="left")

        # Generate Button
        self.generate_button = ctk.CTkButton(main_frame, text="Generate QR Codes", command=self._start, height=40, font=ctk.CTkFont(size=14, weight="bold"))
        self.generate_button.grid(row=11, column=1, columnspan=2, sticky="e", padx=20, pady=10)

        # Status and Log
        self.status = ctk.CTkLabel(main_frame, text="Ready", font=ctk.CTkFont(size=12, slant="italic"))
        self.status.grid(row=12, column=0, columnspan=3, sticky="w", padx=20, pady=(10, 0))

        self.log = ctk.CTkTextbox(main_frame, height=120, state="disabled")
        self.log.grid(row=13, column=0, columnspan=3, sticky="nsew", padx=20, pady=10)
        main_frame.grid_rowconfigure(13, weight=1)

    def _entry(self, parent, row, label, var, hint=None, show=""):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=20, pady=5)
        entry = ctk.CTkEntry(parent, textvariable=var, show=show, placeholder_text=hint)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=10, pady=5)

    def _browse(self):
        chosen = filedialog.askdirectory(initialdir=self.out_dir.get() or str(Path.cwd()))
        if chosen:
            self.out_dir.set(chosen)

    def _start(self):
        try:
            config = self._config()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.generate_button.configure(state="disabled")
        self._write_log("Starting generation...")
        threading.Thread(target=self._generate, args=(config,), daemon=True).start()

    def _config(self):
        hotel_name = self.hotel_name.get().strip()
        if not hotel_name:
            raise ValueError("Hotel name is required.")
        floors = int(self.floors.get())
        per_floor = int(self.rooms_per_floor.get())
        if floors < 1 or per_floor < 1 or per_floor > 99:
            raise ValueError("Floors must be at least 1 and rooms per floor must be between 1 and 99.")
        if self.do_register.get() and not self.admin_key.get().strip():
            raise ValueError("Admin key is required when registration is enabled.")
        return {
            "hotel_name": hotel_name,
            "hotel_id": self.hotel_id.get().strip() or slugify(hotel_name),
            "floors": floors,
            "rooms_per_floor": per_floor,
            "start_floor": int(self.start_floor.get()),
            "base_url": self.base_url.get().strip().rstrip("/"),
            "api_url": self.api_url.get().strip().rstrip("/"),
            "admin_key": self.admin_key.get().strip(),
            "out_dir": Path(self.out_dir.get().strip()),
            "make_pdf": self.make_pdf.get(),
            "do_register": self.do_register.get(),
        }

    def _generate(self, config):
        try:
            import re
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', config["hotel_name"]).strip()
            folder_name = safe_name if safe_name else config["hotel_id"]
            out_dir = config["out_dir"] / folder_name
            rooms, labels = [], []
            for floor in range(config["start_floor"], config["start_floor"] + config["floors"]):
                floor_dir = out_dir / f"floor_{floor:02d}"
                floor_dir.mkdir(parents=True, exist_ok=True)
                for idx in range(1, config["rooms_per_floor"] + 1):
                    number = room_number(floor, idx)
                    token = secrets.token_urlsafe(9)
                    label = make_label(f"{config['base_url']}/r/{token}", config["hotel_name"], number)
                    label.save(floor_dir / f"room_{number}.png")
                    labels.append(label)
                    rooms.append({"floor": floor, "room_number": number, "token": token})

            manifest = out_dir / "rooms.json"
            manifest.write_text(json.dumps({
                "hotel_id": config["hotel_id"],
                "hotel_name": config["hotel_name"],
                "rooms": rooms,
            }, indent=2))
            with open(out_dir / "rooms.csv", "w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=["floor", "room_number", "token"])
                writer.writeheader()
                writer.writerows(rooms)
            if config["make_pdf"]:
                build_pdf(labels, out_dir / "print_sheet.pdf")
            self.events.put(("log", f"Created {len(rooms)} QR codes in {out_dir}"))

            if config["do_register"]:
                result = register(
                    config["api_url"],
                    config["admin_key"],
                    config["hotel_id"],
                    config["hotel_name"],
                    rooms,
                )
                self.events.put(("log", f"Registered {result['registered']} rooms with {config['api_url']}"))
            self.events.put(("done", str(out_dir)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._write_log(value)
                self.status.configure(text=value)
            elif kind == "done":
                self.generate_button.configure(state="normal")
                self.status.configure(text="Done")
                messagebox.showinfo(APP_TITLE, f"QR codes are ready:\n{value}")
            elif kind == "error":
                self.generate_button.configure(state="normal")
                self.status.configure(text="Failed")
                messagebox.showerror(APP_TITLE, value)
                self._write_log("ERROR: " + value)
        self.after(150, self._drain_events)

    def _write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


if __name__ == "__main__":
    QRGeneratorApp().mainloop()
