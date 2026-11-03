"""NOVA — Samet Şahin'in kişisel masaüstü asistanı.

Çalıştırma:  python main.py
Arayüz web/ klasöründe (HTML/CSS/JS). Yerel bir sunucu üzerinden Microsoft Edge'in
uygulama penceresinde açılır (novaapp/server.py).
"""

import base64
import json
import os
import queue
import re
import sys
import threading
import logging
import time
import webbrowser

from novaapp import log as nova_log  # noqa: E402

LOG_PATH = nova_log.setup(debug=True)
log = logging.getLogger("nova")

from novaapp import APP_NAME, VERSION  # noqa: E402
from novaapp import commands, tts  # noqa: E402
from novaapp.about import build as build_about  # noqa: E402
from novaapp.brain import Brain, BrainError  # noqa: E402
from novaapp.config import Settings, resource  # noqa: E402
from novaapp.listener import Listener, recognize  # noqa: E402
from novaapp import server as ui  # noqa: E402
from novaapp import updater, widgets  # noqa: E402
from novaapp import chips  # noqa: E402
from novaapp import social  # noqa: E402
from novaapp import extras, tv  # noqa: E402
import datetime as dt  # noqa: E402


class Nova:
    def __init__(self):
        self.settings = Settings()
        self.brain = Brain(self.settings)
        self.ui = None          # UIServer
        self.browser = None     # pencere işlemi
        self.quit_event = threading.Event()
        self.awake = True
        self.state = "idle"
        self.jobs = queue.Queue()
        self.speaking = threading.Event()
        self.busy = threading.Event()
        self._interrupted = False
        self.pending = None      # onay bekleyen mesaj
        self.timers = {}
        self.calendar = widgets.Calendar()
        self.update_info = None
        self._timer_seq = 0
        self.listener = Listener(self._on_utterance, self._on_level, self._on_mic_error,
                                 sensitivity=lambda: self.settings.get("sensitivity"))
        threading.Thread(target=self._worker, daemon=True, name="nova-worker").start()

    # ---------------- arayüze olay gönder ----------------
    def emit(self, event_type, **data):
        if not self.ui:
            return
        data["type"] = event_type
        self.ui.hub.send(data)

    def set_state(self, state, label=None):
        self.state = state
        self.emit("state", state=state, label=label, awake=self.awake,
                  mic=self.listener.enabled.is_set())

    def idle_state(self):
        if not self.awake:
            self.set_state("sleeping")
        elif self.listener.enabled.is_set():
            self.set_state("listening")
        else:
            self.set_state("idle")

    # ---------------- başlangıç ----------------
    def start(self):
        self.listener.start()
        if self.settings.get("continuous"):
            self.listener.enabled.set()
        threading.Thread(target=self._stats_loop, daemon=True).start()
        threading.Thread(target=self._calendar_loop, daemon=True, name="nova-takvim").start()
        threading.Thread(target=self._update_check, daemon=True, name="nova-guncelleme").start()
        time.sleep(0.4)
        name = self.settings.get("user_name")
        chip = chips.get(self.settings)
        if not self.brain.ready():
            self.emit("needs_setup")
            self.say(f"Merhaba{' ' + name if name else ''}, ben {chip['name']}. Başlamak için ayarlardan "
                     "bir beyin seçmen yeterli.")
        else:
            self.say(f"Merhaba{' ' + name if name else ''}. {chip['greeting']}")

    # ---------------- ses girişi ----------------
    def _on_level(self, level):
        self.emit("level", value=round(level, 3))

    def _on_mic_error(self, msg):
        self.emit("toast", text=msg, kind="error")

    def _on_utterance(self, pcm):
        if self.speaking.is_set() or self.busy.is_set():
            return
        if self.awake:
            self.set_state("hearing")
        text = recognize(pcm, self.settings.get("language"), fallbacks=self.brain.transcribers())
        text = (text or "").strip()
        log.info("Duyulan: %r", text)
        if not text:
            if not self.busy.is_set() and not self.speaking.is_set():
                self.idle_state()
            return
        self.jobs.put(("voice", text))

    # ---------------- iş kuyruğu ----------------
    def _worker(self):
        while True:
            source, text = self.jobs.get()
            self.busy.set()
            try:
                if source == "announce":
                    self.say(text)
                elif source == "announce_send":
                    self.message_send(text)
                else:
                    self._process(source, text)
            except Exception as e:  # hiçbir hata NOVA'yı düşürmesin
                log.exception("İşlem hatası")
                self.emit("toast", text=f"Beklenmeyen hata: {e}", kind="error")
                self.speaking.clear()
                self.listener.hold.clear()
                self.idle_state()
            finally:
                self.busy.clear()

    def _process(self, source, text):
        n = commands.norm(text)
        wake = [commands.norm(w) for w in self.settings.words("wake_words")]
        if "nova" in wake:
            wake += WAKE_VARIANTS
        wake += [chips.name(self.settings, c).lower() for c in chips.ORDER]  # çip adları da uyandırır
        sleep = [commands.norm(w) for w in self.settings.words("sleep_words")]

        if not self.awake:
            if source == "voice" and not any(re.search(rf"\b{re.escape(w)}\b", n) for w in wake):
                return  # uyurken yalnızca uyandırma kelimesini dinle
            self.awake = True
            rest = n
            for w in wake:
                rest = re.sub(rf"\b{re.escape(w)}\b", " ", rest)
            rest = re.sub(r"\b(hey|hadi|artık)\b", " ", rest).strip(" ,")
            self.emit("user", text=text)
            if not rest:
                self.say("Buradayım.")
                return
            text, n = rest, rest
        else:
            self.emit("user", text=text)

        if re.search(r"(çip(i|ini)?|kişiliğ(i|ini)|moda?|sese)? ?(geç|değiştir|aktif et|yükle|çalıştır|olsun)$", n) \
                and (re.search(r"\bçip|kişilik|mod", n) or re.search(r"'?(e|a|ye|ya) geç$", n)):
            cid = chips.find(self.settings, n)
            if cid:
                self.set_chip(cid)
                self.say(chips.get(self.settings)["greeting"])
                return
            if re.search(r"\bçip", n):
                names = ", ".join(chips.name(self.settings, c) for c in chips.ORDER)
                self.say(f"Hangi çipe geçeyim? Seçenekler: {names}.")
                return
        # baştaki ad hitabını at ("nova, saat kaç" → "saat kaç")
        names = "|".join(re.escape(x) for x in ["nova", "noa", "nuva", "nowa", "nava"] +
                         [chips.name(self.settings, c).lower() for c in chips.ORDER])
        stripped = re.sub(rf"^(hey |hadi )?({names})\b[ ,]*", "", n)
        if stripped and stripped != n and not stripped.startswith("'"):
            text, n = stripped, stripped
        if any(re.fullmatch(rf"(nova )?{re.escape(w)}( nova)?", n) for w in sleep):
            self.awake = False
            first = self.settings.words("wake_words")
            self.say(f"Uyku moduna geçiyorum. Uyandırmak için '{first[0] if first else 'nova'} uyan' demen yeterli.",
                     then_sleep=True)
            return
        if re.fullmatch(r"(nova )?(kendini kapat|uygulamayı kapat|kapan)", n):
            self.say("Görüşürüz.")
            time.sleep(2.5)
            self.quit()
            return
        if re.fullmatch(r"(nova )?(sohbeti sıfırla|konuşmayı sıfırla|yeni sohbet)", n):
            self.brain.reset()
            self.emit("clear")
            self.say("Sohbeti sıfırladım.")
            return
        if re.search(r"seni (kim|kimler) (yaptı|geliştirdi|tasarladı)|yapımcın kim|seni yapan kim", n):
            self.say(f"Beni Samet Şahin geliştirdi. Onu sosyal medyada {build_about(self.settings)['handle']} "
                     "olarak bulabilirsin.")
            return

        # --- onay bekleyen mesaj var mı? ---
        if self.pending:
            p, self.pending = self.pending, None
            if p.get("stage") == "to":
                who = social._dative_root(n.split()[0] if len(n.split()) == 1 else n).strip()
                p["contact"] = {"name": who[:1].upper() + who[1:], "search": True}
                p.pop("missing", None)
                return self.message_flow(p)
            if p.get("stage") == "power":
                if re.search(r"^(evet|tamam|olur|onayl\w*|kapat|başlat|tabii)\b", n):
                    extras.power_do(p["kind"])
                    return self.say("Tamam. İptal etmek için 15 saniye içinde 'iptal' de." if p["kind"] in ("shutdown", "restart") else "Tamam.")
                return self.say("Peki, vazgeçtim.")
            if p.get("stage") == "text":
                p["text"] = text[:1].upper() + text[1:]
                p.pop("missing", None)
                return self.message_flow(p)
            if re.search(r"^(evet|gönder|tamam|olur|onayl\w*|paylaş|evet gönder|tabii)\b", n):
                return self.message_send(p)
            if re.search(r"^(hayır|iptal|vazgeç|gönderme|dur|boş ver)\b", n):
                self.emit("msg_preview", hide=True)
                return self.say("Tamam, göndermedim.")
            self.emit("msg_preview", hide=True)

        # --- mesaj gönderme / paylaşım ---
        sm = social.parse(text, n, social.parse_contacts(self.settings.get("contacts")))
        if sm:
            return self.message_flow(sm)

        # --- canlı TV ---
        if re.search(r"\b(canlı|izle|aç|kanal|tv|televizyon)", n) and not re.search(r"youtube|spotify", n):
            ch = tv.find(n)
            if ch and re.search(r"aç|izle|canlı|geç|koy|$", n):
                tv.open_channel(ch[0])
                return self.say(f"{ch[1]} canlı yayını açılıyor.")
            if re.search(r"canlı (tv|televizyon|yayın)|televizyon aç|tv aç", n):
                self.emit("panel", name="tv")
                return self.say("Canlı TV kanalları ekranda. Hangisini açayım?")
        # --- güç komutları (onaylı) ---
        if re.fullmatch(r"(iptal|kapatmayı iptal et|vazgeç)", n):
            extras.power_cancel()
        kind = extras.power_intent(n)
        if kind:
            self.pending = {"stage": "power", "kind": kind}
            return self.say(extras.POWER[kind][0][:1].upper() + extras.POWER[kind][0][1:] + "?")
        # --- deprem, namaz vakti, hesap, pano ---
        if re.search(r"deprem", n):
            return self.say(extras.earthquake_reply(n))
        if re.search(r"namaz|ezan|vakitler|iftar|sahur", n):
            return self.say(extras.prayer_reply(n, self.settings.get("city") or "İstanbul"))
        r = extras.calc(n)
        if r:
            return self.say(r)
        if re.search(r"pano(daki|dakini|yu)? (oku|ne var)|kopyaladığım\w* (oku|ne)", n):
            clip = extras.clipboard_text().strip()
            return self.say(clip[:600] if clip else "Pano boş görünüyor.")

        reply = commands.handle(text, self.settings)
        image = None
        if isinstance(reply, dict):
            if "timer" in reply:
                self.add_timer(reply["timer"], reply.get("label", ""))
                reply = reply["reply"]
            elif reply.get("cancel_timers"):
                count = self.cancel_timers()
                reply = "Tüm zamanlayıcıları iptal ettim." if count else "Kurulu bir zamanlayıcı yok."
            elif reply.get("list_timers"):
                reply = self.describe_timers()
            elif "news" in reply:
                reply = self.news_reply(reply["news"], reply.get("read"))
            elif "calendar_add" in reply:
                reply = self.calendar_add_voice(reply["calendar_add"])
            elif "calendar_list" in reply:
                reply = self.calendar_reply(reply["calendar_list"])
            elif "alarm_at" in reply:
                reply = self.alarm_at(reply["alarm_at"], reply.get("label", ""))
            elif "map" in reply:
                reply = self.map_reply(reply["map"])
            elif "directions" in reply:
                import urllib.parse
                commands.open_url("https://www.google.com/maps/dir/?api=1&destination="
                                  + urllib.parse.quote(reply["directions"]))
                reply = f"{reply['directions']} için yol tarifini açtım."
            elif "rates" in reply:
                reply = self.rates_reply(reply["rates"])
            elif reply.get("update_check"):
                reply = self.update_reply()
            elif "panel" in reply:
                self.emit("panel", name=reply["panel"])
                reply = "Açtım."
            elif "vision" in reply:
                self.set_state("thinking", "Ekrana bakıyorum")
                image = self.capture_screen()
                if image is None:
                    self.say("Ekran görüntüsü alamadım.")
                    return
                reply = None
        if reply is None:
            self.set_state("thinking")
            try:
                reply = self.brain.ask(text, image_png=image)
            except BrainError as e:
                log.warning("Beyin hatası: %s", e)
                reply = str(e)
                self.emit("toast", text=reply, kind="error")
        self.say(reply)

    # ---------------- 1.3 özellikleri ----------------
    def news_reply(self, cat, read):
        data = widgets.news(cat)
        if not data["items"]:
            return "Haberlere şu an ulaşamadım."
        # Haber bülteni ekranı: büyük kartlar, okunurken sırayla öne çıkar
        self.emit("news_show", category=cat, name=data["name"], items=data["items"][:12])
        if not read:
            return f"{data['name']} haberleri ekranda. Okumamı istersen 'haberleri oku' de."
        self.say(f"{data['name']} bülteni.")
        for idx, item in enumerate(data["items"][:6]):
            if not self.awake:
                break
            self.emit("news_focus", index=idx)
            self.say(item["title"].rstrip(".") + ".", record=False)
            if self._interrupted:
                break
        self.emit("news_focus", index=-1)
        return ""

    def calendar_add_voice(self, text):
        n = commands.norm(text)
        n = re.sub(r"^(nova )?(takvim(e|ime)|ajandama)\s*", "", n)
        n = re.sub(r"\b(randevu|etkinlik)?\s*(ekle|kaydet|koy|oluştur|yaz)\b", " ", n)
        n = re.sub(r"\b(takvim(e|ime)|bir|şunu)\b", " ", n)
        day, t, title = widgets.parse_when(n)
        day = day or dt.date.today()
        title = title.strip(" :,") or "Etkinlik"
        ev = self.calendar.add(title[:1].upper() + title[1:], day.isoformat(), t)
        self.emit("calendar", events=self.calendar.public(), focus=ev["date"])
        when = "bugün" if day == dt.date.today() else "yarın" if day == dt.date.today() + dt.timedelta(1) \
            else f"{day.day} {widgets.MONTHS_TR[day.month - 1].capitalize()}"
        return f"Takvime ekledim: {when}{' saat ' + t if t else ''}, {ev['title']}."

    def calendar_reply(self, which):
        day = dt.date.today() + dt.timedelta(days=1 if which == "yarın" else 0)
        events = self.calendar.on_day(day)
        self.emit("panel", name="calendar", focus=day.isoformat())
        if not events:
            return f"{which.capitalize()} takviminde bir şey yok."
        parts = [f"{e['time']} {e['title']}" if e["time"] else e["title"] for e in events]
        return f"{which.capitalize()} {len(events)} etkinliğin var: " + ", ".join(parts) + "."

    def alarm_at(self, hhmm, label=""):
        now = dt.datetime.now()
        h, m = map(int, hhmm.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        self.add_timer(int((target - now).total_seconds()), label or f"Saat {hhmm} alarmı")
        day = "yarın " if target.date() != now.date() else ""
        return f"Tamam, {day}saat {hhmm}'de {'hatırlatacağım: ' + label if label else 'haber vereceğim'}."

    def map_reply(self, place):
        p = widgets.geocode(place)
        if not p:
            return f"{place} için haritada bir yer bulamadım."
        self.emit("panel", name="map", place=p)
        return f"{p['name']} haritada."

    def rates_reply(self, which):
        r = widgets.rates()
        self.emit("rates", **r)
        if not r["ok"]:
            return "Döviz kurlarına şu an ulaşamadım."
        x = r["rates"]
        names = {"dolar": "USD", "euro": "EUR", "avro": "EUR", "sterlin": "GBP", "altın": "ALTIN"}
        fmt = lambda v: f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if which and names[which] in x:
            unit = "gram altın" if which == "altın" else which.capitalize()
            return f"{unit} şu an {fmt(x[names[which]])} lira."
        parts = [f"{k if k != 'ALTIN' else 'gram altın'} {fmt(v)}" for k, v in x.items()]
        return "Güncel kurlar: " + ", ".join(parts) + " lira."

    def update_reply(self):
        info = updater.check(self.settings.get("update_repo"))
        self.update_info = info
        self.emit("update", **info)
        if not info.get("ok"):
            return "Güncellemeleri denetleyemedim."
        if info.get("available"):
            return f"Yeni sürüm var: {info['latest']}. Üstteki Güncelle düğmesine basabilirsin."
        return f"NOVA güncel. Sürüm {info['current']}."

    def _update_check(self):
        time.sleep(8)
        if not self.settings.get("auto_update"):
            return
        info = updater.check(self.settings.get("update_repo"))
        self.update_info = info
        if info.get("available"):
            log.info("Yeni sürüm: %s", info.get("latest"))
            self.emit("update", **info)

    def _calendar_loop(self):
        while True:
            try:
                for ev, kind in self.calendar.due():
                    when = f"{ev['remind']} dakika sonra" if kind == "once" else "şimdi"
                    msg = f"Takvim hatırlatması: {when} {ev['title']}."
                    self.emit("alarm", text=msg)
                    self.jobs.put(("announce", msg))
            except Exception:
                log.exception("Takvim döngüsü")
            time.sleep(20)

    # ---------------- ekran ----------------
    def capture_screen(self):
        """NOVA penceresini kısa süre gizleyip ekranın görüntüsünü al."""
        hidden = ui.window_show("minimize")
        if hidden:
            time.sleep(0.6)
        try:
            return commands.grab_png()
        finally:
            if hidden:
                ui.window_show("restore")

    # ---------------- zamanlayıcılar ----------------
    def add_timer(self, seconds, label=""):
        self._timer_seq += 1
        tid = self._timer_seq
        t = threading.Timer(seconds, self._timer_fired, args=(tid,))
        t.daemon = True
        self.timers[tid] = {"id": tid, "label": label, "end": time.time() + seconds, "seconds": seconds, "t": t}
        t.start()
        self._emit_timers()

    def _timer_fired(self, tid):
        item = self.timers.pop(tid, None)
        self._emit_timers()
        if not item:
            return
        msg = f"Hatırlatma: {item['label']}." if item["label"] else \
            f"{commands.say_duration(item['seconds'])} doldu."
        self.emit("alarm", text=msg)
        self.jobs.put(("announce", msg))

    def cancel_timers(self):
        count = len(self.timers)
        for item in list(self.timers.values()):
            item["t"].cancel()
        self.timers.clear()
        self._emit_timers()
        return count

    def describe_timers(self):
        if not self.timers:
            return "Kurulu bir zamanlayıcı yok."
        parts = []
        for item in sorted(self.timers.values(), key=lambda i: i["end"]):
            left = commands.say_duration(max(1, int(item["end"] - time.time())))
            parts.append(f"{item['label']} için {left}" if item["label"] else left)
        return "Kalan süre: " + ", ".join(parts) + "."

    def _emit_timers(self):
        self.emit("timers", items=[{"id": i["id"], "label": i["label"], "end": int(i["end"] * 1000)}
                                   for i in sorted(self.timers.values(), key=lambda i: i["end"])])

    # ---------------- ses çıkışı ----------------
    def say(self, text, then_sleep=False, record=True):
        if not text:
            return self.idle_state()
        self._interrupted = False
        if record:
            self.emit("nova", text=text)
        if not self.settings.get("speak"):
            if then_sleep:
                self.set_state("sleeping")
            else:
                self.idle_state()
            return
        self.speaking.set()
        self.listener.hold.set()
        self.set_state("speaking")
        # Cümle cümle seslendir: ilk cümle hemen çalarken sonrakiler hazırlanır
        chunks = tts.split_sentences(text)
        for i, chunk in enumerate(chunks):
            if not self.speaking.is_set():  # kullanıcı sözünü kesti
                break
            voice, pitch, rate, fx = chips.voice(self.settings)
            audio = tts.synth(chunk, voice, rate, pitch)
            self.emit("speak", text=chunk, audio=base64.b64encode(audio).decode() if audio else None,
                      lang=self.settings.get("language"), first=(i == 0), final=(i == len(chunks) - 1), fx=fx)
        # arayüz çalmayı bitirince speech_done çağırır; güvenlik için zaman aşımı
        deadline = time.time() + 8 + len(text) * 0.12
        while self.speaking.is_set() and time.time() < deadline:
            time.sleep(0.05)
        self.speaking.clear()
        time.sleep(0.25)
        self.listener.hold.clear()
        self.idle_state()

    # ---------------- mesajlaşma ----------------
    def message_flow(self, m):
        plat = social.PLATFORMS[m["platform"]]
        if m["platform"] != "x" and not m.get("contact"):
            m["stage"] = "to"
            self.pending = m
            return self.say("Kime göndereyim? Uygulamada kayıtlı olduğu adı söyle.")
        if m.get("missing") == "text" or not m.get("text"):
            m["stage"] = "text"
            self.pending = m
            return self.say("Ne yazayım?" if m["platform"] != "x" else "Ne paylaşayım?")
        if self.settings.get("msg_confirm"):
            m["stage"] = "confirm"
            self.pending = m
            to = f"{m['contact']['name']} kişisine " if m.get("contact") else ""
            self.emit("msg_preview", platform=m["platform"], platform_name=plat,
                      to=m["contact"]["name"] if m.get("contact") else "", text=m["text"])
            verb = "paylaşayım mı" if m["platform"] == "x" else "göndereyim mi"
            return self.say(f"{social.FROM[m['platform']]} {to}şunu {verb}: {m['text']}")
        return self.message_send(m)

    def message_send(self, m):
        self.emit("msg_preview", hide=True)
        ok, msg = social.send(m["platform"], m.get("contact"), m["text"], self.settings)
        log.info("Mesaj (%s → %s): %s", m["platform"], (m.get("contact") or {}).get("name", "-"), ok)
        self.emit("msg_sent", ok=ok, platform=m["platform"], to=(m.get("contact") or {}).get("name", ""),
                  text=m["text"])
        return self.say(msg)

    def set_chip(self, cid):
        if cid not in chips.CHIPS:
            return False
        self.settings.update({"chip": cid})
        self.emit("chip", chip=chips.get(self.settings), chips=chips.public(self.settings))
        log.info("Çip: %s", cid)
        return True

    # ---------------- sistem bilgisi ----------------
    def _stats_loop(self):
        try:
            import psutil
        except ImportError:
            return
        psutil.cpu_percent()
        while True:
            time.sleep(2)
            try:
                b = psutil.sensors_battery()
                self.emit("stats", cpu=round(psutil.cpu_percent()), ram=round(psutil.virtual_memory().percent),
                          battery=round(b.percent) if b else None, plugged=bool(b and b.power_plugged))
            except Exception:
                pass

    def quit(self):
        log.info("NOVA kapanıyor")
        self.listener.stop()
        if self.browser and self.browser.poll() is None:
            try:
                self.browser.terminate()
            except Exception:
                pass
        self.quit_event.set()


WAKE_VARIANTS = ["noa", "nuva", "nowa", "nava", "nove", "nowa"]


class Api:
    """JavaScript'ten çağrılan fonksiyonlar (POST /api/<ad>)."""

    def __init__(self, nova: Nova):
        self._n = nova

    def init(self):
        from novaapp.tts import VOICES
        n = self._n
        return {"app": APP_NAME, "version": VERSION, "about": build_about(n.settings), "settings": n.settings.public(),
                "timers": [{"id": i["id"], "label": i["label"], "end": int(i["end"] * 1000)}
                           for i in sorted(n.timers.values(), key=lambda i: i["end"])],
                "update": n.update_info if n.update_info and n.update_info.get("available") else None,
                "chip": chips.get(n.settings), "chips": chips.public(n.settings), "tv": tv.public(),
                "voices": VOICES, "state": n.state, "awake": n.awake, "mic": n.listener.enabled.is_set(),
                "ready": n.brain.ready()}

    def send_text(self, text):
        text = (text or "").strip()
        if text:
            self._n.awake = True
            self._n.jobs.put(("text", text))
        return True

    def speech_done(self):
        self._n.speaking.clear()
        return True

    def contacts(self):
        return social.parse_contacts(self._n.settings.get("contacts"))

    def tv_open(self, cid):
        ch = tv.open_channel(cid)
        return {"ok": bool(ch), "name": ch[1] if ch else ""}

    def apps(self):
        try:
            return social.installed()
        except Exception:
            return {"whatsapp": False, "telegram": False, "x": False}

    def msg_send(self, platform, to_name, text):
        text = (text or "").strip()
        if not text:
            return {"ok": False, "text": "Mesaj boş."}
        to_name = (to_name or "").strip()
        contact = {"name": to_name, "search": True} if to_name else None
        if platform != "x" and not contact:
            return {"ok": False, "text": "Kime gönderileceğini yaz."}
        ok, msg = social.send(platform, contact, text, self._n.settings)
        return {"ok": ok, "text": msg}

    def msg_confirm(self, yes):
        p, self._n.pending = self._n.pending, None
        if not p:
            return False
        if yes:
            self._n.jobs.put(("announce_send", p))
        else:
            self._n.emit("msg_preview", hide=True)
        return True

    def share(self, platform, text, url=""):
        link = social.share_url(platform, text or "", url or "")
        if link:
            webbrowser.open(link, new=2)
        return bool(link)

    def set_chip(self, cid):
        ok = self._n.set_chip(cid)
        if ok and not self._n.busy.is_set():
            self._n.jobs.put(("announce", chips.get(self._n.settings)["greeting"]))
        return {"chip": chips.get(self._n.settings), "chips": chips.public(self._n.settings)}

    def stop_speaking(self):
        self._n._interrupted = True
        self._n.speaking.clear()  # kalan cümleler hazırlanmaz
        self._n.emit("stop_audio")
        return True

    def toggle_mic(self):
        l = self._n.listener
        l.enabled.clear() if l.enabled.is_set() else l.enabled.set()
        if not self._n.speaking.is_set():
            self._n.idle_state()
        return l.enabled.is_set()

    def set_awake(self, awake):
        self._n.awake = bool(awake)
        if not self._n.speaking.is_set():
            self._n.idle_state()
        return self._n.awake

    def save_settings(self, values):
        self._n.settings.update(values or {})
        self._n.emit("chip", chip=chips.get(self._n.settings), chips=chips.public(self._n.settings))
        return {"settings": self._n.settings.public(), "ready": self._n.brain.ready(),
                "about": build_about(self._n.settings), "chips": chips.public(self._n.settings)}

    def cancel_timer(self, tid):
        item = self._n.timers.pop(int(tid), None)
        if item:
            item["t"].cancel()
        self._n._emit_timers()
        return True

    def test_brain(self):
        try:
            return {"ok": True, "text": self._n.brain.ask("Kısaca kendini tanıt.")}
        except BrainError as e:
            return {"ok": False, "text": str(e)}

    def open_url(self, url):
        if isinstance(url, str) and url.startswith(("https://", "http://")):
            webbrowser.open(url, new=2)
        return True

    def minimize(self):
        return ui.window_show("minimize")

    # ----- paneller -----
    def get_news(self, cat="gundem"):
        return widgets.news(cat)

    def read_news(self, cat="gundem"):
        self._n.jobs.put(("text", f"{widgets.NEWS_NAMES.get(cat, 'Gündem')} haberlerini oku"))
        return True

    def get_weather(self, city=None):
        return widgets.weather(city or self._n.settings.get("city"))

    def get_rates(self):
        return widgets.rates()

    def geocode(self, q):
        return widgets.geocode(q)

    def cal_list(self):
        return self._n.calendar.public()

    def cal_add(self, ev):
        e = self._n.calendar.add(ev.get("title"), ev.get("date"), ev.get("time") or "", ev.get("note") or "",
                                 ev.get("remind", 10))
        return {"ok": True, "event": e, "events": self._n.calendar.public()}

    def cal_delete(self, eid):
        self._n.calendar.delete(eid)
        return self._n.calendar.public()

    def add_timer(self, seconds, label=""):
        self._n.add_timer(max(1, int(float(seconds))), str(label or ""))
        return True

    def add_alarm(self, hhmm, label=""):
        return self._n.alarm_at(hhmm, label)

    def notes_list(self):
        p = commands.notes_path()
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                m = re.match(r"\[(.*?)\] (.*)", line)
                out.append({"time": m.group(1), "text": m.group(2)} if m else {"time": "", "text": line})
        return out

    def note_add(self, text):
        text = (text or "").strip().replace("\n", " ")
        if text:
            with commands.notes_path().open("a", encoding="utf-8") as f:
                f.write(f"[{dt.datetime.now():%d.%m.%Y %H:%M}] {text}\n")
        return self.notes_list()

    def note_delete(self, index):
        p = commands.notes_path()
        lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
        if 0 <= int(index) < len(lines):
            lines.pop(int(index))
            p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return self.notes_list()

    def check_update(self):
        info = updater.check(self._n.settings.get("update_repo"))
        self._n.update_info = info
        return info

    def install_update(self):
        info = self._n.update_info or updater.check(self._n.settings.get("update_repo"))
        if not info.get("available"):
            return {"ok": False, "error": "Yeni sürüm yok"}

        def run():
            try:
                updater.download_and_install(info["url"], lambda p: self._n.emit("update_progress", value=p))
                self._n.emit("toast", text="Güncelleme kuruluyor, NOVA yeniden açılacak…")
                time.sleep(1.5)
                self._n.quit()
            except Exception as e:
                log.exception("Güncelleme hatası")
                self._n.emit("toast", text=f"Güncelleme indirilemedi: {e}", kind="error")

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def log_js(self, text):
        log.warning("Arayüz: %s", str(text)[:500])
        return True

    def quit(self):
        threading.Thread(target=self._n.quit, daemon=True).start()
        return True


def message_box(text, title="NOVA"):
    log.error(text)
    if sys.platform.startswith("win"):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    else:
        print(text, file=sys.stderr)


def single_instance() -> bool:
    """NOVA zaten açıksa penceresini öne getir. Pencere yoksa (takılı kalmış kopya) yine de başla."""
    if not sys.platform.startswith("win"):
        return True
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    global _MUTEX
    _MUTEX = k32.CreateMutexW(None, False, "Local\\NOVA_SametSahin_Asistan_v2")
    if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS
        return True
    return not ui.window_show("front")


def main():
    log.info("NOVA %s başlıyor (Python %s, %s, %s)", VERSION, sys.version.split()[0], sys.platform,
             "exe" if getattr(sys, "frozen", False) else "kaynak")
    if not single_instance():
        log.info("NOVA zaten açık; pencere öne getirildi")
        return
    nova = Nova()
    api = Api(nova)
    nova.ui = ui.UIServer(resource("web"), api)
    profile = nova_log.data_dir() / "pencere-v2"
    nova.browser = ui.open_window(nova.ui.url, profile, bool(nova.settings.get("fullscreen")))

    def boot():
        if nova.ui.hub.ever_connected.wait(40):
            time.sleep(0.4)
            nova.start()
        else:
            log.error("Arayüz 40 sn içinde bağlanmadı")
            message_box("NOVA arayüzü açılamadı. Microsoft Edge kurulu mu?\n\n"
                        f"Ayrıntılar: {LOG_PATH}")
            nova.quit()

    threading.Thread(target=boot, daemon=True, name="nova-boot").start()

    # Pencere kapanınca NOVA da kapansın
    while not nova.quit_event.is_set():
        if nova.browser is not None and nova.browser.poll() is not None:
            # Edge bazen pencereyi ayrı bir işleme devreder; arayüz hâlâ bağlıysa bekle
            if nova.ui.hub.ever_connected.is_set() and nova.ui.hub.count() == 0:
                log.info("Pencere kapandı")
                break
            nova.browser = None
        if nova.browser is None and nova.ui.hub.ever_connected.is_set() and nova.ui.hub.count() == 0 \
                and time.time() - nova.ui.hub.last_seen > 15:
            log.info("Arayüz 15 sn'dir bağlı değil, kapanıyor")
            break
        nova.quit_event.wait(1)
    nova.quit()


def check_python():
    if getattr(sys, "frozen", False):
        return True
    if sys.version_info[:2] not in ((3, 12), (3, 13)):
        message_box(f"Bu Python sürümü ({sys.version.split()[0]}) ile main.py doğrudan açılamaz.\n\n"
                    "NOVA'yı açmak için klasördeki 'NOVA Baslat.bat' dosyasına çift tıkla "
                    "(ya da build.bat ile oluşan dist\\NOVA\\NOVA.exe'yi kullan).")
        return False
    return True


if __name__ == "__main__":
    try:
        if check_python():
            main()
    except Exception as e:
        log.exception("NOVA başlatılamadı")
        message_box(f"NOVA başlatılamadı: {e}\n\nAyrıntılar: {LOG_PATH}")
    finally:
        logging.shutdown()
        os._exit(0)
