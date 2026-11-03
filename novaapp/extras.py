"""Ek özellikler: son depremler, namaz vakitleri, hızlı hesap, bilgisayar güç komutları, pano okuma."""

import datetime as dt
import logging
import math
import re
import subprocess
import sys

import requests

log = logging.getLogger("nova.extras")
IS_WIN = sys.platform.startswith("win")
UA = {"User-Agent": "NOVA-Asistan (+https://github.com/pepsicosamet-arch/nova)"}


# ---------------- son depremler (AFAD) ----------------
def earthquakes(limit=5, min_mag=0.0):
    end = dt.datetime.utcnow()
    start = end - dt.timedelta(days=1)
    try:
        r = requests.get("https://deprem.afad.gov.tr/apiv2/event/filter", timeout=10, headers=UA, params={
            "start": start.strftime("%Y-%m-%dT%H:%M:%S"), "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "orderby": "timedesc", "limit": 50, "minmag": min_mag})
        items = r.json()
    except Exception as e:
        log.warning("AFAD hatası: %s", e)
        return None
    out = []
    for q in items[:limit]:
        try:
            t = dt.datetime.fromisoformat(q["date"].replace("Z", "")) + dt.timedelta(hours=3)
            out.append({"mag": float(q["magnitude"]), "place": q.get("location") or q.get("province") or "",
                        "time": t.strftime("%H:%M"), "depth": q.get("depth")})
        except (KeyError, ValueError):
            continue
    return out


def earthquake_reply(n: str):
    big = "büyük" in n or "4" in n
    qs = earthquakes(limit=5, min_mag=3.5 if big else 0)
    if qs is None:
        return "Deprem bilgisine şu an ulaşamadım."
    if not qs:
        return "Son 24 saatte kayda değer bir deprem yok."
    first = qs[0]
    rest = ", ".join(f"{q['place']} {q['mag']:.1f}" for q in qs[1:4])
    txt = f"En son deprem saat {first['time']}'da {first['place']} civarında, büyüklüğü {first['mag']:.1f}."
    return txt + (f" Öncekiler: {rest}." if rest else "")


# ---------------- namaz vakitleri (Diyanet hesabı) ----------------
VAKIT = [("Fajr", "İmsak"), ("Sunrise", "Güneş"), ("Dhuhr", "Öğle"), ("Asr", "İkindi"),
         ("Maghrib", "Akşam"), ("Isha", "Yatsı")]


def prayer_times(city: str):
    try:
        j = requests.get("https://api.aladhan.com/v1/timingsByCity", timeout=10, headers=UA,
                         params={"city": city, "country": "Turkey", "method": 13}).json()
        t = j["data"]["timings"]
        return [(tr, t[en][:5]) for en, tr in VAKIT]
    except Exception as e:
        log.warning("Namaz vakti hatası: %s", e)
        return None


def prayer_reply(n: str, city: str):
    times = prayer_times(city)
    if not times:
        return "Namaz vakitlerine şu an ulaşamadım."
    now = dt.datetime.now().strftime("%H:%M")
    for name in ("akşam", "öğle", "ikindi", "yatsı", "imsak", "sabah", "güneş"):
        if name in n:
            key = {"sabah": "İmsak"}.get(name, name.capitalize().replace("Iıkindi", "İkindi"))
            key = {"İkindi": "İkindi", "Ikindi": "İkindi"}.get(key, key)
            hit = next((v for v in times if v[0].lower() == key.lower() or v[0].lower().startswith(name[:3])), None)
            if hit:
                return f"{city} için {hit[0].lower()} vakti {hit[1]}."
    nxt = next((v for v in times if v[1] > now), None)
    lst = ", ".join(f"{a} {b}" for a, b in times)
    head = f"Sıradaki vakit {nxt[0].lower()}, saat {nxt[1]}. " if nxt else ""
    return f"{head}{city} için bugünkü vakitler: {lst}."


# ---------------- hızlı hesap ----------------
WORD_OPS = [(r"\bartı\b", "+"), (r"\beksi\b", "-"), (r"\bçarpı\b|\bkere\b|\bx\b", "*"), (r"\bbölü\b", "/"),
            (r"\büzeri\b|\büssü\b", "**"), (r"\bmod\b", "%")]


def calc(n: str):
    m = re.search(r"(?:hesapla|kaç eder|kaçtır|kaç yapar|sonucu ne|=)\s*$", n) or re.search(r"^(?:hesapla)\s", n)
    pct = re.search(r"(\d+(?:[.,]\d+)?)'?(?:n[ıiuü]n|[ıiuü]n)? yüzde (\d+(?:[.,]\d+)?)'?\w* kaç", n) or \
        re.search(r"yüzde (\d+(?:[.,]\d+)?)'?\w*\s+(?:of\s+)?(\d+(?:[.,]\d+)?)", n)
    if pct:
        a, b = (float(pct.group(1).replace(",", ".")), float(pct.group(2).replace(",", ".")))
        base, p = (a, b) if pct.re.pattern.startswith("(") else (b, a)
        return _fmt(base * p / 100)
    if not m and not re.search(r"\d\s*(artı|eksi|çarpı|bölü|kere|[+\-*/x])\s*\d", n):
        return None
    expr = re.sub(r"(hesapla|kaç eder|kaçtır|kaç yapar|sonucu ne|nedir|=|\?)", " ", n)
    expr = re.sub(r"karekök\s*(\d+(?:[.,]\d+)?)", r"sqrt(\1)", expr)
    for rx, op in WORD_OPS:
        expr = re.sub(rx, op, expr)
    expr = expr.replace(",", ".")
    if not re.fullmatch(r"[\d\s.+\-*/%()sqrt]+", expr) or not re.search(r"\d", expr):
        return None
    try:
        val = eval(expr, {"__builtins__": {}}, {"sqrt": math.sqrt})  # yalnızca rakam ve işlemler
    except Exception:
        return None
    return _fmt(val)


def _fmt(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, float):
        v = round(v, 4)
    return f"Sonuç {str(v).replace('.', ',')}."


# ---------------- güç komutları (onaylı) ----------------
POWER = {"shutdown": ("bilgisayarı kapatayım mı", ["shutdown", "/s", "/t", "15"]),
         "restart": ("bilgisayarı yeniden başlatayım mı", ["shutdown", "/r", "/t", "15"]),
         "sleep": ("bilgisayarı uyku moduna alayım mı", None),
         "logoff": ("oturumu kapatayım mı", ["shutdown", "/l"])}


def power_intent(n: str):
    if re.search(r"bilgisayar\w* (kapat|kapan)|pc'?yi kapat|sistemi kapat", n):
        return "shutdown"
    if re.search(r"(bilgisayar\w*|pc'?yi|sistemi) (yeniden başlat|resetle|restart)", n):
        return "restart"
    if re.search(r"bilgisayar\w* (uyut|uyku moduna al)", n):
        return "sleep"
    if re.search(r"oturumu kapat|hesaptan çık", n):
        return "logoff"
    return None


def power_do(kind: str):
    if not IS_WIN:
        return False
    if kind == "sleep":
        import ctypes
        ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        return True
    subprocess.Popen(POWER[kind][1], creationflags=0x08000000)
    return True


def power_cancel():
    if IS_WIN:
        subprocess.Popen(["shutdown", "/a"], creationflags=0x08000000)


# ---------------- pano ----------------
def clipboard_text() -> str:
    if not IS_WIN:
        return ""
    import ctypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.GetClipboardData.restype = ctypes.c_void_p
    k.GlobalLock.restype = ctypes.c_wchar_p
    k.GlobalLock.argtypes = [ctypes.c_void_p]
    if not u.OpenClipboard(None):
        return ""
    try:
        h = u.GetClipboardData(13)
        if not h:
            return ""
        txt = k.GlobalLock(h) or ""
        k.GlobalUnlock(ctypes.c_void_p(h))
        return txt
    finally:
        u.CloseClipboard()
