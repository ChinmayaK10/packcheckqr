#!/usr/bin/env python3
"""Small desktop app for generating and registering hotel QR codes."""
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from generate_qr import build_pdf, make_label, register, room_number, slugify
import csv
import json
import secrets


APP_TITLE = "Hotel QR Generator"


class QRGeneratorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x620")
        self.minsize(680, 560)
        self.events = queue.Queue()

        self.hotel_name = tk.StringVar()
        self.hotel_id = tk.StringVar()
        self.floors = tk.IntVar(value=3)
        self.rooms_per_floor = tk.IntVar(value=2)
        self.start_floor = tk.IntVar(value=1)
        self.base_url = tk.StringVar(value="https://packcheckqrbg.vercel.app")
        self.api_url = tk.StringVar(value="https://packcheckqrbg.vercel.app")
        self.admin_key = tk.StringVar(value="admin-secret")
        self.out_dir = tk.StringVar(value=str(Path(__file__).parent / "qr_codes"))
        self.make_pdf = tk.BooleanVar(value=True)
        self.do_register = tk.BooleanVar(value=True)

        self._build_ui()
        self.after(150, self._drain_events)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        root = ttk.Frame(self, padding=18)
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(1, weight=1)

        heading = ttk.Label(root, text="Hotel QR Generator", font=("Segoe UI", 18, "bold"))
        heading.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        self._entry(root, 1, "Hotel name", self.hotel_name)
        self._entry(root, 2, "Hotel ID", self.hotel_id, hint="Optional. Auto-created from hotel name.")
        self._spin(root, 3, "Floors", self.floors, 1, 200)
        self._spin(root, 4, "Rooms per floor", self.rooms_per_floor, 1, 99)
        self._spin(root, 5, "Start floor", self.start_floor, 0, 200)
        self._entry(root, 6, "Public QR base URL", self.base_url)
        self._entry(root, 7, "Backend API URL", self.api_url)
        self._entry(root, 8, "Admin key", self.admin_key, show="*")

        ttk.Label(root, text="Output folder").grid(row=9, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.out_dir).grid(row=9, column=1, sticky="ew", pady=6)
        ttk.Button(root, text="Browse", command=self._browse).grid(row=9, column=2, sticky="ew", padx=(8, 0), pady=6)

        checks = ttk.Frame(root)
        checks.grid(row=10, column=1, columnspan=2, sticky="w", pady=(8, 12))
        ttk.Checkbutton(checks, text="Create print-sheet PDF", variable=self.make_pdf).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(checks, text="Register rooms with backend", variable=self.do_register).pack(side="left")

        buttons = ttk.Frame(root)
        buttons.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        buttons.columnconfigure(0, weight=1)
        self.generate_button = ttk.Button(buttons, text="Generate QR Codes", command=self._start)
        self.generate_button.grid(row=0, column=1, sticky="e")

        self.status = ttk.Label(root, text="Ready")
        self.status.grid(row=12, column=0, columnspan=3, sticky="w")

        self.log = tk.Text(root, height=12, wrap="word", state="disabled")
        self.log.grid(row=13, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        root.rowconfigure(13, weight=1)

    def _entry(self, parent, row, label, var, hint=None, show=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=var, show=show).grid(row=row, column=1, columnspan=2, sticky="ew", pady=6)

    def _spin(self, parent, row, label, var, start, end):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Spinbox(parent, from_=start, to=end, textvariable=var, width=10).grid(row=row, column=1, sticky="w", pady=6)

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
        self.generate_button.config(state="disabled")
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
            out_dir = config["out_dir"] / config["hotel_id"]
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
                self.status.config(text=value)
            elif kind == "done":
                self.generate_button.config(state="normal")
                self.status.config(text="Done")
                messagebox.showinfo(APP_TITLE, f"QR codes are ready:\n{value}")
            elif kind == "error":
                self.generate_button.config(state="normal")
                self.status.config(text="Failed")
                messagebox.showerror(APP_TITLE, value)
                self._write_log("ERROR: " + value)
        self.after(150, self._drain_events)

    def _write_log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")


if __name__ == "__main__":
    QRGeneratorApp().mainloop()
