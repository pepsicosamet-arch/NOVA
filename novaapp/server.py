"""Yerel arayüz sunucusu + uygulama penceresi.

Arayüz (web/) 127.0.0.1 üzerinde sunulur ve Microsoft Edge'in "uygulama modu" penceresinde açılır
(adres çubuğu yok, normal bir program gibi görünür). Edge yoksa Chrome, o da yoksa varsayılan tarayıcı.

JavaScript → Python:  POST /api/<fonksiyon>   (gövde: JSON argüman listesi, başlıkta X-Nova-Token)
Python → JavaScript:  GET  /events?t=<token>  (Server-Sent Events akışı)
"""

import json
import logging
import mimetypes
import os
import queue
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("nova.server")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


class Hub:
    """Bağlı arayüz pencerelerine olay dağıtır."""

    def __init__(self):
        self.clients = set()
        self.lock = threading.Lock()
        self.ever_connected = threading.Event()
        self.last_seen = time.time()

    def add(self):
        q = queue.Queue(maxsize=500)
        with self.lock:
            self.clients.add(q)
        self.ever_connected.set()
        self.last_seen = time.time()
        return q

    def remove(self, q):
        with self.lock:
            self.clients.discard(q)
        self.last_seen = time.time()

    def count(self):
        with self.lock:
            return len(self.clients)

    def send(self, data: dict):
        msg = json.dumps(data, ensure_ascii=False)
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass


class UIServer:
    def __init__(self, web_root: str, api):
        self.root = Path(web_root).resolve()
        self.api = api
        self.hub = Hub()
        self.token = secrets.token_urlsafe(24)
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # sessiz
                pass

            def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                url = urlparse(self.path)
                if url.path == "/events":
                    if parse_qs(url.query).get("t", [""])[0] != server.token:
                        return self._send(403, b"{}")
                    return self._events()
                rel = url.path.lstrip("/") or "index.html"
                path = (server.root / rel).resolve()
                if server.root not in path.parents or not path.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype.endswith("javascript"):
                    ctype += "; charset=utf-8"
                self._send(200, path.read_bytes(), ctype)

            def do_POST(self):
                url = urlparse(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""   # gövde her durumda okunmalı (keep-alive)
                if not url.path.startswith("/api/") or self.headers.get("X-Nova-Token") != server.token:
                    return self._send(403, b"{}")
                name = url.path[5:]
                fn = getattr(server.api, name, None)
                if name.startswith("_") or not callable(fn):
                    return self._send(404, b"{}")
                try:
                    args = json.loads(raw or b"[]")
                    if not isinstance(args, list):
                        args = [args]
                    result = fn(*args)
                    self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"))
                except Exception as e:
                    log.exception("API hatası: %s", name)
                    self._send(500, json.dumps({"error": str(e)}).encode("utf-8"))

            def _events(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                q = server.hub.add()
                log.info("Arayüz bağlandı")
                try:
                    self.wfile.write(b": merhaba\n\n")
                    self.wfile.flush()
                    while True:
                        try:
                            msg = q.get(timeout=10)
                            self.wfile.write(f"data: {msg}\n\n".encode("utf-8"))
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass
                finally:
                    server.hub.remove(q)
                    log.info("Arayüz bağlantısı kapandı")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/index.html#t={self.token}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="nova-http").start()
        log.info("Arayüz sunucusu: 127.0.0.1:%s", self.port)


# ---------------- uygulama penceresi ----------------
def find_browser():
    cands = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
        base = os.environ.get(env)
        if base:
            cands.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    cands.append(shutil.which("msedge"))
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        base = os.environ.get(env)
        if base:
            cands.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    cands += [shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium")]
    for c in cands:
        if c and Path(c).is_file():
            return str(c)
    return None


def open_window(url: str, profile_dir: Path, fullscreen: bool):
    """Uygulama penceresini açar. Pencere kapanınca biten işlemi (Popen) döndürür; olmazsa None."""
    exe = find_browser()
    if not exe:
        log.warning("Edge/Chrome bulunamadı, varsayılan tarayıcı açılıyor")
        import webbrowser
        webbrowser.open(url)
        return None
    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [exe, f"--app={url}", f"--user-data-dir={profile_dir}",
            "--no-first-run", "--no-default-browser-check", "--disable-sync",
            "--autoplay-policy=no-user-gesture-required",
            "--disable-features=Translate,msEdgeFirstRunExperience,msHubApps,msImplicitSignin",
            "--window-size=1280,800"]
    if fullscreen:
        args.append("--start-fullscreen")
    log.info("Pencere açılıyor: %s", Path(exe).name)
    flags = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW
    return subprocess.Popen(args, creationflags=flags)


# ---------------- Windows pencere işlemleri ----------------
def _hwnd(title="NOVA"):
    if not sys.platform.startswith("win"):
        return None
    import ctypes
    return ctypes.windll.user32.FindWindowW(None, title) or None


def window_show(mode: str, title="NOVA") -> bool:
    """mode: minimize | restore | front"""
    h = _hwnd(title)
    if not h:
        return False
    import ctypes
    u = ctypes.windll.user32
    if mode == "minimize":
        u.ShowWindow(h, 6)
    else:
        u.ShowWindow(h, 9)
        u.SetForegroundWindow(h)
    return True
