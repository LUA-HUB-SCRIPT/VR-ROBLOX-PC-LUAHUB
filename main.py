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

