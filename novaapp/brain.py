"""NOVA'nın beyni: Google Gemini, OpenAI ChatGPT ya da kendi yapay zekan (OpenAI uyumlu API).

Yalnızca REST kullanılır; ek SDK gerekmez. Görsel (ekran) anlama da desteklenir.
"""

import base64
import datetime as dt
import logging
import re

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
TIMEOUT = 60
MAX_TURNS = 12
NAMES = {"gemini": "Gemini", "openai": "ChatGPT", "custom": "Kendi yapay zekan"}

log = logging.getLogger("nova.brain")

DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
          "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


class BrainError(Exception):
    pass


class ModelGone(Exception):
    """Google eski modeli kapattı; hata mesajında yeni model önerildi."""

    def __init__(self, new_model):
        super().__init__(new_model)
        self.new_model = new_model


DEFAULT_GEMINI = "gemini-3.8-flash"


def turkish_now():
    n = dt.datetime.now()
    return f"{n.day} {MONTHS[n.month - 1]} {n.year} {DAYS[n.weekday()]}, saat {n:%H:%M}"


def speakable(text: str) -> str:
    """Markdown işaretlerini temizler; seslendirmeye uygun düz metin."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"<think>.*?</think>", " ", t, flags=re.S)        # bazı yerel modellerin düşünce bloğu
    t = re.sub(r"[*_#`>|]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+\n", "\n", t)
    return t.strip()


class Brain:
    def __init__(self, settings):
        self.s = settings
        self.history = []  # [(role, text)] role: "user" | "assistant"

    # ---------- ortak ----------
    def system_prompt(self):
        name = self.s.get("user_name") or ""
        who = f"Kullanıcının adı {name}. " if name else ""
        return (
            "Sen NOVA'sın: Samet Şahin'in tasarlayıp geliştirdiği kişisel, sesli bir masaüstü asistanısın. "
            "Seni kim yaptı diye sorulursa 'Beni Samet Şahin geliştirdi' de. "
            f"{who}Şu an: {turkish_now()}. "
            "Yanıtların sesli okunacak: kısa, doğal ve sıcak konuş; genelde 1-3 cümle. "
            "Kullanıcı ayrıntı isterse daha uzun anlatabilirsin. "
            "Madde işareti, başlık, emoji ya da markdown kullanma. "
            "Kullanıcı hangi dilde konuşursa o dilde yanıt ver, varsayılan Türkçe. "
            "Uygulama/site açma, ses, müzik, hava durumu, zamanlayıcı, not ve ekran görüntüsü gibi "
            "bilgisayar komutlarını NOVA kendisi uygular; senden yalnızca sohbet ve bilgi isteniyor."
        )

    def reset(self):
        self.history.clear()

    def available(self):
        """Kullanılabilir beyinler; seçili olan önce."""
        have = []
        if self.s.get("gemini_key"):
            have.append("gemini")
        if self.s.get("openai_key"):
            have.append("openai")
        # Kendi yapay zekan: seçiliyse önce; seçili değilse yerel sunucu (Ollama) yedek olarak denenir
        url = (self.s.get("custom_url") or "").strip()
        if url and self.s.get("custom_model") and (self.s.get("provider") == "custom" or _is_local(url)):
            have.append("custom")
        chosen = self.s.get("provider")
        return sorted(have, key=lambda p: p != chosen)

    def ready(self):
        return bool(self.available())

    def ask(self, text: str, image_png: bytes | None = None) -> str:
        order = self.available()
        if not order:
            raise BrainError("Beyin ayarlanmamış. Ayarlar'dan Gemini, ChatGPT ya da kendi yapay zekanı bağla.")
        last, errors = None, []
        for p in order:
            try:
                if p == "gemini":
                    reply = self._gemini(text, image_png)
                elif p == "openai":
                    reply = self._chat(OPENAI_URL, self.s.get("openai_key"),
                                       self.s.get("openai_model") or "gpt-4o-mini", text, image_png, "ChatGPT")
                else:
                    url = self.s.get("custom_url").rstrip("/") + "/chat/completions"
                    reply = self._chat(url, self.s.get("custom_key"), self.s.get("custom_model"),
                                       text, image_png, "Kendi yapay zekan")
                reply = speakable(reply) or "Bunu yanıtlayamadım, bir daha söyler misin?"
                self.history.append(("user", text if image_png is None else f"[ekran görüntüsü] {text}"))
                self.history.append(("assistant", reply))
                self.history = self.history[-MAX_TURNS * 2:]
                return reply
            except BrainError as e:
                log.warning("%s çalışmadı: %s", NAMES[p], e)
                last = e
                errors.append(e)
        raise errors[0] if errors else last

    # ---------- Gemini ----------
    def _gemini(self, text, image_png=None):
        contents = [{"role": "user" if r == "user" else "model", "parts": [{"text": t}]}
                    for r, t in self.history]
        parts = [{"text": text}]
        if image_png:
            parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image_png).decode()}})
        contents.append({"role": "user", "parts": parts})
        body = {
            "systemInstruction": {"parts": [{"text": self.system_prompt()}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 900},
        }
        if self.s.get("web_search") and not image_png:
            body["tools"] = [{"google_search": {}}]
        data = None
        for _ in range(3):
            model = self.s.get("gemini_model") or DEFAULT_GEMINI
            body["generationConfig"].pop("thinkingConfig", None)
            if "2.5-flash" in model:
                body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}  # hız için
            try:
                data = self._gemini_post(model, body)
            except ModelGone as e:                    # eski model kapatıldı → önerilen modele geç
                log.warning("Gemini modeli %s kapatılmış, %s modeline geçiliyor", model, e.new_model)
                self.s.update({"gemini_model": e.new_model})
                continue
            if data is None and "tools" in body:      # arama aracı desteklenmiyorsa aramasız dene
                body.pop("tools")
                continue
            break
        if data is None:
            raise BrainError("Gemini isteği başarısız oldu.")
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError):
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise BrainError("Gemini bu isteğe yanıt vermedi." if reason else "Gemini boş yanıt döndü.")

    def _gemini_post(self, model, body):
        try:
            r = requests.post(GEMINI_URL.format(model=model), json=body, timeout=TIMEOUT,
                              headers={"x-goog-api-key": self.s.get("gemini_key")})
        except requests.RequestException:
            raise BrainError("İnternete ulaşamadım. Bağlantını kontrol eder misin?")
        if r.status_code == 200:
            return r.json()
        if r.status_code in (400, 429) and "tools" in body:
            # Google Arama aracının ayrı (ve çoğu zaman daha düşük) kotası var: aramasız dene
            log.warning("Gemini %s (arama aracıyla); aramasız deneniyor", r.status_code)
            return None
        if r.status_code == 404:
            m = re.search(r"use models/([\w.\-]+)", r.text)
            if m and m.group(1) != model:
                raise ModelGone(m.group(1))
        log.warning("Gemini %s: %s", r.status_code, r.text[:1500])
        raise BrainError(_http_message("Gemini", r))

    # ---------- OpenAI ve OpenAI uyumlu (kendi yapay zekan) ----------
    def _chat(self, url, key, model, text, image_png, name):
        msgs = [{"role": "system", "content": self.system_prompt()}]
        msgs += [{"role": r, "content": t} for r, t in self.history]
        if image_png:
            data_url = "data:image/png;base64," + base64.b64encode(image_png).decode()
            msgs.append({"role": "user", "content": [{"type": "text", "text": text},
                                                     {"type": "image_url", "image_url": {"url": data_url}}]})
        else:
            msgs.append({"role": "user", "content": text})
        body = {"model": model, "messages": msgs}
        if url == OPENAI_URL:
            body["max_completion_tokens"] = 900
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            r = requests.post(url, json=body, timeout=(4, 120) if url != OPENAI_URL else TIMEOUT, headers=headers)
            if r.status_code == 404 and url != OPENAI_URL:
                better = self._ollama_pick(model)     # model adı yanlışsa kurulu olanı bul
                if better and better != model:
                    log.info("Yerel model %s yerine %s kullanılıyor", model, better)
                    self.s.update({"custom_model": better})
                    body["model"] = better
                    r = requests.post(url, json=body, timeout=(4, 120), headers=headers)
        except requests.RequestException:
            if url == OPENAI_URL:
                raise BrainError("İnternete ulaşamadım. Bağlantını kontrol eder misin?")
            raise BrainError(f"{name} sunucusuna ulaşamadım ({self.s.get('custom_url')}). Ollama açık mı?")
        if r.status_code != 200:
            log.warning("%s %s: %s", name, r.status_code, r.text[:300])
            raise BrainError(_http_message(name, r))
        try:
            return (r.json()["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, ValueError):
            raise BrainError(f"{name} boş yanıt döndü.")

    def _ollama_pick(self, wanted):
        """Ollama'da kurulu modellerden istenene en yakınını seç."""
        base = re.sub(r"/v1/?$", "", (self.s.get("custom_url") or "").rstrip("/"))
        try:
            names = [m["name"] for m in requests.get(base + "/api/tags", timeout=4).json().get("models", [])]
        except Exception:
            return None
        if not names:
            return None
        root = (wanted or "").split(":")[0]
        return next((n for n in names if n == wanted), None) or \
            next((n for n in names if n.split(":")[0] == root), None) or names[0]

    # ---------- konuşmayı yazıya çevirme (yedekler) ----------
    def transcribe(self, wav_bytes: bytes) -> str:
        key = self.s.get("gemini_key")
        if not key:
            return ""
        body = {"contents": [{"role": "user", "parts": [
            {"text": "Bu ses kaydındaki konuşmayı olduğu gibi yazıya dök. Yalnızca metni yaz. "
                     "Anlaşılır konuşma yoksa hiçbir şey yazma."},
            {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(wav_bytes).decode()}},
        ]}], "generationConfig": {"temperature": 0}}
        model = self.s.get("gemini_model") or DEFAULT_GEMINI
        if "2.5-flash" in model:
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        try:
            r = requests.post(GEMINI_URL.format(model=model), json=body, timeout=TIMEOUT,
                              headers={"x-goog-api-key": key})
            parts = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except Exception:
            return ""

    def transcribe_openai(self, wav_bytes: bytes) -> str:
        key = self.s.get("openai_key")
        if not key:
            return ""
        lang = (self.s.get("language") or "tr-TR").split("-")[0]
        r = requests.post("https://api.openai.com/v1/audio/transcriptions", timeout=TIMEOUT,
                          headers={"Authorization": f"Bearer {key}"},
                          files={"file": ("ses.wav", wav_bytes, "audio/wav")},
                          data={"model": "whisper-1", "language": lang})
        if r.status_code != 200:
            return ""
        return (r.json().get("text") or "").strip()

    def transcribers(self):
        order = [self.transcribe, self.transcribe_openai]
        return order[::-1] if self.s.get("provider") == "openai" else order


def _is_local(url: str) -> bool:
    return bool(re.match(r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(/|$)", url))


def _http_message(name, r):
    if r.status_code in (401, 403):
        return f"{name} API anahtarı geçersiz görünüyor. Ayarlar'dan kontrol eder misin?"
    if r.status_code == 429:
        if "quota" in r.text.lower() and "billing" in r.text.lower():
            return (f"{name} anahtarının kotası doldu. Kota yenilenene kadar Ayarlar'dan ChatGPT'yi "
                    "ya da 'Kendi YZ'm' (bilgisayarındaki Ollama) seçeneğini kullanabilirsin.")
        return f"{name} çok hızlı istek aldı. Birkaç saniye sonra tekrar dene."
    if r.status_code == 404:
        return f"{name} modeli bulunamadı. Ayarlar'dan model adını değiştir."
    if r.status_code >= 500:
        return f"{name} şu an yanıt veremiyor (sunucu hatası). Biraz sonra tekrar dene."
    return f"{name} hata verdi (kod {r.status_code})."
