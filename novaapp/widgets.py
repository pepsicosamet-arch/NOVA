"""Arayüz panelleri için veri: haberler, hava durumu, döviz/altın, konum arama, takvim.

Hepsi anahtarsız, herkese açık kaynaklardan gelir. Sonuçlar kısa süre önbellekte tutulur.
"""

import datetime as dt
import html
import json
import logging
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from .config import data_dir

log = logging.getLogger("nova.widgets")
UA = {"User-Agent": "NOVA-Asistan/1.3 (+https://github.com/pepsicosamet-arch/nova)"}
_cache = {}
_cache_lock = threading.Lock()


def cached(key, ttl, fn):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


# ======================= HABERLER =======================
NEWS_FEEDS = {
    "gundem": [("NTV", "https://www.ntv.com.tr/gundem.rss"),
               ("TRT Haber", "https://www.trthaber.com/manset_articles.rss")],
    "sondakika": [("TRT Haber", "https://www.trthaber.com/sondakika_articles.rss"),
                  ("NTV", "https://www.ntv.com.tr/son-dakika.rss")],
    "dunya": [("BBC Türkçe", "https://feeds.bbci.co.uk/turkce/rss.xml"),
              ("NTV", "https://www.ntv.com.tr/dunya.rss")],
    "ekonomi": [("NTV", "https://www.ntv.com.tr/ekonomi.rss"),
                ("TRT Haber", "https://www.trthaber.com/ekonomi_articles.rss")],
    "spor": [("NTV Spor", "https://www.ntvspor.net/rss"),
             ("TRT Haber", "https://www.trthaber.com/spor_articles.rss")],
    "teknoloji": [("NTV", "https://www.ntv.com.tr/teknoloji.rss"),
                  ("TRT Haber", "https://www.trthaber.com/bilim_teknoloji_articles.rss")],
}
NEWS_NAMES = {"gundem": "Gündem", "sondakika": "Son dakika", "dunya": "Dünya", "ekonomi": "Ekonomi",
              "spor": "Spor", "teknoloji": "Teknoloji"}


def _text(el, *names):
    for n in names:
        found = el.find(n)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


def _clean_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def parse_feed(xml_bytes: bytes, source: str):
    items = []
    root = ET.fromstring(xml_bytes)
    ns = {"atom": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}
    entries = root.findall(".//item") or root.findall(".//atom:entry", ns)
    for it in entries[:30]:
        title = _clean_html(it.findtext("title") or it.findtext("atom:title", "", ns))
        link = _text(it, "link")
        if not link:
            le = it.find("atom:link", ns)
            link = le.get("href", "") if le is not None else ""
        date_s = _text(it, "pubDate") or it.findtext("atom:updated", "", ns) or it.findtext("atom:published", "", ns)
        ts = None
        try:
            ts = parsedate_to_datetime(date_s).timestamp() if date_s else None
        except (TypeError, ValueError):
            try:
                ts = dt.datetime.fromisoformat(date_s.replace("Z", "+00:00")).timestamp()
            except ValueError:
                ts = None
        desc = _clean_html(_text(it, "description") or it.findtext("atom:summary", "", ns))
        img = ""
        enc = it.find("enclosure")
        if enc is not None and "image" in (enc.get("type") or "image"):
            img = enc.get("url", "")
        if not img:
            m = it.find("media:content", ns)
            if m is None:
                m = it.find("media:thumbnail", ns)
            if m is not None:
                img = m.get("url", "")
        if title and link:
            items.append({"title": title, "link": link, "ts": ts, "desc": desc[:220],
                          "img": img, "source": source})
    return items


def news(category="gundem", limit=25):
    category = category if category in NEWS_FEEDS else "gundem"

    def load():
        out, seen = [], set()
        for source, url in NEWS_FEEDS[category]:
            try:
                r = requests.get(url, headers=UA, timeout=10)
                r.raise_for_status()
                for item in parse_feed(r.content, source):
                    key = item["title"].lower()[:60]
                    if key not in seen:
                        seen.add(key)
                        out.append(item)
            except Exception as e:
                log.warning("Haber kaynağı okunamadı (%s): %s", url, e)
        out.sort(key=lambda i: i["ts"] or 0, reverse=True)
        return out[:limit]

    items = cached(f"news:{category}", 600, load)
    return {"category": category, "name": NEWS_NAMES[category], "items": items, "ok": bool(items)}


# ======================= MÜZİK =======================
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/130.0 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9"}


def youtube_first(query: str):
    """YouTube aramasındaki ilk videonun kimliği (oynatmak için). Bulunamazsa None."""
    try:
        r = requests.get("https://www.youtube.com/results", params={"search_query": query},
                         headers=BROWSER_UA, cookies={"CONSENT": "YES+1"}, timeout=8)
        ids = re.findall(r'"videoRenderer":\{"videoId":"([\w-]{11})"', r.text) or \
            re.findall(r'"videoId":"([\w-]{11})"', r.text)
        return ids[0] if ids else None
    except Exception as e:
        log.warning("YouTube araması başarısız: %s", e)
        return None


# ======================= HAVA DURUMU =======================
WMO = {0: ("Açık", "☀"), 1: ("Az bulutlu", "🌤"), 2: ("Parçalı bulutlu", "⛅"), 3: ("Kapalı", "☁"),
       45: ("Sisli", "🌫"), 48: ("Kırağılı sis", "🌫"), 51: ("Hafif çisenti", "🌦"), 53: ("Çisenti", "🌦"),
       55: ("Yoğun çisenti", "🌧"), 61: ("Hafif yağmur", "🌦"), 63: ("Yağmur", "🌧"), 65: ("Şiddetli yağmur", "🌧"),
       66: ("Dondurucu yağmur", "🌧"), 67: ("Dondurucu yağmur", "🌧"), 71: ("Hafif kar", "🌨"), 73: ("Kar", "🌨"),
       75: ("Yoğun kar", "❄"), 77: ("Kar taneleri", "🌨"), 80: ("Sağanak", "🌦"), 81: ("Sağanak", "🌧"),
       82: ("Şiddetli sağanak", "⛈"), 85: ("Kar sağanağı", "🌨"), 86: ("Yoğun kar sağanağı", "❄"),
       95: ("Fırtına", "⛈"), 96: ("Dolulu fırtına", "⛈"), 99: ("Dolulu fırtına", "⛈")}
DAYS_SHORT = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


def geocode(query: str):
    """Şehir/yer adı → konum. Önce Open-Meteo (şehirler), sonra OpenStreetMap Nominatim (adresler)."""
    q = (query or "").strip()
    if not q:
        return None

    def load():
        try:
            g = requests.get("https://geocoding-api.open-meteo.com/v1/search", timeout=10, headers=UA,
                             params={"name": q, "count": 1, "language": "tr"}).json()
            if g.get("results"):
                p = g["results"][0]
                label = ", ".join(x for x in (p.get("name"), p.get("admin1"), p.get("country")) if x)
                return {"name": p["name"], "label": label, "lat": p["latitude"], "lon": p["longitude"]}
        except Exception as e:
            log.warning("Open-Meteo konum hatası: %s", e)
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search", timeout=10, headers=UA,
                             params={"q": q, "format": "json", "limit": 1, "accept-language": "tr"}).json()
            if r:
                p = r[0]
                return {"name": p.get("name") or q, "label": p.get("display_name", q),
                        "lat": float(p["lat"]), "lon": float(p["lon"])}
        except Exception as e:
            log.warning("Nominatim konum hatası: %s", e)
        return None

    return cached(f"geo:{q.lower()}", 86400, load)


def weather(city: str):
    place = geocode(city or "İstanbul")
    if not place:
        return {"ok": False, "error": f"{city} bulunamadı"}

    def load():
        w = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, headers=UA, params={
            "latitude": place["lat"], "longitude": place["lon"], "timezone": "auto",
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": 5,
        }).json()
        c, d = w["current"], w["daily"]
        desc, icon = WMO.get(int(c["weather_code"]), ("Değişken", "🌡"))
        days = []
        for i, day in enumerate(d["time"]):
            dd = dt.date.fromisoformat(day)
            dname = "Bugün" if i == 0 else DAYS_SHORT[dd.weekday()]
            dsc, ic = WMO.get(int(d["weather_code"][i]), ("Değişken", "🌡"))
            days.append({"day": dname, "icon": ic, "desc": dsc, "max": round(d["temperature_2m_max"][i]),
                         "min": round(d["temperature_2m_min"][i]),
                         "rain": d.get("precipitation_probability_max", [None] * 5)[i]})
        return {"ok": True, "city": place["name"], "temp": round(c["temperature_2m"]),
                "feels": round(c["apparent_temperature"]), "desc": desc, "icon": icon,
                "wind": round(c["wind_speed_10m"]), "humidity": c.get("relative_humidity_2m"), "days": days}

    try:
        return cached(f"wx:{place['lat']:.2f},{place['lon']:.2f}", 900, load)
    except Exception as e:
        log.warning("Hava durumu hatası: %s", e)
        return {"ok": False, "error": "Hava durumuna ulaşılamadı"}


# ======================= DÖVİZ / ALTIN =======================
def rates():
    def load():
        out = {}
        try:  # Truncgil: döviz + gram altın (anahtarsız)
            j = requests.get("https://finans.truncgil.com/v4/today.json", timeout=10, headers=UA).json()

            def val(key):
                v = j.get(key) or {}
                s = v.get("Selling") or v.get("Satış") or v.get("Buying")
                return float(str(s).replace(".", "").replace(",", ".")) if isinstance(s, str) else float(s)

            for code, key in (("USD", "USD"), ("EUR", "EUR"), ("GBP", "GBP"), ("ALTIN", "GRA")):
                try:
                    out[code] = round(val(key), 2)
                except Exception:
                    pass
        except Exception as e:
            log.warning("Truncgil hatası: %s", e)
        if "USD" not in out:  # yedek: Merkez Bankası
            try:
                r = requests.get("https://www.tcmb.gov.tr/kurlar/today.xml", timeout=10, headers=UA)
                root = ET.fromstring(r.content)
                for cur in root.findall("Currency"):
                    code = cur.get("CurrencyCode")
                    if code in ("USD", "EUR", "GBP"):
                        out[code] = round(float(cur.findtext("ForexSelling")), 2)
            except Exception as e:
                log.warning("TCMB hatası: %s", e)
        return {"ok": bool(out), "rates": out, "time": dt.datetime.now().strftime("%H:%M")}

    return cached("rates", 600, load)


# ======================= TAKVİM =======================
class Calendar:
    def __init__(self):
        self.path = data_dir() / "takvim.json"
        self.lock = threading.Lock()
        try:
            self.events = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []
        except Exception:
            self.events = []

    def _save(self):
        self.path.write_text(json.dumps(self.events, ensure_ascii=False, indent=1), encoding="utf-8")

    def add(self, title, date, time_="", note="", remind=10):
        title = (title or "").strip()
        dt.date.fromisoformat(date)  # doğrula
        if time_:
            dt.datetime.strptime(time_, "%H:%M")
        ev = {"id": uuid.uuid4().hex[:10], "title": title or "Etkinlik", "date": date, "time": time_ or "",
              "note": (note or "").strip(), "remind": int(remind or 0), "notified": []}
        with self.lock:
            self.events.append(ev)
            self.events.sort(key=lambda e: (e["date"], e["time"] or "99"))
            self._save()
        return ev

    def delete(self, eid):
        with self.lock:
            before = len(self.events)
            self.events = [e for e in self.events if e["id"] != eid]
            self._save()
            return len(self.events) != before

    def public(self):
        with self.lock:
            return [{k: v for k, v in e.items() if k != "notified"} for e in self.events]

    def on_day(self, day: dt.date):
        iso = day.isoformat()
        return [e for e in self.public() if e["date"] == iso]

    def due(self, now=None):
        """Hatırlatma zamanı gelen etkinlikler: [(etkinlik, 'once'|'simdi')]."""
        now = now or dt.datetime.now()
        out = []
        with self.lock:
            changed = False
            for e in self.events:
                if not e.get("time"):
                    continue
                start = dt.datetime.fromisoformat(f"{e['date']}T{e['time']}")
                if start < now - dt.timedelta(minutes=2):
                    continue
                marks = e.setdefault("notified", [])
                rem = int(e.get("remind") or 0)
                if rem and "once" not in marks and start - dt.timedelta(minutes=rem) <= now < start:
                    marks.append("once")
                    out.append((dict(e), "once"))
                    changed = True
                if "simdi" not in marks and start <= now:
                    marks.append("simdi")
                    out.append((dict(e), "simdi"))
                    changed = True
            if changed:
                self._save()
        return out


# ---------------- Türkçe tarih/saat ayrıştırma (sesli takvim için) ----------------
MONTHS_TR = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül",
             "ekim", "kasım", "aralık"]
WEEKDAYS_TR = ["pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar"]


def parse_when(n: str, today=None):
    """'yarın saat 15:30', '5 kasım saat 9', 'cuma 14'te' → (tarih, 'HH:MM' | '', kalan metin)."""
    today = today or dt.date.today()
    day, rest = None, n
    m = re.search(r"\b(bugün|yarın|öbür gün|ertesi gün)\b", rest)
    if m:
        day = today + dt.timedelta(days={"bugün": 0, "yarın": 1, "öbür gün": 2, "ertesi gün": 1}[m.group(1)])
        rest = rest.replace(m.group(0), " ")
    if day is None:
        m = re.search(r"\b(\d{1,2}) (" + "|".join(MONTHS_TR) + r")\w*", rest)
        if m:
            mon = MONTHS_TR.index(m.group(2)) + 1
            day = dt.date(today.year, mon, int(m.group(1)))
            if day < today:
                day = day.replace(year=today.year + 1)
            rest = rest.replace(m.group(0), " ")
    if day is None:
        m = re.search(r"\b(?:bu |gelecek |önümüzdeki )?(" + "|".join(sorted(WEEKDAYS_TR, key=len, reverse=True)) + r")\w*", rest)
        if m:
            target = WEEKDAYS_TR.index(m.group(1))
            delta = (target - today.weekday()) % 7 or 7
            day = today + dt.timedelta(days=delta)
            rest = rest.replace(m.group(0), " ")
    t = ""
    m = re.search(r"\b(?:saat )?(\d{1,2})[:.](\d{2})\b", rest) or \
        re.search(r"\bsaat (\d{1,2})(?:'?(?:de|da|te|ta))?\b", rest) or \
        re.search(r"\b(\d{1,2})'?(?:de|da|te|ta)\b", rest)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2)) if m.lastindex and m.lastindex >= 2 else 0
        if re.search(r"akşam|öğleden sonra|gece", rest) and h < 12:
            h += 12
        if 0 <= h < 24 and 0 <= mi < 60:
            t = f"{h:02d}:{mi:02d}"
        rest = rest.replace(m.group(0), " ")
    rest = re.sub(r"\b(sabah|akşam|öğleden sonra|öğlen|gece|'?(de|da|te|ta))\b", " ", rest)
    return day, t, re.sub(r"\s+", " ", rest).strip(" ,.:")
