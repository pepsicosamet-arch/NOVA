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


# ---------------- kurulu uygulamalar ----------------
def _packages(pattern):
    import glob
    import os
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
    return bool(base and glob.glob(os.path.join(base, pattern)))


def _has_protocol(scheme):
    if not IS_WIN:
        return False
    import winreg
    for root, path in ((winreg.HKEY_CLASSES_ROOT, scheme), (winreg.HKEY_CURRENT_USER, rf"Software\Classes\{scheme}")):
        try:
            with winreg.OpenKey(root, path):
                return True
        except OSError:
            pass
    return False


def installed():
    """PC'de kurulu masaüstü uygulamaları: {'whatsapp': bool, 'telegram': bool, 'x': bool}"""
    import os
    appdata = os.environ.get("APPDATA", "")
    return {
        "whatsapp": IS_WIN and (_packages("*WhatsAppDesktop*") or _has_protocol("whatsapp")),
        "telegram": IS_WIN and (_packages("*TelegramDesktop*") or os.path.isdir(os.path.join(appdata, "Telegram Desktop"))
                                or _has_protocol("tg")),
        "x": IS_WIN and (_packages("*Twitter*") or _packages("*.X_*")),
    }


def focus_window(*names) -> bool:
    """Başlığında verilen adlardan biri geçen pencereyi öne getir (Enter doğru yere gitsin)."""
    if not IS_WIN:
        return False
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if not u.IsWindowVisible(h):
            return True
        n = u.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, buf, n + 1)
            title = buf.value
            if any(x.lower() in title.lower() for x in names) and "NOVA" not in title:
                found.append(h)
                return False
        return True

    u.EnumWindows(cb, 0)
    if found:
        u.ShowWindow(found[0], 9)
        u.SetForegroundWindow(found[0])
        return True
    return False


def normalize_phone(p: str) -> str:
    digits = re.sub(r"[^\d]", "", p or "")
    if digits.startswith("0") and len(digits) == 11:
        digits = "90" + digits[1:]
    elif len(digits) == 10 and digits.startswith("5"):
        digits = "90" + digits
    return digits


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
                c["phone"] = normalize_phone(p)
        if len(parts) == 1 and re.fullmatch(r"[+\d\s()-]{10,}", parts[0]):   # yalnızca numara yazılmışsa
            c["phone"] = normalize_phone(parts[0])
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
    # 64 bit tutamaçlar için tüm tipler açıkça belirtilmeli (yoksa OverflowError)
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    u32.OpenClipboard.argtypes = [ctypes.c_void_p]
    u32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    u32.SetClipboardData.restype = ctypes.c_void_p
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
    auto = True   # kullanıcı istedi: onay sormadan, doğrudan gönder
    wait = wait or float(settings.get("msg_wait") or 4)
    name = contact["name"] if contact else ""

    if contact and contact.get("search") and platform in ("whatsapp", "telegram"):
        return send_by_search(platform, name, text, auto, wait)

    if platform == "whatsapp":
        if not contact or not contact.get("phone"):
            return send_by_search(platform, name, text, auto, wait)
        q = urllib.parse.quote(text)
        desktop = installed()["whatsapp"] and _open(f"whatsapp://send?phone={contact['phone']}&text={q}")
        if not desktop:
            webbrowser.open(f"https://web.whatsapp.com/send?phone={contact['phone']}&text={q}")
            wait += 8
        where = "WhatsApp uygulamasından" if desktop else "WhatsApp Web'den"
        if auto and IS_WIN:
            def go():
                time.sleep(wait)
                focus_window("WhatsApp")
                time.sleep(0.3)
                _keys(VK_RETURN)
            threading.Thread(target=go, daemon=True).start()
            return True, f"{where} {name} kişisine gönderiyorum."
        return True, f"{where} {name} sohbetini mesaj hazır şekilde açtım. Göndermek için Enter'a bas."

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
        desktop = installed()["telegram"] and _open(uri)
        if not desktop:
            if contact.get("tg"):
                webbrowser.open(f"https://web.telegram.org/k/#@{contact['tg']}")
            else:
                webbrowser.open("https://web.telegram.org/k/")
                return True, ("Telegram uygulaması kurulu değil ve bu kişinin kullanıcı adı yok. "
                              "Telegram Web'i açtım; numarayla sohbet açmak için kişiye @kullanıcı adı ekle.")
            wait += 8
        set_clipboard(text)
        where = "Telegram uygulamasından" if desktop else "Telegram Web'den"
        if auto and IS_WIN:
            def go():
                time.sleep(wait)
                focus_window("Telegram")
                time.sleep(0.3)
                _keys(VK_CONTROL, VK_V)
                time.sleep(0.4)
                _keys(VK_RETURN)
            threading.Thread(target=go, daemon=True).start()
            return True, f"{where} {name} kişisine gönderiyorum."
        return True, f"{where} {name} sohbetini açtım, mesaj panoda. Ctrl+V ve Enter ile gönder."

    if platform == "x":
        webbrowser.open("https://x.com/intent/post?text=" + urllib.parse.quote(text))
        if auto and IS_WIN:                       # X'te Ctrl+Enter gönderiyi paylaşır
            def go():
                time.sleep(wait + 4)
                focus_window(" / X", "X'te", "Gönderi", "Post", "Twitter")
                time.sleep(0.4)
                _keys(VK_CONTROL, VK_RETURN)
            threading.Thread(target=go, daemon=True).start()
            return True, "X'te paylaşıyorum. Tarayıcında X hesabın açık olmalı."
        return True, "X'te gönderi hazır. Paylaş butonuna basman yeterli."

    return False, "Bu platformu tanımıyorum."


def send_by_search(platform, name, text, auto, wait):
    """Numara gerekmeden: uygulamayı aç, kişiyi uygulamanın kendi aramasında bul, mesajı yaz, gönder."""
    apps = installed()
    if not apps.get(platform):
        nm = "WhatsApp" if platform == "whatsapp" else "Telegram"
        return False, f"{nm} uygulaması bu bilgisayarda yüklü değil. Microsoft Store'dan {nm}'ı kurarsan mesajı doğrudan gönderirim."
    # Masaüstü uygulaması: Windows UI Otomasyonu ile kişiyi bul ve gönder (sonucu bekler)
    from . import wa_auto
    return wa_auto.send(platform, name, text, auto, wait)


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
def _dative_root(w):
    """anneme → annem, ahmet'e → ahmet, babaya → baba, ömrüm → ömrüm"""
    w = w.strip(".,!?")
    if "'" in w:
        return w.split("'")[0]
    if re.search(r"[aeıioöuü](ye|ya)$", w):
        return w[:-2]
    if re.search(r"[^aeıioöuü][ea]$", w) and len(w) > 3:
        return w[:-1]
    return w


def recipient(n, platform):
    """Mesajın kime gideceğini cümleden çıkar: ('Annem', 'anneme')."""
    m = re.search(r"(\S+(?:\s\S+)?)\s+kişisine\b", n)
    if m:
        words = m.group(1).split()
        words = [w for w in words if not re.match(PLAT_RE[platform], w)]
        name = " ".join(words[-1:])
        return name.capitalize(), name
    words = n.split()
    plat_i = next((i for i, w in enumerate(words) if re.match(PLAT_RE[platform], w)), None)
    for w in words:                                 # 'ahmet'e' gibi kesme işaretli yönelme eki
        if re.search(r"'(e|a|ye|ya)$", w) and not re.match(PLAT_RE[platform], w):
            return _dative_root(w).capitalize(), w
    if plat_i is not None:                          # platformun hemen önündeki/arkasındaki kelime
        for j in (plat_i - 1, plat_i + 1):
            if 0 <= j < len(words) and re.search(r"(e|a)$", words[j]) and words[j] not in ("bir", "da", "de"):
                return _dative_root(words[j]).capitalize(), words[j]
    return "", ""



PLAT_RE = {
    "whatsapp": r"\b(whatsapp|vatsap|watsap|wp)[\w']*",
    "telegram": r"\btelegram[\w']*",
    "x": r"\b(twitter|tivitır|x)'?(ta|te|tan|ten|da|de|dan|den)\b|\btweet\w*|\btvit\w*",
}


def parse(text: str, n: str, contacts):
    """'WhatsApp'tan anneme geliyorum yaz' → {'platform', 'contact', 'text'} ya da None."""
    platform = next((p for p, rx in PLAT_RE.items() if re.search(rx, n)), None)
    implicit = not platform
    if not platform:
        # platform söylenmediyse: "ömrüm kişisine ... mesaj gönder" → WhatsApp
        if (re.search(r"kişisine", n) and re.search(r"\b(gönder|yolla|ilet|yaz|at)\w*\s*$", n)) or \
                (re.search(r"'(e|a|ye|ya)\b", n) and re.search(r"\b(mesaj\w*|yaz)\b.*\b(gönder|yolla|at|ilet|yaz)\s*$", n)):
            platform = "whatsapp"
        else:
            return None
    is_post = platform == "x" and re.search(r"paylaş|tweet|tvit|gönderi|at\b", n)
    is_msg = re.search(r"\b(yaz|gönder|mesaj|de ki|söyle|ilet|at)\b", n)
    if not (is_post or is_msg):
        return None
    # tırnak içindeki metin varsa onu al
    m = re.search(r"(?:^|[\s:])[\"“'‘](.+?)[\"”'’]\s*(?:diye|yaz|gönder|mesaj|paylaş|de|$)", text)
    contact = find_contact(contacts, n) if platform != "x" else None
    num = re.search(r"(\+?\d[\d\s-]{8,15}\d)", n)
    if platform != "x" and not contact and num and len(normalize_phone(num.group(1))) >= 11:
        ph = normalize_phone(num.group(1))
        contact = {"name": num.group(1).strip(), "phone": ph, "tg": ""}
        n = n.replace(num.group(1), " ")
    if m and len(m.group(1)) > 1:
        body = m.group(1).strip()
    else:
        body = n
        body = re.sub(PLAT_RE[platform], " ", body)
        if contact:
            body = re.sub(rf"(^|\s){re.escape(_tr_lower(contact['name']))}\S*", " ", body)
        body = re.sub(r"^\s*(nova\s+)?", "", body)
        body = re.sub(r"^\s*(şunu|şu mesajı|bir mesaj)\s+", " ", body)
        body = re.sub(r"\b(mesajını|mesajı|üzerinden|kişisine)\b", " ", body)
        body = re.sub(r"^\s*(bir\s+)?mesaj\s*$", "", body)
        body = re.sub(r"^\s*(paylaş|yaz|gönder)\s*:?\s*", " ", body)
        body = re.sub(r"\s*(diye\s+)?(mesaj\s+)?(yaz|gönder|at|paylaş|ilet|de ki|söyle|tweetle|tweet at|gönderi paylaş)\s*:?\s*$", "", body)
        body = re.sub(r"^\s*(yaz|gönder|paylaş|de ki)\s*:?\s*", "", body)
        body = re.sub(r"^\s*'\w*\s*", "", body)
        body = re.sub(r"\s+", " ", body).strip(" :,.")
    if not body:
        return {"platform": platform, "contact": contact, "text": "", "missing": "text"}
    if platform != "x" and not contact:
        guess, word = recipient(n, platform)
        if word:
            body = re.sub(rf"(^|\s){re.escape(word)}(\s|$)", " ", " " + body + " ").strip()
        body = re.sub(r"\bkişisine\b", " ", body).strip()
        body = re.sub(r"^\s*'\w*\s*", "", body)
        if not guess:
            return {"platform": platform, "contact": None, "text": body, "missing": "contact"}
        contact = {"name": guess, "search": True}
        if not body:
            return {"platform": platform, "contact": contact, "text": "", "missing": "text"}
    # kullanıcının yazdığı büyük/küçük harfleri geri getir
    low = text.replace("İ", "i").lower().replace("’", "'")
    i = low.find(body)
    if i >= 0:
        body = text[i:i + len(body)]
    return {"platform": platform, "contact": contact, "text": body[:1].upper() + body[1:], "implicit": implicit}
