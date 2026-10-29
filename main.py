

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
