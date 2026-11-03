"""Akıllı ev: Şımart (Tuya/ThingClips altyapılı) cihazlar — ilk olarak Katya T robot süpürge.

Şımart uygulaması (com.lemo.simarttest) Tuya'nın OEM SDK'sıyla yapılmıştır; cihazlar Tuya bulutundadır.
Şımart hesabı dış erişim vermediği için cihaz Smart Life'a taşınır ve aşağıdaki resmî API kullanılır.

Bağlantı Tuya'nın resmî bulut API'si (iot.tuya.com) ile yapılır. Kurulum bir kez:
  1. iot.tuya.com'da ücretsiz hesap aç → Cloud → Create Cloud Project
     (Industry: Smart Home, Data Center: Central Europe).
  2. Projenin Overview sayfasındaki Access ID ve Access Secret'ı NOVA'ya gir.
  3. Devices → Link App Account → QR kodu Smart Life / Tuya uygulamasıyla okut.
  4. Süpürgenin Cihaz Kimliğini (uygulamada cihaz → ✎ → Cihaz Bilgisi → Sanal Kimlik) NOVA'ya gir.
Komutlar Tuya'nın standart robot süpürge talimat setiyle gönderilir; cihazın desteklediği
komutlar otomatik okunur, desteklenmeyenler atlanır.
"""

import logging
import threading
import time

log = logging.getLogger("nova.ev")

REGIONS = {"eu": "Avrupa (Türkiye)", "us": "Amerika", "cn": "Çin", "in": "Hindistan", "sg": "Singapur"}

STATUS_TR = {
    "standby": "beklemede", "smart_clean": "temizlik yapıyor", "smart": "temizlik yapıyor",
    "cleaning": "temizlik yapıyor", "zone_clean": "bölge temizliği yapıyor", "part_clean": "nokta temizliği yapıyor",
    "wall_clean": "kenar temizliği yapıyor", "spiral": "spiral temizlik yapıyor", "mop_clean": "paspas yapıyor",
    "paused": "duraklatıldı", "pause": "duraklatıldı", "goto_charge": "şarj istasyonuna dönüyor",
    "go_charging": "şarj istasyonuna dönüyor", "charging": "şarj oluyor", "charge_done": "şarjı dolu",
    "chargecompleted": "şarjı dolu", "sleep": "uykuda", "fault": "arıza veriyor", "dormant": "uykuda",
    "self_clean": "kendini temizliyor", "dust_collecting": "toz topluyor", "repositing": "konum buluyor",
    "remote_control": "uzaktan kumandayla sürülüyor", "mapping": "harita çıkarıyor",
}
SUCTION_TR = {"closed": "kapalı", "gentle": "sessiz", "quiet": "sessiz", "normal": "normal", "standard": "normal",
              "strong": "güçlü", "max": "maksimum", "turbo": "maksimum"}


class TuyaVacuum:
    def __init__(self, settings):
        self.s = settings
        self._cloud = None
        self._funcs = None
        self._lock = threading.Lock()

    # ---------- bağlantı ----------
    def configured(self):
        return all(self.s.get(k) for k in ("tuya_key", "tuya_secret", "tuya_device"))

    def reset(self):
        self._cloud, self._funcs = None, None

    def cloud(self):
        if self._cloud is None:
            import tinytuya
            try:
                self._cloud = tinytuya.Cloud(apiRegion=self.s.get("tuya_region") or "eu",
                                         apiKey=self.s.get("tuya_key").strip(),
                                         apiSecret=self.s.get("tuya_secret").strip(),
                                         apiDeviceID=self.s.get("tuya_device").strip(),
                                         configFile=None)
            except Exception as e:
                log.warning("Tuya bağlantı hatası: %s", e)
                raise RuntimeError("Tuya bulutuna bağlanılamadı. İnternet bağlantını kontrol et.")
            err = getattr(self._cloud, "error", None)
            if err:
                self._cloud = None
                raise RuntimeError(_err_text(err))
        return self._cloud

    @property
    def dev(self):
        return (self.s.get("tuya_device") or "").strip()

    def functions(self):
        if self._funcs is None:
            r = self.cloud().getfunctions(self.dev)
            self._check(r)
            self._funcs = {f["code"]: f for f in (r.get("result") or {}).get("functions", [])}
            log.info("Süpürge komutları: %s", ", ".join(self._funcs))
        return self._funcs

    def _check(self, r):
        if not isinstance(r, dict):
            raise RuntimeError("Tuya'dan yanıt alınamadı.")
        if r.get("success") is False or r.get("Error"):
            raise RuntimeError(_err_text(r))

    def devices(self):
        """Hesaba bağlı tüm Tuya cihazları (kurulumda süpürgeyi seçmek için)."""
        out = self.cloud().getdevices(verbose=False)
        if isinstance(out, dict) and (out.get("Error") or out.get("success") is False):
            raise RuntimeError(_err_text(out))
        return [{"id": d.get("id"), "name": d.get("name"), "category": d.get("category", ""),
                 "online": d.get("online")} for d in (out or [])]

    # ---------- durum ----------
    def status(self):
        r = self.cloud().getstatus(self.dev)
        self._check(r)
        st = {x["code"]: x["value"] for x in r.get("result", [])}
        battery = next((st[k] for k in ("electricity_left", "battery_percentage", "residual_electricity", "battery")
                        if k in st), None)
        raw = st.get("status") or st.get("work_status") or st.get("mode")
        return {"battery": battery, "status": raw, "status_tr": STATUS_TR.get(str(raw), str(raw or "bilinmiyor")),
                "suction": st.get("suction"), "suction_tr": SUCTION_TR.get(str(st.get("suction")), st.get("suction")),
                "fault": st.get("fault"), "clean_area": st.get("clean_area"), "clean_time": st.get("clean_time"),
                "raw": st}

    # ---------- komutlar ----------
    def _send(self, commands):
        with self._lock:
            r = self.cloud().sendcommand(self.dev, {"commands": commands})
        self._check(r)
        log.info("Süpürge komutu: %s", commands)
        return True

    def _has(self, code):
        return code in self.functions()

    def _enum(self, code, *prefer):
        f = self.functions().get(code)
        if not f:
            return None
        import json
        try:
            rng = json.loads(f.get("values") or "{}").get("range", [])
        except ValueError:
            rng = []
        return next((p for p in prefer if p in rng), rng[0] if rng else None)

    def start(self):
        if self._has("power_go"):
            return self._send([{"code": "power_go", "value": True}])
        mode = self._enum("mode", "smart", "auto", "random")
        if mode:
            return self._send([{"code": "mode", "value": mode}])
        if self._has("switch_go"):
            return self._send([{"code": "switch_go", "value": True}])
        raise RuntimeError("Süpürge başlat komutunu desteklemiyor.")

    def pause(self):
        if self._has("pause"):
            return self._send([{"code": "pause", "value": True}])
        if self._has("power_go"):
            return self._send([{"code": "power_go", "value": False}])
        if self._has("switch_go"):
            return self._send([{"code": "switch_go", "value": False}])
        raise RuntimeError("Süpürge duraklat komutunu desteklemiyor.")

    def dock(self):
        if self._has("switch_charge"):
            return self._send([{"code": "switch_charge", "value": True}])
        mode = self._enum("mode", "chargego", "charge", "goto_charge")
        if mode and mode.startswith("charge") or mode == "goto_charge":
            return self._send([{"code": "mode", "value": mode}])
        raise RuntimeError("Süpürge şarja dönme komutunu desteklemiyor.")

    def seek(self):
        if self._has("seek"):
            return self._send([{"code": "seek", "value": True}])
        raise RuntimeError("Süpürgede 'beni bul' sesi yok.")

    def suction(self, level):
        want = {"sessiz": ("gentle", "quiet", "closed"), "normal": ("normal", "standard"),
                "güçlü": ("strong",), "maksimum": ("max", "turbo", "strong")}.get(level, ("normal",))
        val = self._enum("suction", *want)
        if not val:
            raise RuntimeError("Süpürgenin emiş gücü ayarlanamıyor.")
        self._send([{"code": "suction", "value": val}])
        return SUCTION_TR.get(val, val)

    def mode(self, name):
        val = self._enum("mode", *{"kenar": ("wall_follow", "edge"), "spiral": ("spiral", "part"),
                                   "paspas": ("mop",), "nokta": ("part", "spot", "pose")}.get(name, ()))
        if not val:
            raise RuntimeError(f"Süpürge {name} modunu desteklemiyor.")
        return self._send([{"code": "mode", "value": val}])


def _err_text(r):
    msg = str(r.get("msg") or r.get("Error") or r.get("Payload") or r) if isinstance(r, dict) else str(r)
    low = msg.lower()
    if "sign invalid" in low or "secret" in low or "1004" in msg:
        return "Access ID ya da Secret hatalı (iot.tuya.com proje sayfasındakileri yapıştır)."
    if "permission deny" in low or "1106" in msg:
        return ("Tuya izin vermedi. iot.tuya.com'da Smart Life hesabını projeye bağladığından (Link App Account) "
                "ve veri merkezinin Avrupa olduğundan emin ol.")
    if "28841105" in msg or "expire" in low:
        return "Tuya bulut deneme süresi dolmuş. iot.tuya.com → Cloud → Cloud Services'ten IoT Core'u ücretsiz uzat."
    if "device" in low and ("not exist" in low or "1007" in msg or "2009" in msg):
        return "Bu cihaz kimliği hesabında bulunamadı. Cihaz kimliğini kontrol et."
    return f"Tuya hatası: {msg[:160]}"


def lan_scan(seconds=8):
    """Aynı Wi-Fi'daki Tuya cihazlarını bul (cihazların yayınladığı keşif paketlerini dinler; hiçbir şeyi değiştirmez)."""
    import tinytuya
    try:
        found = tinytuya.deviceScan(verbose=False, maxretry=seconds, color=False, poll=False)
    except Exception as e:
        log.warning("Ağ taraması hatası: %s", e)
        return {"ok": False, "error": str(e), "devices": []}
    devs = [{"ip": ip, "id": d.get("gwId") or d.get("id"), "version": d.get("version"),
             "product": d.get("productKey")} for ip, d in (found or {}).items()]
    return {"ok": True, "devices": devs}


# ---------------- sesli komutlar ----------------
import re  # noqa: E402

VAC_RE = r"süpürge|robot|katya"


def intent(n: str):
    if not re.search(VAC_RE, n):
        return None
    if re.search(r"şarj(a|ına)? (dön|git|gönder)|eve (dön|git|gönder)|istasyon(a|una) (dön|git)|üsse dön", n):
        return ("dock", None)
    if re.search(r"durdur|duraklat|dur\b|bekle|kapat", n):
        return ("pause", None)
    if re.search(r"nerede|bul\b|ses(ini)? (ver|çıkar)|öttür", n):
        return ("seek", None)
    m = re.search(r"(sessiz|normal|güçlü|maksimum|en yüksek|en güçlü|tam güç|yüksek|düşük)", n)
    if m and re.search(r"emiş|güç|mod|ayarla|yap|çek", n):
        lvl = {"en yüksek": "maksimum", "en güçlü": "maksimum", "tam güç": "maksimum", "yüksek": "güçlü",
               "düşük": "sessiz"}.get(m.group(1), m.group(1))
        return ("suction", lvl)
    m = re.search(r"(kenar|spiral|paspas|nokta)", n)
    if m and re.search(r"mod|temizle|yap|başlat", n):
        return ("mode", m.group(1))
    if re.search(r"şarj(ı)? kaç|pil(i)? kaç|batarya|ne durumda|durumu|ne yapıyor|neredesin", n):
        return ("status", None)
    if re.search(r"başlat|başla|çalıştır|\bsüpür\b|süpürsün|temizle|temizliğe|\bçalış|\baç\b", n):
        return ("start", None)
    return None
