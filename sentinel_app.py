"""
sentinel_app.py
===============
Main entry point for the Ghost Trail desktop application.

Approach (reliable on any Windows PC):
  1. Show a tkinter splash screen
  2. Start FastAPI server (background thread)
  3. Start AI tracker pipeline (background thread)
  4. Wait for server to be ready
  5. Open the dashboard in the user's default browser (Chrome/Edge/Firefox)
  6. Keep a small control window open with system tray icon
  7. User controls the app from the tray icon
"""

from __future__ import annotations

import os
import sys
import threading
import shutil
import subprocess
import time
import tkinter as tk
import tkinter.ttk as ttk
import webbrowser
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

APP_NAME  = "Ghost Trail"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765
SERVER_URL  = f"http://{SERVER_HOST}:{SERVER_PORT}"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_DIR = _base_dir()


# ─────────────────────────────────────────────────────────────────────────────
# Error logger — writes to a file so we can see crashes even from .exe
# ─────────────────────────────────────────────────────────────────────────────

LOG_PATH = BASE_DIR / "sentinel_log.txt"

def _log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass
    print(msg)


def _dashboard_needs_build() -> bool:
    """Return True when React source/config is newer than dashboard/dist."""
    if getattr(sys, "frozen", False):
        return False
    dashboard = BASE_DIR / "dashboard"
    src = dashboard / "src"
    dist = dashboard / "dist"
    if not (dashboard / "package.json").exists():
        return False
    if not dist.exists() or not (dist / "index.html").exists():
        return True
    try:
        newest_source = max(
            p.stat().st_mtime
            for p in [dashboard / "package.json", dashboard / "package-lock.json", dashboard / "vite.config.js", dashboard / "index.html"]
            + list(src.rglob("*.jsx")) + list(src.rglob("*.js")) + list(src.rglob("*.css"))
            if p.exists()
        )
        newest_dist = max(p.stat().st_mtime for p in dist.rglob("*") if p.is_file())
        return newest_source > newest_dist
    except Exception as exc:
        _log(f"[WARN] Could not compare dashboard timestamps: {exc}")
        return False


def _prepare_dashboard() -> bool:
    """Build the React dashboard before starting FastAPI when source is newer.

    This prevents the common situation where edited React source is present but
    sentinel_app.py still serves an older dashboard/dist bundle.
    """
    if getattr(sys, "frozen", False):
        return True
    dashboard = BASE_DIR / "dashboard"
    if not _dashboard_needs_build():
        return True

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        _log("[WARN] Dashboard source is newer than dashboard/dist, but npm was not found. Run 'cd dashboard && npm install && npm run build'.")
        return False

    node_modules_bin = dashboard / "node_modules" / ".bin"
    vite_cmd = node_modules_bin / ("vite.cmd" if os.name == "nt" else "vite")
    if not vite_cmd.exists():
        _log("[INFO] Dashboard dependencies are missing/incomplete. Running npm install...")
        try:
            install = subprocess.run([npm, "install"], cwd=str(dashboard), check=False, timeout=600)
            if install.returncode != 0:
                _log(f"[ERROR] npm install failed with exit code {install.returncode}.")
                return False
        except Exception as exc:
            _log(f"[ERROR] npm install failed: {exc}")
            return False

    _log("[INFO] Building updated React dashboard...")
    try:
        build = subprocess.run([npm, "run", "build"], cwd=str(dashboard), check=False, timeout=600)
        if build.returncode != 0:
            _log(f"[ERROR] Dashboard build failed with exit code {build.returncode}.")
            return False
        _log("[INFO] Dashboard build complete.")
        return True
    except Exception as exc:
        _log(f"[ERROR] Dashboard build failed: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Control Window (serves as loading screen and control panel)
# ─────────────────────────────────────────────────────────────────────────────

class ControlWindow:
    def __init__(self) -> None:
        self._tracker = None
        self._root = tk.Tk()
        self._root.title("Ghost Trail — Control Panel")
        
        # Reliable icon loading using PhotoImage instead of ICO
        try:
            img = tk.PhotoImage(file=str(BASE_DIR / "assets" / "tray_icon.png"))
            self._root.iconphoto(False, img)
        except Exception as e:
            _log(f"[WARN] Failed to load window icon: {e}")

        # Light Mode Theme
        self.bg_color = "#F8F9FA"
        self.text_dark = "#212529"
        self.text_light = "#6C757D"
        
        self._root.configure(bg=self.bg_color)
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        w, h = 340, 280
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        tk.Label(
            self._root, text="GHOST TRAIL",
            font=("Segoe UI", 22, "bold"),
            fg="#0EA5B7", bg=self.bg_color
        ).pack(pady=(24, 2))

        tk.Label(
            self._root, text="Perimeter Defense Control Panel",
            font=("Segoe UI", 10),
            fg=self.text_light, bg=self.bg_color
        ).pack()

        tk.Frame(self._root, bg="#E9ECEF", height=2, width=280).pack(pady=16)

        self._status_var = tk.StringVar(value="Initializing...")
        tk.Label(
            self._root,
            textvariable=self._status_var,
            font=("Segoe UI", 11, "bold"),
            fg="#10B981", bg=self.bg_color
        ).pack(pady=(0, 16))

        btn_cfg = dict(
            font=("Segoe UI", 10, "bold"),
            width=24, pady=8, bd=0, cursor="hand2",
            activeforeground="white",
        )

        tk.Button(
            self._root,
            text="Quit Application",
            bg="#EF4444", fg="white",
            activebackground="#DC2626",
            command=self._quit,
            **btn_cfg
        ).pack(pady=12)

        tk.Label(
            self._root,
            text=f"Server: {SERVER_URL}",
            font=("Segoe UI", 8),
            fg=self.text_light, bg=self.bg_color
        ).pack(side="bottom", pady=10)

        self._update_status()

    def set_tracker(self, tracker):
        self._tracker = tracker

    def set_status(self, text: str) -> None:
        try:
            self._status_var.set(text)
            self._root.update()
        except Exception:
            pass

    def update(self) -> None:
        try:
            self._root.update()
        except Exception:
            pass

    def _update_status(self) -> None:
        try:
            if self._tracker and self._tracker.is_running():
                self._status_var.set("● AI PIPELINE RUNNING")
                self._status_var.get()
            elif self._tracker:
                self._status_var.set("○ AI PIPELINE STOPPED")
        except Exception:
            pass
        try:
            self._root.after(2000, self._update_status)
        except Exception:
            pass

    def _open_browser(self) -> None:
        webbrowser.open(SERVER_URL)

    def _on_close(self) -> None:
        self._root.withdraw()
        self._show_tray_notification()

    def show(self) -> None:
        self._root.deiconify()
        self._root.lift()

    def _show_tray_notification(self) -> None:
        popup = tk.Toplevel()
        popup.title("")
        popup.configure(bg="#FFFFFF")
        popup.overrideredirect(True)
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        w, h = 300, 80
        popup.geometry(f"{w}x{h}+{sw-w-20}+{sh-h-60}")
        popup.attributes("-topmost", True)
        # Draw border
        tk.Frame(popup, bg="#E2E8F0", bd=1).pack(fill="both", expand=True)
        tk.Label(popup, text="Ghost Trail is running",
                 font=("Segoe UI", 10, "bold"), fg="#F97316", bg="#FFFFFF").place(relx=0.5, rely=0.3, anchor="center")
        tk.Label(popup, text="Access it via the system tray or browser.",
                 font=("Segoe UI", 8), fg="#64748B", bg="#FFFFFF").place(relx=0.5, rely=0.6, anchor="center")
        popup.after(3000, popup.destroy)

    def _quit(self) -> None:
        import threading
        import time
        try:
            from sentinel_server import WS_MANAGER
            import asyncio
            loop = asyncio.new_event_loop()
            loop.run_until_complete(WS_MANAGER.broadcast({"type": "shutdown"}))
            loop.close()
        except Exception:
            pass

        if self._tracker:
            threading.Thread(target=self._tracker.stop, daemon=True).start()
        time.sleep(0.1)
        os._exit(0)

    def run(self) -> None:
        self._root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
# System Tray Icon (optional — only if pystray available)
# ─────────────────────────────────────────────────────────────────────────────

def _run_tray(tracker, control_win) -> None:
    try:
        import pystray
        from pystray import MenuItem as Item, Menu
        from PIL import Image, ImageDraw

        # Simple orange circle icon
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, size-2, size-2], fill="#0F1B2D")
        draw.ellipse([2, 2, size-2, size-2], outline="#FF6B00", width=5)

        def _show(_i, _it):
            control_win._root.after(0, control_win.show)

        def _open_browser(_i, _it):
            webbrowser.open(SERVER_URL)

        def _stop(_i, _it):
            tracker.stop()

        def _start(_i, _it):
            if not tracker.is_running():
                tracker.start()

        def _quit(_i, _it):
            tracker.stop()
            _i.stop()
            os._exit(0)

        icon = pystray.Icon(
            "sentinel_ai", img, APP_NAME,
            Menu(
                Item("Show Control Panel", _show, default=True),
                Item("Open Dashboard", _open_browser),
                Menu.SEPARATOR,
                Item("Stop Tracker", _stop),
                Item("Start Tracker", _start),
                Menu.SEPARATOR,
                Item("Quit", _quit),
            )
        )
        icon.run()
    except Exception as e:
        _log(f"[WARN] Tray icon unavailable: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # ── Handle pythonw (no console) stdout/stderr to prevent uvicorn crash ──
    try:
        devnull = open(os.devnull, "w")
        if sys.stdout is None or not hasattr(sys.stdout, 'write'):
            sys.stdout = devnull
        if sys.stderr is None or not hasattr(sys.stderr, 'write'):
            sys.stderr = devnull
        
        # Override standard streams at OS level if possible to prevent any native print issues
        sys.__stdout__ = sys.stdout
        sys.__stderr__ = sys.stderr
    except Exception:
        pass

    _log("=" * 50)
    _log("Ghost Trail starting up")

    # ── 1. Create Control Window Immediately ────────────────────────────
    try:
        control = ControlWindow()
        control.set_status("Starting internal server...")
        control.update()
        _log("Control window displayed")
    except Exception as e:
        _log(f"[ERROR] GUI failed: {e}")
        control = None

    # ── 2. Make sure edited React source is reflected in dashboard/dist ──
    if control:
        control.set_status("Preparing dashboard...")
        control.update()
    _prepare_dashboard()

    # ── 3. Start FastAPI server ─────────────────────────────────────────
    try:
        from sentinel_server import run_server
        server_thread = threading.Thread(
            target=run_server,
            kwargs={"host": SERVER_HOST, "port": SERVER_PORT},
            daemon=True,
            name="sentinel-server",
        )
        server_thread.start()
        _log("FastAPI server thread started")
    except Exception as e:
        _log(f"[ERROR] Server start failed: {e}")

    # ── 4. Start AI pipeline ─────────────────────────────────────────────
    if control:
        control.set_status("Loading AI models (20-40 sec)...")
        control.update()

    try:
        from sentinel_tracker import SentinelTracker
        tracker = SentinelTracker()
        tracker.start()
        if control:
            control.set_tracker(tracker)
        _log("AI tracker thread started")
    except Exception as e:
        _log(f"[ERROR] Tracker start failed: {e}")
        class _DummyTracker:
            def start(self): pass
            def stop(self): pass
            def is_running(self): return False
        tracker = _DummyTracker()
        if control:
            control.set_tracker(tracker)

    # ── 5. Wait for server ready ────────────────────────────────────────
    if control:
        control.set_status("Waiting for server to be ready...")
    _log("Waiting for server...")

    import urllib.request
    ready = False
    deadline = time.time() + 30.0
    while time.time() < deadline:
        if control:
            control.update()
        try:
            urllib.request.urlopen(f"{SERVER_URL}/api/status", timeout=1)
            ready = True
            _log("Server is ready!")
            break
        except Exception:
            time.sleep(0.3)

    if not ready:
        _log("[WARN] Server not ready after 30s — opening browser anyway")

    # ── 6. Open browser & set status ────────────────────────────────────
    if control:
        control.set_status("● AI PIPELINE RUNNING")
        control.update()

    _log(f"Opening browser at {SERVER_URL}")
    webbrowser.open(SERVER_URL)

    # ── 7. Start tray icon in background ────────────────────────────────
    tray_thread = threading.Thread(
        target=_run_tray,
        args=(tracker, control),
        daemon=True,
        name="sentinel-tray",
    )
    tray_thread.start()

    _log("Control window running (main loop)")
    if control:
        control.run()  # Blocking — keeps app alive
    else:
        while True:
            time.sleep(1)

    # ── Cleanup ─────────────────────────────────────────────────────────
    tracker.stop()
    _log("Ghost Trail shutdown complete")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        main()
    except Exception as e:
        _log(f"[FATAL] {e}")
        import traceback
        _log(traceback.format_exc())
        # Show error in a message box
        try:
            import tkinter.messagebox as mb
            mb.showerror("Ghost Trail Error", f"Fatal error:\n\n{e}\n\nCheck sentinel_log.txt for details.")
        except Exception:
            pass
