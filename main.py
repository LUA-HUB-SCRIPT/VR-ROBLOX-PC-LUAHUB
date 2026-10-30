
import os
import sys
import json
import time
import threading
import webbrowser
from pathlib import Path

from flask import Flask, send_file, jsonify
from flask_sock import Sock

import pyautogui
import pygame

# ==========================================
# LUAHUB VIRTUAL VR
# Developer: AHZA
# ==========================================

APP_NAME = "LUAHUB VIRTUAL VR"
PORT = 8765

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    if hasattr(sys, "_MEIPASS"):
        WEB_DIR = Path(sys._MEIPASS)
    else:
        WEB_DIR = BASE_DIR
else:
    BASE_DIR = Path(__file__).resolve().parent
    WEB_DIR = BASE_DIR

INDEX_FILE = WEB_DIR / "index.html"

app = Flask(__name__)
sock = Sock(app)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

lock = threading.RLock()

# ==========================================
# STATE
# ==========================================

state = {
    "connected": False,
    "camera": False,
    "tracking": False,
    "head": {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0
    },
    "gamepad": False,
    "gamepad_name": "Not detected",
    "last_seen": 0
}

pressed_keys = set()
running = True
gamepad_instance = None

# ==========================================
# INPUT MAPPING
# ==========================================

KEY_MAP = {
    "forward": "w",
    "back": "s",
    "left": "a",
    "right": "d",
    "jump": "space",
    "sprint": "shift",
    "crouch": "ctrl",
    "interact": "e"
}

def key_down(key):
    if key not in KEY_MAP:
        return

    with lock:
        if key in pressed_keys:
            return

        pressed_keys.add(key)

    try:
        pyautogui.keyDown(KEY_MAP[key])
    except Exception as error:
        print("Key down error:", error)


def key_up(key):
    if key not in KEY_MAP:
        return

    with lock:
        if key not in pressed_keys:
            return

        pressed_keys.discard(key)

    try:
        pyautogui.keyUp(KEY_MAP[key])
    except Exception as error:
        print("Key up error:", error)


def release_all():
    with lock:
        keys = list(pressed_keys)
        pressed_keys.clear()

    for key in keys:
        try:
            pyautogui.keyUp(KEY_MAP[key])
        except Exception:
            pass

    print("[LUAHUB] All keys released")


# ==========================================
# GAMEPAD
# ==========================================

def init_gamepad():
    global gamepad_instance

    try:
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() > 0:
            gamepad_instance = pygame.joystick.Joystick(0)
            gamepad_instance.init()

            state["gamepad"] = True
            state["gamepad_name"] = gamepad_instance.get_name()

            print("[GAMEPAD]", gamepad_instance.get_name())
            return True

    except Exception as error:
        print("[GAMEPAD ERROR]", error)

    state["gamepad"] = False
    state["gamepad_name"] = "Not detected"

    return False


def gamepad_loop():
    global gamepad_instance

    print("[GAMEPAD] Input service started")

    while running:
        try:
            pygame.event.pump()

            if pygame.joystick.get_count() == 0:
                if gamepad_instance:
                    release_all()
                    gamepad_instance = None

                state["gamepad"] = False
                time.sleep(1)
                init_gamepad()
                continue

            if gamepad_instance is None:
                init_gamepad()

            if gamepad_instance is None:
                time.sleep(0.1)
                continue

            pad = gamepad_instance

            # Left analog
            lx = pad.get_axis(0)
            ly = pad.get_axis(1)

            # Deadzone
            deadzone = 0.25

            key_down("forward") if ly < -deadzone else key_up("forward")
            key_down("back") if ly > deadzone else key_up("back")
            key_down("left") if lx < -deadzone else key_up("left")
            key_down("right") if lx > deadzone else key_up("right")

            # Common DualShock-style button mapping
            buttons = pad.get_numbuttons()

            # X
            if buttons > 0:
                key_down("jump") if pad.get_button(0) else key_up("jump")

            # Square
            if buttons > 2:
                key_down("interact") if pad.get_button(2) else key_up("interact")

            # L1 / R1
            if buttons > 4:
                key_down("crouch") if pad.get_button(4) else key_up("crouch")

            if buttons > 5:
                key_down("sprint") if pad.get_button(5) else key_up("sprint")

            time.sleep(0.02)

        except Exception as error:
            print("[GAMEPAD ERROR]", error)
            release_all()
            time.sleep(1)


# ==========================================
# HTTP ROUTES
# ==========================================

@app.route("/")
def home():
    if not INDEX_FILE.exists():
        return "index.html tidak ditemukan", 404

    return send_file(INDEX_FILE)


@app.route("/api/status")
def api_status():
    return jsonify({
        **state,
        "gamepad": bool(state["gamepad"]),
        "gamepad_name": state["gamepad_name"]
    })


@app.route("/api/health")
def health():
    return jsonify({
        "app": APP_NAME,
        "status": "running",
        "port": PORT
    })


# ==========================================
# WEBSOCKET
# ==========================================

@sock.route("/ws")
def websocket(ws):
    print("[WEBSOCKET] Client connected")

    state["connected"] = True

    try:
        while True:
            message = ws.receive()

            if message is None:
                break

            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue

            message_type = data.get("type")

            # ------------------------------
            # KEY DOWN / KEY UP
            # ------------------------------

            if message_type == "key":
                action = data.get("action")
                key_state = data.get("state")

                if key_state == "down":
                    key_down(action)

                elif key_state == "up":
                    key_up(action)

            # ------------------------------
            # RELEASE ALL
            # ------------------------------

            elif message_type in ("stop", "release_all"):
                release_all()

            # ------------------------------
            # TRACKING
            # ------------------------------

            elif message_type == "tracking":
                head = data.get("head", {})

                try:
                    x = float(head.get("x", 0))
                    y = float(head.get("y", 0))
                    z = float(head.get("z", 0))

                    x = max(-1.0, min(1.0, x))
                    y = max(-1.0, min(1.0, y))
                    z = max(-1.0, min(1.0, z))

                    state["head"] = {
                        "x": x,
                        "y": y,
                        "z": z
                    }

                    state["tracking"] = bool(
                        data.get("hand_detected", False)
                        or data.get("head") is not None
                    )

                    state["last_seen"] = time.time()

                except (TypeError, ValueError):
                    pass

    except Exception as error:
        print("[WEBSOCKET ERROR]", error)

    finally:
        state["connected"] = False
        state["tracking"] = False
        release_all()
        print("[WEBSOCKET] Client disconnected")


# ==========================================
# START SERVER
# ==========================================

def run_server():
    print("=" * 45)
    print(APP_NAME)
    print("Developer: AHZA / LUAHUB")
    print("=" * 45)

    print("[SERVER] Starting...")
    print("[SERVER] http://127.0.0.1:8765")

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        threaded=True,
        use_reloader=False
    )


# ==========================================
# MAIN
# ==========================================

def main():
    global running

    init_gamepad()

    threading.Thread(
        target=gamepad_loop,
        daemon=True
    ).start()

    try:
        run_server()

    except KeyboardInterrupt:
        print("\n[LUAHUB] Shutting down...")

    finally:
        running = False
        release_all()

        try:
            pygame.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
