import os
import sys
import time
import socket
import threading
import subprocess
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from flask import Flask, send_from_directory, jsonify, request
from flask_sock import Sock
import pyautogui

APP_NAME = "LUAHUB Virtual VR"
PORT = 8765
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Support both repo layouts: website/index.html and root index.html.
WEB_DIR = os.path.join(BASE_DIR, "website")
if not os.path.isfile(os.path.join(WEB_DIR, "index.html")):
    WEB_DIR = BASE_DIR

app = Flask(__name__, static_folder=None)
sock = Sock(app)

state_lock = threading.Lock()
state = {
    "connected": False,
    "camera": "LUAKAMERA",
    "tracking": False,
    "head_x": 0.0,
    "head_y": 0.0,
    "hand": "none",
    "last_seen": 0.0,
    "keys": set(),
}
pressed_keys = set()
last_mouse = (0.0, 0.0)
mouse_enabled = False
running = True

KEY_MAP = {
    "forward": "w",
    "backward": "s",
    "left": "a",
    "right": "d",
    "jump": "space",
    "sprint": "shift",
}

def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def release_all():
    global pressed_keys
    for key in list(pressed_keys):
        try:
            pyautogui.keyUp(key)
        except Exception:
            pass
    pressed_keys.clear()

def press_state(new_keys):
    global pressed_keys
    desired = {KEY_MAP[k] for k in new_keys if k in KEY_MAP}
    for key in pressed_keys - desired:
        try:
            pyautogui.keyUp(key)
        except Exception:
            pass
    for key in desired - pressed_keys:
        try:
            pyautogui.keyDown(key)
        except Exception:
            pass
    pressed_keys = desired

@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")

@app.get("/api/status")
def api_status():
    with state_lock:
        return jsonify({
            "app": APP_NAME,
            "connected": state["connected"],
            "camera": state["camera"],
            "tracking": state["tracking"],
            "last_seen": state["last_seen"],
            "headTracking": mouse_enabled,
        })

@app.post("/api/settings")
def api_settings():
    global mouse_enabled
    data = request.get_json(silent=True) or {}
    mouse_enabled = bool(data.get("headTracking", False))
    with state_lock:
        state["tracking"] = mouse_enabled
    return jsonify({"ok": True, "headTracking": mouse_enabled})

@sock.route("/ws")
def websocket(ws):
    with state_lock:
        state["connected"] = True
        state["last_seen"] = time.time()
    try:
        while True:
            raw = ws.receive(timeout=10)
            if raw is None:
                with state_lock:
                    if time.time() - state["last_seen"] > 4:
                        state["connected"] = False
                continue
            import json
            try:
                data = json.loads(raw)
            except Exception:
                continue
            kind = data.get("type")
            with state_lock:
                state["last_seen"] = time.time()
                state["connected"] = True
            if kind == "keys":
                press_state(data.get("keys", []))
            elif kind == "stop":
                release_all()
            elif kind == "tracking":
                with state_lock:
                    state["head_x"] = max(-1.0, min(1.0, float(data.get("x", 0))))
                    state["head_y"] = max(-1.0, min(1.0, float(data.get("y", 0))))
                    state["hand"] = str(data.get("gesture", "none"))[:32]
                if mouse_enabled:
                    # Relative mouse movement is intentionally disabled by default.
                    # Browser tracking landmarks alone do not provide calibrated, reliable
                    # Roblox camera control on every game.
                    pass
    except Exception:
        pass
    finally:
        release_all()
        with state_lock:
            state["connected"] = False

def run_server():
    # Use a local-only server. Access from the phone is via ADB reverse forwarding.
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)

def find_adb():
    """Find ADB from PATH, common install locations, or beside the EXE."""
    candidates = []
    found = shutil.which("adb") or shutil.which("adb.exe")
    if found:
        candidates.append(found)

    home = os.path.expanduser("~")
    candidates.extend([
        os.path.join(home, "Downloads", "platform-tools", "adb.exe"),
        os.path.join(home, "platform-tools", "adb.exe"),
        os.path.join(BASE_DIR, "platform-tools", "adb.exe"),
    ])
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.extend([
            os.path.join(exe_dir, "platform-tools", "adb.exe"),
            os.path.join(exe_dir, "adb.exe"),
        ])

    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen and os.path.isfile(candidate):
            seen.add(candidate)
            return candidate
    return None


def adb_setup():
    adb = find_adb()
    if not adb:
        return False, (
            "ADB belum ditemukan. Pastikan adb.exe ada di "
            "Downloads\\platform-tools atau tambahkan folder itu ke PATH."
        )

    try:
        # Check that the ADB server/device command is callable, then set USB reverse.
        version = subprocess.run(
            [adb, "version"], capture_output=True, text=True, timeout=8
        )
        if version.returncode != 0:
            detail = (version.stderr or version.stdout or "ADB tidak dapat dijalankan").strip()
            return False, f"ADB ditemukan tetapi gagal dijalankan:\n{detail}"

        devices = subprocess.run(
            [adb, "devices"], capture_output=True, text=True, timeout=8
        )
        device_lines = [
            line.strip() for line in devices.stdout.splitlines()[1:]
            if line.strip() and "\tdevice" in line
        ]
        if not device_lines:
            return False, (
                f"ADB ditemukan: {adb}\nTetapi HP belum terotorisasi/terdeteksi. "
                "Buka kunci HP, izinkan USB debugging, lalu cabut-pasang kabel."
            )

        result = subprocess.run(
            [adb, "reverse", f"tcp:{PORT}", f"tcp:{PORT}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, f"ADB port forwarding aktif.\nADB: {adb}\nHP: {device_lines[0]}"

        detail = (result.stderr or result.stdout or "Tidak ada detail error").strip()
        return False, f"ADB ditemukan, tetapi port forwarding gagal:\n{detail}"
    except Exception as exc:
        return False, f"Gagal menjalankan ADB ({adb}):\n{exc}"

class AppUI:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("820x600")
        root.minsize(760, 540)
        root.configure(bg="#101116")
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#101116")
        self.style.configure("Card.TFrame", background="#191b24")
        self.style.configure("TLabel", background="#101116", foreground="#f4f5f7", font=("Segoe UI", 10))
        self.style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"), foreground="#ff354d")
        self.style.configure("Sub.TLabel", foreground="#aeb3c2")
        self.style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=9)
        self.style.map("TButton", background=[("active", "#ff354d")])
        self.style.configure("Accent.TButton", background="#ff354d", foreground="white")
        self.style.configure("Card.TLabel", background="#191b24", foreground="#f4f5f7")
        self.style.configure("CardTitle.TLabel", background="#191b24", foreground="#ff5266",
                             font=("Segoe UI", 11, "bold"))

        outer = ttk.Frame(root, padding=22)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="LUAHUB", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="VIRTUAL VR  •  USB CAMERA & PHONE CONTROLLER",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 15))

        cards = ttk.Frame(outer)
        cards.pack(fill="x")
        self.status_card = ttk.Frame(cards, style="Card.TFrame", padding=15)
        self.status_card.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ttk.Label(self.status_card, text="STATUS", style="CardTitle.TLabel").pack(anchor="w")
        self.status_text = ttk.Label(self.status_card, text="Starting local server…", style="Card.TLabel")
        self.status_text.pack(anchor="w", pady=(8, 0))

        camera_card = ttk.Frame(cards, style="Card.TFrame", padding=15)
        camera_card.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ttk.Label(camera_card, text="CAMERA INPUT", style="CardTitle.TLabel").pack(anchor="w")
        self.camera_var = tk.StringVar(value="LUAKAMERA (HP via USB)")
        self.camera_combo = ttk.Combobox(camera_card, textvariable=self.camera_var,
                                         values=["LUAKAMERA (HP via USB)", "Webcam PC / Camo Studio"],
                                         state="readonly", width=27)
        self.camera_combo.pack(anchor="w", pady=(8, 0))

        guide = ttk.Frame(outer, style="Card.TFrame", padding=18)
        guide.pack(fill="both", expand=True, pady=16)
        ttk.Label(guide, text="QUICK SETUP", style="CardTitle.TLabel").pack(anchor="w")
        steps = [
            "1  Install Android Platform Tools (ADB) on Windows.",
            "2  On Android: enable Developer options → USB debugging, then connect USB.",
            "3  Click “Connect USB (ADB)” below and approve the debugging prompt on the phone.",
            "4  After ADB reverse succeeds, open http://127.0.0.1:8765 in the phone browser.",
            "5  Use the on-screen directional pad. Keep Roblox focused to receive keyboard input.",
        ]
        for step in steps:
            ttk.Label(guide, text=step, style="Card.TLabel", wraplength=700).pack(anchor="w", pady=4)

        actions = ttk.Frame(outer)
        actions.pack(fill="x")
        ttk.Button(actions, text="Connect USB (ADB)", style="Accent.TButton",
                   command=self.connect_usb).pack(side="left")
        ttk.Button(actions, text="Open Phone Website", command=self.open_phone).pack(side="left", padx=8)
        ttk.Button(actions, text="Emergency STOP", command=self.stop_all).pack(side="right")
        self.footer = ttk.Label(outer, text=f"PC local address: http://127.0.0.1:{PORT}  •  No APK required",
                                style="Sub.TLabel")
        self.footer.pack(anchor="w", pady=(14, 0))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_status()

    def connect_usb(self):
        ok, msg = adb_setup()
        if ok:
            messagebox.showinfo("LUAHUB USB", msg + "\n\nSekarang buka http://127.0.0.1:8765 di browser HP.")
        else:
            messagebox.showwarning("ADB setup", msg)

    def open_phone(self):
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        messagebox.showinfo("Buka di HP", "Untuk browser HP, aktifkan USB debugging dan ADB reverse terlebih dahulu, lalu buka http://127.0.0.1:8765 di HP.")

    def stop_all(self):
        release_all()

    def refresh_status(self):
        with state_lock:
            connected = state["connected"]
            gesture = state["hand"]
            hx, hy = state["head_x"], state["head_y"]
        self.status_text.configure(
            text=f"Phone website: {'CONNECTED' if connected else 'Waiting for phone'}\n"
                 f"Last gesture: {gesture}\nHead landmarks: X {hx:+.2f} / Y {hy:+.2f}"
        )
        self.root.after(500, self.refresh_status)

    def close(self):
        release_all()
        self.root.destroy()

def main():
    threading.Thread(target=run_server, daemon=True).start()
    root = tk.Tk()
    AppUI(root)
    root.mainloop()
    release_all()

if __name__ == "__main__":
    main()
