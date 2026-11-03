"""Bilgisayar komutları: uygulama/site açma, arama, ses, medya, saat, hava, ekran görüntüsü.

handle(text) bir yanıt metni döndürür ya da komut değilse None (o zaman beyin yanıtlar).
"""

import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

from .brain import DAYS, MONTHS

IS_WIN = sys.platform.startswith("win")


def norm(text: str) -> str:
    t = text.replace("İ", "i").lower()
    t = t.replace("’", "'")
    return re.sub(r"\s+", " ", t).strip(" .!?")


SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "instagram": "https://www.instagram.com", "tiktok": "https://www.tiktok.com",
    "github": "https://github.com", "whatsapp": "https://web.whatsapp.com",
    "gmail": "https://mail.google.com", "spotify": "https://open.spotify.com",
    "twitter": "https://x.com", "x": "https://x.com", "netflix": "https://www.netflix.com",
    "chatgpt": "https://chatgpt.com", "gemini": "https://gemini.google.com",
    "haritalar": "https://maps.google.com", "harita": "https://maps.google.com",
    "çeviri": "https://translate.google.com", "linkedin": "https://www.linkedin.com",
    "twitch": "https://www.twitch.tv", "reddit": "https://www.reddit.com",
}

APPS = {  # Windows komutları
    "hesap makinesi": "calc", "not defteri": "notepad", "paint": "mspaint",
    "komut istemi": "cmd", "terminal": "wt", "dosya gezgini": "explorer",
    "gezgin": "explorer", "ayarlar": "ms-settings:", "görev yöneticisi": "taskmgr",
    "denetim masası": "control", "kamera": "microsoft.windows.camera:",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "chrome": "chrome", "edge": "msedge", "spotify": "spotify:", "discord": "discord:",
    "steam": "steam:", "vs code": "code", "visual studio code": "code",
}

WMO = {0: "açık", 1: "çoğunlukla açık", 2: "parçalı bulutlu", 3: "kapalı", 45: "sisli", 48: "kırağılı sis",
       51: "hafif çiseleyen", 53: "çiseleyen", 55: "yoğun çiseleyen", 61: "hafif yağmurlu", 63: "yağmurlu",
       65: "şiddetli yağmurlu", 66: "dondurucu yağmurlu", 67: "dondurucu yağmurlu", 71: "hafif karlı",
       73: "karlı", 75: "yoğun karlı", 77: "kar taneli", 80: "sağanak yağışlı", 81: "sağanak yağışlı",
       82: "şiddetli sağanaklı", 85: "kar sağanaklı", 86: "yoğun kar sağanaklı", 95: "gök gürültülü fırtınalı",
       96: "dolu ile fırtınalı", 99: "dolu ile şiddetli fırtınalı"}

SUFFIX = r"(?:'?(?:y?[ıiuü]|n[ıiuü]|y[ıiuü]|[ıiuü]|da|de|ta|te|dan|den))?"


def strip_suffix(word: str) -> str:
    return re.sub(r"'\w*$", "", word).strip()


def open_url(url: str):
    webbrowser.open(url, new=2)


def run_app(cmd: str) -> bool:
    if not IS_WIN:
        return False
    try:
        if cmd.endswith(":"):
            os.startfile(cmd)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(f'start "" {cmd}', shell=True)
        return True
    except Exception:
        return False


def press(vk: int, times: int = 1):
    if not IS_WIN:
        return
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.02)


VK_MUTE, VK_DOWN, VK_UP = 0xAD, 0xAE, 0xAF
VK_NEXT, VK_PREV, VK_PLAY = 0xB0, 0xB1, 0xB3


def weather(city: str) -> str:
    try:
        g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": city, "count": 1, "language": "tr"}, timeout=10).json()
        if not g.get("results"):
            return f"{city} için konum bulamadım."
        p = g["results"][0]
        w = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
            "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto",
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max", "forecast_days": 1,
        }).json()
        c, d = w["current"], w["daily"]
        desc = WMO.get(int(c["weather_code"]), "değişken")
        rain = d.get("precipitation_probability_max", [None])[0]
        rain_txt = f" Yağış ihtimali yüzde {rain}." if rain is not None else ""
        return (f"{p['name']}'da hava {desc}, {round(c['temperature_2m'])} derece, hissedilen "
                f"{round(c['apparent_temperature'])}. Bugün en yüksek {round(d['temperature_2m_max'][0])}, "
                f"en düşük {round(d['temperature_2m_min'][0])} derece.{rain_txt}")
    except Exception:
        return "Hava durumuna şu an ulaşamadım."


def screenshot() -> str:
    try:
        from PIL import ImageGrab
        folder = Path.home() / "Pictures" / "NOVA"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"ekran_{dt.datetime.now():%Y%m%d_%H%M%S}.png"
        ImageGrab.grab(all_screens=True).save(path)
        return "Ekran görüntüsünü aldım, Resimler klasöründeki NOVA klasörüne kaydettim."
    except Exception:
        return "Ekran görüntüsü alamadım."


def grab_png(max_w: int = 1600) -> bytes | None:
    """Ekranın küçültülmüş PNG görüntüsü (beyne göstermek için)."""
    try:
        import io
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=False)
        if img.width > max_w:
            img = img.resize((max_w, int(img.height * max_w / img.width)))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def system_status() -> str:
    try:
        import psutil
        cpu = round(psutil.cpu_percent(interval=0.3))
        ram = round(psutil.virtual_memory().percent)
        txt = f"İşlemci yüzde {cpu}, bellek yüzde {ram} dolu."
        b = psutil.sensors_battery()
        if b:
            txt += f" Pil yüzde {round(b.percent)}" + (", şarjda." if b.power_plugged else ".")
        return txt
    except Exception:
        return "Sistem bilgisine ulaşamadım."


# ---------------- zamanlayıcı / hatırlatıcı ----------------
NUMS = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
        "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "doksan": 90, "yüz": 100}
UNITS = {"saniye": 1, "sn": 1, "dakika": 60, "dk": 60, "saat": 3600}
NUM_RE = r"(\d+(?:[.,]\d+)?|yarım|bir buçuk|(?:(?:on|yirmi|otuz|kırk|elli) )?(?:bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz)|on|yirmi|otuz|kırk|elli|altmış|doksan|yüz)"
DUR_RE = NUM_RE + r" ?(saniye|sn|dakika|dk|saat)(?:lık|lik)?"


def _num(word: str) -> float:
    word = word.strip()
    if word == "yarım":
        return 0.5
    if word == "bir buçuk":
        return 1.5
    try:
        return float(word.replace(",", "."))
    except ValueError:
        return float(sum(NUMS.get(w, 0) for w in word.split()))


def parse_duration(n: str) -> int | None:
    total, found = 0.0, False
    for m in re.finditer(DUR_RE, n):
        total += _num(m.group(1)) * UNITS[m.group(2)]
        found = True
    return int(total) if found and total > 0 else None


def say_duration(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    out = []
    if h:
        out.append(f"{h} saat")
    if m:
        out.append(f"{m} dakika")
    if s and not h:
        out.append(f"{s} saniye")
    return " ".join(out) or "birkaç saniye"


def timer_command(n: str):
    if re.search(r"(zamanlayıcı|hatırlatıcı|alarm|sayaç)\w* (iptal|kapat|sil|durdur)", n):
        return {"cancel_timers": True}
    if re.search(r"(zamanlayıcı|hatırlatıcı|sayaç)(lar)?(ım)? (ne durumda|kaç dakika kaldı)|ne kadar kaldı", n):
        return {"list_timers": True}
    sec = parse_duration(n)
    if not sec:
        return None
    m = re.search(DUR_RE + r" sonra (?:bana )?(.+?) ?(?:diye )?(?:hatırlat|söyle|haber ver)", n)
    if m:
        label = re.sub(r"\s*diye$", "", m.group(3).strip())
        label = re.sub(r"^(bana|beni|bunu|şunu)\b\s*", "", label)
        if label:
            return {"timer": sec, "label": label,
                    "reply": f"Tamam, {say_duration(sec)} sonra hatırlatacağım: {label}."}
        return {"timer": sec, "label": "", "reply": f"Tamam, {say_duration(sec)} sonra haber vereceğim."}
    if re.search(r"(zamanlayıcı|sayaç|alarm)|sonra (bana )?haber ver|sonra hatırlat|(geri )?say", n):
        return {"timer": sec, "label": "",
                "reply": f"{say_duration(sec)} için zamanlayıcı kurdum."}
    return None


# ---------------- notlar ----------------
def notes_path() -> Path:
    folder = Path.home() / "Documents" / "NOVA"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "notlar.txt"


def note_command(text: str, n: str):
    m = re.search(r"^(?:nova )?(?:şunu )?not (?:al|et|ekle)[:,]? (.+)$", n) or \
        re.search(r"^(?:nova )?(.+?) (?:diye )?not (?:al|et|ekle)$", n)
    if m:
        body = m.group(1).strip(" :,")
        # kullanıcının yazdığı büyük/küçük harfleri koru
        i = text.lower().find(body[:8]) if body else -1
        if i >= 0:
            body = text[i:i + len(body)] if len(text) >= i + len(body) else body
        with notes_path().open("a", encoding="utf-8") as f:
            f.write(f"[{dt.datetime.now():%d.%m.%Y %H:%M}] {body}\n")
        return "Not aldım."
    if re.search(r"notlar(ımı|ı) (oku|söyle|göster)|son not(um|lar)", n):
        p = notes_path()
        lines = [l.split("] ", 1)[-1] for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
        if not lines:
            return "Henüz hiç notun yok."
        last = lines[-5:]
        return f"Son {len(last)} notun: " + ". ".join(last) + "."
    if re.search(r"notlar(ımı|ı) (aç|klasörünü aç)", n):
        p = notes_path()
        p.touch(exist_ok=True)
        if IS_WIN:
            os.startfile(str(p))  # type: ignore[attr-defined]
        return "Not dosyanı açtım."
    if re.search(r"notlar(ımı|ı) (sil|temizle)", n):
        notes_path().write_text("", encoding="utf-8")
        return "Tüm notlarını sildim."
    return None


VISION_RE = r"ekran(a|ıma|da|ımda|daki|ımdaki) (bak|ne var|neler var|ne görüyorsun|ne yazıyor)|ekranı (açıkla|oku|yorumla|incele)|ekranımı (açıkla|oku|yorumla|incele)|bu ekranda ne"


# ---------------- 1.3: haber, takvim, harita, döviz, alarm, panel ----------------
NEWS_WORDS = {"son dakika": "sondakika", "ekonomi": "ekonomi", "spor": "spor", "teknoloji": "teknoloji",
              "dünya": "dunya", "gündem": "gundem"}
PANEL_WORDS = {"haber": "news", "takvim": "calendar", "harita": "map", "zamanlayıcı": "timers",
               "not": "notes", "hava": "weather", "döviz": "rates", "komut": "help"}


# ---------------- müzik ----------------
def play_music(query: str, source: str) -> str:
    from .widgets import youtube_first
    q = query.strip() or "popüler türkçe şarkılar"
    nice = " ".join(w[:1].upper() + w[1:] for w in q.split())
    if source == "spotify":
        uri = "spotify:search:" + urllib.parse.quote(q)
        if IS_WIN:
            try:
                os.startfile(uri)  # type: ignore[attr-defined]
                return f"Spotify'da {nice} aramasını açtım. Listeden seçip çalabilirsin."
            except OSError:
                pass
        open_url("https://open.spotify.com/search/" + urllib.parse.quote(q))
        return f"Spotify'da {nice} aramasını açtım."
    vid = youtube_first(q)
    if vid:
        base = "https://music.youtube.com/watch?v=" if source == "ytmusic" else "https://www.youtube.com/watch?v="
        open_url(base + vid + "&autoplay=1")
        return f"{nice} çalıyor."
    open_url("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
    return f"YouTube'da {q} için sonuçları açtım."


def music_command(text: str, n: str, settings):
    src = settings.get("music_source") or "youtube"
    m = re.search(r"spotify'?(?:da|dan|de|den)? (.+?) (?:şarkısını |şarkısı |listesini )?(aç|çal|oynat|dinle)$", n) or \
        re.search(r"^(.+?) (?:şarkısını |şarkısı )?spotify'?(?:da|dan|de|den) (aç|çal|oynat)$", n)
    if m:
        return play_music(m.group(1), "spotify")
    m = re.search(r"youtube m[uü]zik'?(?:te|ten|de|den)? (.+?) (aç|çal|oynat)$", n)
    if m:
        return play_music(m.group(1), "ytmusic")
    m = re.search(r"youtube'?(?:da|dan|ta|tan|de|den)? (.+?) (?:videosunu |şarkısını )?(aç|çal|oynat|izle)$", n) or \
        re.search(r"^(.+?) (?:videosunu |şarkısını )?youtube'?(?:da|dan|ta|tan|de|den) (aç|çal|oynat)$", n)
    if m:
        return play_music(m.group(1), "youtube" if src != "ytmusic" else "ytmusic")
    if re.search(r"^(?:biraz |bana )?(?:müzik|şarkı) (aç|çal|koy)$", n):
        return play_music("", src)
    m = re.search(r"^(.+?) (?:şarkısını |şarkısı |müziği |müziğini |albümünü |çalma listesini )?(çal|oynat)$", n) or \
        re.search(r"^(.+?) (?:şarkısını|şarkısı|müziğini|albümünü) (aç|dinle)$", n) or \
        re.search(r"^(.+?) dinlemek istiyorum$", n)
    if m and not re.search(r"\b(alarm|zil|telefon)", m.group(1)):
        q = re.sub(r"^(bana |bir |biraz )+", "", m.group(1))
        return play_music(q, src)
    return None


def extra_command(text: str, n: str):
    # haberler
    if re.search(r"\bhaber", n) and not re.search(r"haber ver", n):
        cat = next((v for k, v in NEWS_WORDS.items() if k in n), "gundem")
        read = bool(re.search(r"oku|söyle|neler|ne var|anlat|nedir|başlık", n))
        return {"news": cat, "read": read}
    # takvim: ekle / listele
    if re.search(r"takvim(e|ime)|randevu|etkinlik", n) and re.search(r"ekle|kaydet|koy|oluştur|yaz", n):
        return {"calendar_add": text}
    if re.search(r"(takvim(de|imde)|programım|planım|ajandam)", n) or \
            re.search(r"(bugün|yarın)(ki)? (neler var|ne var|programım|planım)", n):
        return {"calendar_list": "yarın" if "yarın" in n else "bugün"}
    # belirli saate alarm / hatırlatma
    m = re.search(r"saat (\d{1,2})(?:[:.](\d{2}))?'?(?:de|da|te|ta)? (?:bana |beni )?(.*?)\s*(?:diye )?(uyandır|hatırlat|alarm kur|haber ver|söyle)", n)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        label = re.sub(r"^(bana|beni)\s*", "", m.group(3) or "").strip()
        if m.group(4) == "uyandır" and not label:
            label = "Uyanma vakti"
        if 0 <= h < 24 and 0 <= mi < 60:
            return {"alarm_at": f"{h:02d}:{mi:02d}", "label": label}
    # harita / yol tarifi
    m = re.search(r"(.+?)'?(?:y?[ae]|n[ae])? (?:nasıl giderim|yol tarifi|yol tarifini?)", n)
    if m:
        return {"directions": m.group(1).strip()}
    m = re.search(r"harita(da|ya)? (.+?)'?(?:y[ıiuü]|[ıiuü]|n[ıiuü])? (göster|aç|bul)$", n) or \
        re.search(r"^(.+?) (nerede|haritada göster)$", n)
    if m:
        place = m.group(2) if m.re.pattern.startswith("harita") else m.group(1)
        place = re.sub(r"'.*$", "", place).strip()
        return {"map": place}
    # döviz / altın
    if re.search(r"\b(dolar|euro|avro|sterlin|altın|döviz|kur(lar)?)\b", n) and \
            re.search(r"kaç|ne kadar|fiyat|kuru|kurlar|durum|göster", n):
        which = next((w for w in ("dolar", "euro", "avro", "sterlin", "altın") if w in n), None)
        return {"rates": which}
    # güncelleme
    if re.search(r"güncelleme(leri|yi)? (kontrol|denetle|var mı|bak)|güncelle(me)? var mı|kendini güncelle", n):
        return {"update_check": True}
    # bilgisayarı kilitle
    if re.search(r"(bilgisayarı|ekranı) kilitle", n):
        if IS_WIN:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        return "Bilgisayarı kilitliyorum."
    # panel aç
    m = re.search(r"(haber|takvim|harita|zamanlayıcı|not|hava|döviz|komut)\w* (panelini |sekmesini )?(aç|göster)$", n)
    if m:
        return {"panel": PANEL_WORDS[m.group(1)]}
    return None


def handle(text: str, settings):
    """Yanıt metni, özel istek sözlüğü (zamanlayıcı/ekran) ya da None (beyin yanıtlasın)."""
    n = norm(text)
    now = dt.datetime.now()

    # --- müzik (YouTube / YouTube Music / Spotify) ---
    r = music_command(text, n, settings)
    if r:
        return r

    # --- ekranı görme (beyne ekran görüntüsüyle sorulur) ---
    if re.search(VISION_RE, n):
        return {"vision": text}

    # --- 1.3 komutları ---
    r = extra_command(text, n)
    if r:
        return r

    # --- zamanlayıcı / hatırlatıcı / not ---
    r = timer_command(n)
    if r:
        return r
    r = note_command(text, n)
    if r:
        return r

    # --- saat / tarih ---
    if re.search(r"\bsaat kaç\b|\bsaati söyle", n):
        return f"Saat {now:%H:%M}."
    if re.search(r"bugün (günlerden ne|ayın kaçı|ne günü)|tarih(i)? (ne|söyle)|bugünün tarihi", n):
        return f"Bugün {now.day} {MONTHS[now.month - 1]} {now.year}, {DAYS[now.weekday()]}."

    # --- ses ---
    if re.search(r"\bses(i)? (kapat|sustur)\b|\bsessize al", n):
        press(VK_MUTE); return "Sesi kapattım."
    if re.search(r"\bses(i)? (aç|yükselt|arttır|artır)|sesi biraz aç", n):
        press(VK_UP, 5); return "Sesi açtım."
    if re.search(r"\bses(i)? (kıs|azalt|düşür)", n):
        press(VK_DOWN, 5); return "Sesi kıstım."

    # --- medya ---
    if re.search(r"^(müziği |şarkıyı |videoyu |medyayı )?(durdur|duraklat|devam et|devam ettir|oynat)$", n):
        press(VK_PLAY); return "Tamam."
    if re.search(r"(sonraki|diğer) (şarkı|parça)|şarkıyı (geç|değiştir)", n):
        press(VK_NEXT); return "Sonraki parça."
    if re.search(r"önceki (şarkı|parça)", n):
        press(VK_PREV); return "Önceki parça."

    # --- hava ---
    if "hava" in n and re.search(r"hava (durumu|nasıl|kaç derece)|derece", n):
        m = re.search(r"([a-zçğıöşü]+)(?:'?(?:da|de|ta|te|nın|nin|daki|deki))? hava", n)
        city = settings.get("city") or "İstanbul"
        if m and m.group(1) not in ("bugün", "yarın", "şu", "an", "dışarıda", "dışarda", "acaba"):
            city = strip_suffix(m.group(1))
            city = re.sub(r"(da|de|ta|te)$", "", city) if len(city) > 4 else city
        return weather(city)

    # --- ekran / sistem ---
    if re.search(r"ekran (görüntüsü|resmi)", n):
        return screenshot()
    if re.search(r"sistem (durumu|bilgisi)|pil (durumu|kaç)|şarj kaç", n):
        return system_status()

    # --- YouTube'da aç/çal ---
    m = re.search(r"youtube'?(?:da|ta|de)? (.+?) (aç|çal|oynat|ara|bul)$", n)
    if m:
        q = m.group(1)
        open_url("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
        return f"YouTube'da {q} için sonuçları açtım."

    # --- Google'da ara ---
    m = re.search(r"(?:google'?(?:da|de)? |internette )(.+?) (ara|araştır|bul)$", n) or \
        re.search(r"^(.+?)'?(?:y[ıiuü]|[ıiuü]|n[ıiuü])? ara$", n)
    if m:
        q = m.group(1)
        open_url("https://www.google.com/search?q=" + urllib.parse.quote(q))
        return f"{q} için arama yaptım."

    # --- aç ---
    m = re.search(r"^(.+?) (aç|başlat|çalıştır)$", n)
    if m and not re.search(r"\bses|ışık|kapı|pencere", m.group(1)):
        target = m.group(1).strip()
        target = re.sub(r"^(bana |bir |lütfen )+", "", target)
        base = strip_suffix(target)
        base_nosuf = re.sub(r"(y?[ıiuü]|n[ıiuü])$", "", base) if base not in SITES and base not in APPS else base
        for key in (target, base, base_nosuf):
            if key in APPS and run_app(APPS[key]):
                return f"{key.capitalize()} açılıyor."
        for key in (target, base, base_nosuf):
            if key in SITES:
                open_url(SITES[key]); return f"{key.capitalize()} açılıyor."
        for key in (target, base, base_nosuf):
            if key in APPS:
                return f"{key.capitalize()} bu bilgisayarda açılamadı."
        if re.match(r"^[\w.-]+\.(com|net|org|io|dev|tr|com\.tr|app)$", base):
            open_url("https://" + base); return f"{base} açılıyor."
        exe = base_nosuf.replace(" ", "")
        if IS_WIN and shutil.which(exe) and run_app(exe):
            return f"{base_nosuf.capitalize()} açılıyor."
    return None
