"""Mesaj gönderme ve paylaşım: WhatsApp, Telegram, X (Twitter).

- WhatsApp: masaüstü uygulaması (whatsapp://send) ya da WhatsApp Web açılır, mesaj kutuya yazılır,
  "otomatik gönder" açıksa Enter'a basılır.
- Telegram: kişinin sohbeti açılır (tg://resolve), mesaj panodan yapıştırılır ve Enter'a basılır.
  İstersen Telegram Bot ile tamamen arka planda gönderilir (Ayarlar → Mesajlaşma → bot anahtarı).
- X: gönderi penceresi metin hazır olarak açılır; paylaş butonuna sen basarsın
  (otomatik paylaşım X'in ücretli API'sini gerektirir).

Kişiler Ayarlar'da her satıra bir kişi olacak şekilde tutulur:
    Annem = +905551112233 = @annem_tg
"""

import logging
import re
import sys
import threading
import time
import urllib.parse
import webbrowser

import requests

log = logging.getLogger("nova.social")
IS_WIN = sys.platform.startswith("win")
PLATFORMS = {"whatsapp": "WhatsApp", "telegram": "Telegram", "x": "X"}
FROM = {"whatsapp": "WhatsApp'tan", "telegram": "Telegram'dan", "x": "X'te"}


# ---------------- kişiler ----------------
def parse_contacts(raw: str):
    out = []
    for line in (raw or "").splitlines():
        parts = [p.strip() for p in re.split(r"[=|;]", line) if p.strip()]
        if not parts:
            continue
        c = {"name": parts[0], "phone": "", "tg": ""}
        for p in parts[1:]:
            if p.startswith("@") or (not re.search(r"\d{6,}", p) and re.fullmatch(r"[A-Za-z0-9_]{4,}", p)):
                c["tg"] = p.lstrip("@")
            else:
                digits = re.sub(r"[^\d]", "", p)
                if digits.startswith("0") and len(digits) == 11:
                    digits = "90" + digits[1:]          # 0555... → 90555...
                elif len(digits) == 10 and digits.startswith("5"):
                    digits = "90" + digits
                c["phone"] = digits
        out.append(c)
    return out


def _tr_lower(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


def find_contact(contacts, text_norm):
    """Metinde geçen kişiyi bul (Türkçe ekleriyle: annem → anneme, annemin...)."""
    best = None
    for c in contacts:
        nm = _tr_lower(c["name"])
        if not nm:
            continue
        if re.search(rf"(^|\s){re.escape(nm)}", text_norm):
            if not best or len(nm) > len(_tr_lower(best["name"])):
                best = c
    return best


# ---------------- Windows klavye / pano ----------------
def _keys(*combo):
    if not IS_WIN:
        return
    import ctypes
    u = ctypes.windll.user32
    for vk in combo:
        u.keybd_event(vk, 0, 0, 0)
    for vk in reversed(combo):
        u.keybd_event(vk, 0, 2, 0)


VK_RETURN, VK_CONTROL, VK_V = 0x0D, 0x11, 0x56


def set_clipboard(text: str) -> bool:
    if not IS_WIN:
        return False
    import ctypes
    from ctypes import wintypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    data = (text + "\0").encode("utf-16-le")
    for _ in range(5):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        return False
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(0x0042, len(data))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        u32.SetClipboardData(13, h)  # CF_UNICODETEXT
        return True
    finally:
        u32.CloseClipboard()


def _open(uri: str) -> bool:
    try:
        if IS_WIN:
            import os
            os.startfile(uri)  # type: ignore[attr-defined]
        else:
            webbrowser.open(uri)
        return True
    except OSError:
        return False


# ---------------- gönderme ----------------
def send(platform, contact, text, settings, wait=None):
    """Mesajı gönderir. (başarılı mı, kullanıcıya söylenecek metin) döndürür."""
    auto = bool(settings.get("msg_auto_send"))
    wait = wait or float(settings.get("msg_wait") or 4)
    name = contact["name"] if contact else ""

    if platform == "whatsapp":
        if not contact or not contact.get("phone"):
            return False, f"{name or 'Bu kişi'} için telefon numarası kayıtlı değil. Ayarlar → Mesajlaşma'dan ekle."
        q = urllib.parse.quote(text)
        opened = _open(f"whatsapp://send?phone={contact['phone']}&text={q}")
        if not opened:
            webbrowser.open(f"https://web.whatsapp.com/send?phone={contact['phone']}&text={q}")
            wait += 6
        if auto and IS_WIN:
            threading.Thread(target=lambda: (time.sleep(wait), _keys(VK_RETURN)), daemon=True).start()
            return True, f"WhatsApp'tan {name} kişisine gönderiyorum."
        return True, f"WhatsApp'ta {name} sohbetini mesaj hazır şekilde açtım. Göndermek için Enter'a bas."

    if platform == "telegram":
        bot, chat = (settings.get("tg_bot_token") or "").strip(), ""
        if contact and contact.get("tg", "").lstrip("-").isdigit():
            chat = contact["tg"]
        if bot and chat:                          # Telegram Bot ile arka planda gönder
            try:
                r = requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", timeout=10,
                                  json={"chat_id": chat, "text": text})
                if r.ok and r.json().get("ok"):
                    return True, f"Telegram'dan {name} kişisine gönderdim."
                log.warning("Telegram bot hatası: %s", r.text[:300])
            except requests.RequestException as e:
                log.warning("Telegram bot hatası: %s", e)
        if not contact or not (contact.get("tg") or contact.get("phone")):
            return False, f"{name or 'Bu kişi'} için Telegram kullanıcı adı ya da numara kayıtlı değil."
        uri = f"tg://resolve?domain={contact['tg']}" if contact.get("tg") else f"tg://resolve?phone={contact['phone']}"
        if not _open(uri):
            webbrowser.open(f"https://t.me/{contact['tg']}" if contact.get("tg") else "https://web.telegram.org/")
        set_clipboard(text)
        if auto and IS_WIN:
            def go():
                time.sleep(wait)
                _keys(VK_CONTROL, VK_V)
                time.sleep(0.4)
                _keys(VK_RETURN)
            threading.Thread(target=go, daemon=True).start()
            return True, f"Telegram'dan {name} kişisine gönderiyorum."
        return True, f"Telegram'da {name} sohbetini açtım, mesaj panoda. Ctrl+V ve Enter ile gönder."

    if platform == "x":
        webbrowser.open("https://x.com/intent/post?text=" + urllib.parse.quote(text))
        return True, "X'te gönderi hazır. Paylaş butonuna basman yeterli."

    return False, "Bu platformu tanımıyorum."


def share_url(platform, text, url=""):
    full = f"{text} {url}".strip()
    if platform == "x":
        return "https://x.com/intent/post?text=" + urllib.parse.quote(text) + ("&url=" + urllib.parse.quote(url) if url else "")
    if platform == "whatsapp":
        return "https://wa.me/?text=" + urllib.parse.quote(full)
    if platform == "telegram":
        return "https://t.me/share/url?url=" + urllib.parse.quote(url or text) + "&text=" + urllib.parse.quote(text)
    return ""


# ---------------- sesli komut ayrıştırma ----------------
PLAT_RE = {
    "whatsapp": r"\b(whatsapp|vatsap|watsap|wp)[\w']*",
    "telegram": r"\btelegram[\w']*",
    "x": r"\b(twitter|tivitır|x)'?(ta|te|tan|ten|da|de|dan|den)\b|\btweet\w*|\btvit\w*",
}


def parse(text: str, n: str, contacts):
    """'WhatsApp'tan anneme geliyorum yaz' → {'platform', 'contact', 'text'} ya da None."""
    platform = next((p for p, rx in PLAT_RE.items() if re.search(rx, n)), None)
    if not platform:
        return None
    is_post = platform == "x" and re.search(r"paylaş|tweet|tvit|gönderi|at\b", n)
    is_msg = re.search(r"\b(yaz|gönder|mesaj|de ki|söyle|ilet|at)\b", n)
    if not (is_post or is_msg):
        return None
    # tırnak içindeki metin varsa onu al
    m = re.search(r"(?:^|[\s:])[\"“'‘](.+?)[\"”'’]\s*(?:diye|yaz|gönder|mesaj|paylaş|de|$)", text)
    contact = find_contact(contacts, n) if platform != "x" else None
    if m and len(m.group(1)) > 1:
        body = m.group(1).strip()
    else:
        body = n
        body = re.sub(PLAT_RE[platform], " ", body)
        if contact:
            body = re.sub(rf"(^|\s){re.escape(_tr_lower(contact['name']))}\S*", " ", body)
        body = re.sub(r"^\s*(nova\s+)?", "", body)
        body = re.sub(r"^\s*(şunu|şu mesajı|bir mesaj)\s+", " ", body)
        body = re.sub(r"\b(mesajını|mesajı|üzerinden)\b", " ", body)
        body = re.sub(r"^\s*(paylaş|yaz|gönder)\s*:?\s*", " ", body)
        body = re.sub(r"\s*(diye\s+)?(mesaj\s+)?(yaz|gönder|at|paylaş|ilet|de ki|söyle|tweetle|tweet at|gönderi paylaş)\s*:?\s*$", "", body)
        body = re.sub(r"^\s*(yaz|gönder|paylaş|de ki)\s*:?\s*", "", body)
        body = re.sub(r"\s+", " ", body).strip(" :,.")
    if not body:
        return {"platform": platform, "contact": contact, "text": "", "missing": "text"}
    if platform != "x" and not contact:
        g = re.search(r"(\w+)'?(?:e|a|ye|ya)\b", n)
        guess = g.group(1) if g else ""
        body = re.sub(rf"\b{re.escape(guess)}'?(e|a|ye|ya)\b\s*", "", body).strip() if guess else body
        return {"platform": platform, "contact": None, "guess": guess, "text": body, "missing": "contact"}
    # kullanıcının yazdığı büyük/küçük harfleri geri getir
    low = text.replace("İ", "i").lower().replace("’", "'")
    i = low.find(body)
    if i >= 0:
        body = text[i:i + len(body)]
    return {"platform": platform, "contact": contact, "text": body[:1].upper() + body[1:]}
