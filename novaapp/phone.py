"""Telefon bağlantısı: aynı Wi-Fi'daki telefondan NOVA'yı kullan.

Ayarlar'dan açılır. Bilgisayar ekranındaki QR kodu telefon kamerasıyla okut; açılan sayfadan
NOVA'ya yazabilir, hızlı komut gönderebilir, fotoğraf/dosya yollayabilir ve panoyu paylaşabilirsin.
Bağlantı gizli bir anahtar (token) ile korunur; anahtarı yenilemek eski bağlantıları geçersiz kılar.
"""

import datetime as dt
import json
import logging
import re
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

log = logging.getLogger("nova.phone")
MAX_UPLOAD = 50 * 1024 * 1024


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def upload_dir() -> Path:
    p = Path.home() / "Pictures" / "NOVA" / "Telefon"
    p.mkdir(parents=True, exist_ok=True)
    return p


class PhoneServer:
    def __init__(self, nova):
        self.nova = nova
        self.httpd = None
        self.port = None

    @property
    def token(self):
        t = self.nova.settings.get("phone_token")
        if not t:
            t = secrets.token_urlsafe(12)
            self.nova.settings.update({"phone_token": t})
        return t

    def url(self):
        return f"http://{lan_ip()}:{self.port}/phone#t={self.token}" if self.port else ""

    def qr_svg(self):
        try:
            import segno
            uri = segno.make(self.url(), error="m").png_data_uri(scale=6, border=2, dark="#04050b", light="#ffffff")
            return f'<img src="{uri}" alt="Telefon bağlantı QR kodu">'
        except Exception as e:
            log.warning("QR üretilemedi: %s", e)
            return ""

    def info(self):
        return {"enabled": bool(self.httpd), "url": self.url(), "svg": self.qr_svg() if self.httpd else ""}

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
            self.port = None
            log.info("Telefon bağlantısı kapatıldı")

    def start(self):
        if self.httpd:
            return True
        srv = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json; charset=utf-8"):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body, ensure_ascii=False).encode("utf-8")
                elif isinstance(body, str):
                    body = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _ok(self, url):
                tok = self.headers.get("X-Nova-Token") or parse_qs(url.query).get("t", [""])[0]
                return secrets.compare_digest(tok or "", srv.token)

            def do_GET(self):
                url = urlparse(self.path)
                if url.path in ("/", "/phone"):
                    return self._send(200, PHONE_HTML, "text/html; charset=utf-8")
                if not self._ok(url):
                    return self._send(403, {"error": "anahtar"})
                if url.path == "/phone/api/feed":
                    since = int(parse_qs(url.query).get("since", ["0"])[0] or 0)
                    items = [f for f in list(srv.nova.feed) if f["id"] > since]
                    return self._send(200, {"items": items, "state": srv.nova.state,
                                            "chip": srv.nova.chip_name()})
                if url.path == "/phone/api/clip":
                    from .extras import clipboard_text
                    return self._send(200, {"text": clipboard_text()})
                return self._send(404, {})

            def do_POST(self):
                url = urlparse(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_UPLOAD:
                    return self._send(413, {"error": "Dosya çok büyük (en fazla 50 MB)."})
                raw = self.rfile.read(n) if n else b""
                if not self._ok(url):
                    return self._send(403, {"error": "anahtar"})
                if url.path == "/phone/api/send":
                    text = (json.loads(raw or b"{}").get("text") or "").strip()[:1000]
                    if text:
                        srv.nova.awake = True
                        srv.nova.jobs.put(("phone", text))
                    return self._send(200, {"ok": bool(text)})
                if url.path == "/phone/api/clip":
                    from .social import set_clipboard
                    text = (json.loads(raw or b"{}").get("text") or "")[:20000]
                    ok = set_clipboard(text)
                    srv.nova.emit("toast", text="📱 Telefondan panoya metin geldi.")
                    return self._send(200, {"ok": ok})
                if url.path == "/phone/api/upload":
                    name = unquote(parse_qs(url.query).get("name", ["dosya"])[0])
                    name = re.sub(r"[^\w.\- ]", "_", Path(name).name)[:80] or "dosya"
                    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = upload_dir() / f"{stamp}_{name}"
                    path.write_bytes(raw)
                    srv.nova.emit("toast", text=f"📱 Telefondan dosya geldi: {path.name}")
                    log.info("Telefondan dosya: %s (%d bayt)", path, len(raw))
                    return self._send(200, {"ok": True, "path": str(path)})
                return self._send(404, {})

        port = int(self.nova.settings.get("phone_port") or 8765)
        for p in (port, port + 1, port + 2, 0):
            try:
                self.httpd = ThreadingHTTPServer(("0.0.0.0", p), H)
                break
            except OSError:
                continue
        if not self.httpd:
            return False
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="nova-telefon").start()
        log.info("Telefon bağlantısı: %s", self.url().split("#")[0])
        return True


PHONE_HTML = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#04050b"><title>NOVA · Telefon</title>
<style>
:root{--bg:#04050b;--p:#0d1122;--l:rgba(150,172,230,.18);--ink:#e9edf7;--mu:#8590ad;--acc:#5fe3ff}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
body{display:flex;flex-direction:column;padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}
header{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--l)}
header b{letter-spacing:.35em;font-size:17px}header span{margin-left:auto;font-size:12px;color:var(--mu)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--acc);box-shadow:0 0 10px var(--acc)}
#feed{flex:1;overflow:auto;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
.m{max-width:85%;padding:9px 12px;border-radius:14px;background:var(--p);border:1px solid var(--l)}
.m.u{align-self:flex-end;background:#13314a;border-color:#1d4a6d}
.quick{display:flex;gap:6px;overflow-x:auto;padding:8px 12px;scrollbar-width:none}
.quick button{flex:none;border:1px solid var(--l);background:var(--p);color:var(--ink);border-radius:99px;padding:8px 12px;font:inherit;font-size:13px}
form{display:flex;gap:8px;padding:10px 12px 14px;border-top:1px solid var(--l)}
input[type=text]{flex:1;min-width:0;border:1px solid var(--l);background:var(--p);color:var(--ink);border-radius:12px;padding:12px;font:inherit}
.b{border:0;border-radius:12px;padding:0 14px;font:inherit;font-weight:600;background:var(--acc);color:#04050b}
.tools{display:flex;gap:6px;padding:0 12px 10px}
.tools label,.tools button{flex:1;text-align:center;border:1px solid var(--l);background:var(--p);color:var(--ink);border-radius:12px;padding:10px 6px;font:inherit;font-size:13px}
.tools input{display:none}
#err{display:none;margin:16px;padding:14px;border:1px solid #ff6f80;border-radius:12px;color:#ffc2ca}
.toast{position:fixed;left:50%;bottom:110px;transform:translateX(-50%);background:var(--p);border:1px solid var(--l);padding:8px 14px;border-radius:10px;font-size:13px;opacity:0;transition:.3s}
.toast.on{opacity:1}
</style></head><body>
<header><i class="dot"></i><b id="nm">NOVA</b><span id="st">bağlanıyor…</span></header>
<div id="err">Bağlantı anahtarı geçersiz. Bilgisayardaki QR kodu yeniden okut.</div>
<div id="feed"></div>
<div class="quick" id="quick"></div>
<div class="tools">
  <label>📷 Fotoğraf yolla<input type="file" id="photo" accept="image/*" capture="environment"></label>
  <label>📎 Dosya yolla<input type="file" id="file"></label>
  <button id="clipOut">📋 PC'ye kopyala</button><button id="clipIn">⬇ PC panosu</button>
</div>
<form id="f"><input type="text" id="t" placeholder="NOVA'ya yaz…" autocomplete="off"><button class="b" id="mic" type="button" hidden>🎤</button><button class="b">Gönder</button></form>
<div class="toast" id="toast"></div>
<script>
const tok=(location.hash.match(/t=([\w-]+)/)||[])[1]||"";const H={"X-Nova-Token":tok,"Content-Type":"application/json"};
const $=s=>document.querySelector(s);let since=0;
function toast(t){const e=$("#toast");e.textContent=t;e.classList.add("on");setTimeout(()=>e.classList.remove("on"),2500)}
function add(w,t){const d=document.createElement("div");d.className="m "+(w==="user"?"u":"");d.textContent=t;$("#feed").appendChild(d);$("#feed").scrollTop=1e9}
async function send(text){if(!text)return;await fetch("/phone/api/send",{method:"POST",headers:H,body:JSON.stringify({text})})}
async function poll(){try{const r=await fetch("/phone/api/feed?since="+since,{headers:H});if(r.status===403){$("#err").style.display="block";$("#st").textContent="bağlı değil";return}
const d=await r.json();for(const i of d.items){add(i.who,i.text);since=i.id}$("#st").textContent="bağlı · "+({listening:"dinliyor",speaking:"konuşuyor",thinking:"düşünüyor",sleeping:"uykuda"}[d.state]||"hazır");$("#nm").textContent=d.chip||"NOVA"}catch(e){$("#st").textContent="bağlantı yok"}}
setInterval(poll,1500);poll();
$("#f").onsubmit=e=>{e.preventDefault();const v=$("#t").value.trim();$("#t").value="";send(v)};
for(const q of ["Saat kaç?","Hava nasıl?","Son dakika haberlerini oku","Müziği durdur","Sesi aç","Sesi kıs","Ekran görüntüsü al","Ekranda ne var?","Bilgisayarı kilitle"]){const b=document.createElement("button");b.textContent=q;b.onclick=()=>send(q);$("#quick").appendChild(b)}
async function up(file){if(!file)return;toast("Gönderiliyor…");const r=await fetch("/phone/api/upload?name="+encodeURIComponent(file.name),{method:"POST",headers:{"X-Nova-Token":tok},body:file});toast(r.ok?"Bilgisayara gönderildi ✓":"Gönderilemedi")}
$("#photo").onchange=e=>up(e.target.files[0]);$("#file").onchange=e=>up(e.target.files[0]);
$("#clipOut").onclick=async()=>{const t=prompt("Bilgisayarın panosuna gidecek metin:");if(t)await fetch("/phone/api/clip",{method:"POST",headers:H,body:JSON.stringify({text:t})}).then(()=>toast("Panoya kopyalandı ✓"))};
$("#clipIn").onclick=async()=>{const d=await (await fetch("/phone/api/clip",{headers:H})).json();if(d.text){try{await navigator.clipboard.writeText(d.text);toast("Telefona kopyalandı ✓")}catch(e){prompt("PC panosu:",d.text)}}else toast("PC panosu boş")};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(SR){const m=$("#mic");m.hidden=false;m.onclick=()=>{try{const r=new SR();r.lang="tr-TR";r.onresult=e=>send(e.results[0][0].transcript);r.onerror=()=>toast("Mikrofon bu bağlantıda kullanılamıyor, yazarak gönder.");r.start();toast("Dinliyorum…")}catch(e){toast("Mikrofon kullanılamıyor")}}}
</script></body></html>"""
