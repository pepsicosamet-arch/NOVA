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
from novaapp import smarthome  # noqa: E402
from novaapp import phone as phone_mod  # noqa: E402
from collections import deque  # noqa: E402
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
        self.last_reply = ""     # beynin son yanıtı ("bunu gönder" için)
        self.last_said = ""
        self.gen = 0             # kullanıcı araya girince düşünmeyi iptal etmek için
        self.feed = deque(maxlen=80)   # telefon sayfası için son konuşmalar
        self._feed_id = 0
        self.profile = None
        self.phone = phone_mod.PhoneServer(self)
        self.vacuum = smarthome.TuyaVacuum(self.settings)
        self.timers = {}
        self.calendar = widgets.Calendar()
        self.update_info = None
        self._timer_seq = 0
        self.listener = Listener(self._on_utterance, self._on_level, self._on_mic_error,
                                 sensitivity=lambda: self.settings.get("sensitivity"),
                                 on_barge=self._on_barge, barge=lambda: bool(self.settings.get("barge_in")))
        threading.Thread(target=self._worker, daemon=True, name="nova-worker").start()

    # ---------------- arayüze olay gönder ----------------
    def emit(self, event_type, **data):
        if event_type in ("user", "nova") and data.get("text"):
            self._feed_id += 1
            self.feed.append({"id": self._feed_id, "who": event_type, "text": data["text"]})
        if not self.ui:
            return
        data["type"] = event_type
        self.ui.hub.send(data)

    def chip_name(self):
        return chips.name(self.settings)

    # ---------------- pencere / arka plan ----------------
    def window_open(self):
        return bool(self.ui and self.ui.hub.count() > 0)

    def show_window(self):
        if self.window_open():
            ui.window_show("front")
        elif self.ui:
            self.browser = ui.open_window(self.ui.url, self.profile, bool(self.settings.get("fullscreen")))

    def hide_window(self):
        if self.browser and self.browser.poll() is None:
            self.browser.terminate()
        else:
            ui.window_show("minimize")

    def apply_autostart(self):
        if not sys.platform.startswith("win") or not getattr(sys, "frozen", False):
            return
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
                if self.settings.get("autostart"):
                    winreg.SetValueEx(k, "NOVA", 0, winreg.REG_SZ, f'"{sys.executable}" --arka-plan')
                else:
                    try:
                        winreg.DeleteValue(k, "NOVA")
                    except OSError:
                        pass
        except OSError as e:
            log.warning("Otomatik başlatma ayarlanamadı: %s", e)

    def start_tray(self):
        try:
            import pystray
            from PIL import Image
        except Exception as e:
            log.warning("Sistem tepsisi simgesi yok: %s", e)
            return
        try:
            img = Image.open(resource("assets", "nova_256.png"))
        except Exception:
            img = Image.new("RGB", (64, 64), "#5fe3ff")
        mic_label = lambda item: "Mikrofonu kapat" if self.listener.enabled.is_set() else "Mikrofonu aç"
        menu = pystray.Menu(
            pystray.MenuItem("NOVA'yı göster", lambda: self.show_window(), default=True),
            pystray.MenuItem(mic_label, lambda: (self.listener.enabled.clear() if self.listener.enabled.is_set()
                                                 else self.listener.enabled.set(), self.idle_state())),
            pystray.MenuItem("Kapat", lambda: self.quit()),
        )
        try:
            self.tray = pystray.Icon("NOVA", img, "NOVA · arka planda dinliyor", menu)
            threading.Thread(target=self.tray.run, daemon=True, name="nova-tepsi").start()
        except Exception as e:
            log.warning("Sistem tepsisi simgesi oluşturulamadı: %s", e)

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
        if self.settings.get("phone_enabled"):
            self.phone.start()
        self.start_tray()
        self.apply_autostart()
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

    def _on_barge(self):
        """Kullanıcı konuşmaya başladı: NOVA susar ve düşünmeyi bırakır."""
        self._interrupted = True
        self.gen += 1                      # süren düşünme sonucunu çöpe at
        self.speaking.clear()
        self.emit("stop_audio")
        self.listener.hold.clear()
        self.set_state("hearing")

    def ask_brain(self, text, image_png=None):
        """Beyne sor; kullanıcı araya girerse yanıtı beklemeden bırak (None döner)."""
        import concurrent.futures as cf
        g = self.gen
        self.listener.hold.set()           # düşünürken de araya girilebilsin
        ex = cf.ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(self.brain.ask, text, image_png)
        try:
            while True:
                try:
                    return fut.result(timeout=0.1)
                except cf.TimeoutError:
                    if self.gen != g:
                        log.info("Düşünme iptal edildi (kullanıcı araya girdi)")
                        return None
        finally:
            ex.shutdown(wait=False)
            if self.gen == g:
                self.listener.hold.clear()

    def _on_mic_error(self, msg):
        self.emit("toast", text=msg, kind="error")

    def _on_utterance(self, pcm):
        if self.speaking.is_set():
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
                elif source == "vision_img":
                    png, q = text
                    self.set_state("thinking", "Kameraya bakıyorum")
                    try:
                        self.say(self.brain.ask(q or "Kamerada ne görüyorsun? Kısaca anlat.", image_png=png))
                    except BrainError as e:
                        self.say(str(e))
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
        if source == "phone":
            source = "text"
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
        if self.pending and self.pending.get("stage") in ("text", "to") and \
                social.parse(text, n, []) is not None:
            self.pending = None                 # yeni bir mesaj komutu geldi: eskisini bırak
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
                if re.fullmatch(r"(gönder|hadi gönder|gönder hadi|evet|tamam|olur|onu gönder|bunu gönder)", n):
                    if self.last_reply:
                        p["text"] = self.last_reply
                    else:
                        self.pending = p
                        return self.say("Mesajın kendisini söyle, ne yazayım?")
                else:
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

        # --- pencere / arka plan ---
        if re.search(r"(ekranı|pencereyi|arayüzü|kendini) (aç|göster)|ekrana gel|nova'?yı (aç|göster)", n):
            self.show_window()
            return self.say("Buradayım.")
        if re.search(r"arka plana (geç|çekil|git)|(pencereyi|ekranı|kendini) (gizle|kapat)|gizlen", n):
            self.say("Arka plana geçiyorum, seni dinlemeye devam ediyorum.")
            self.hide_window()
            return
        # --- kamera ---
        if re.search(r"kamera(yı|y[ıi])? (aç|başlat|göster)|kamerayı açar mısın", n):
            self.show_window()
            self.emit("camera", action="open")
            return self.say("Kamerayı açtım.")
        if re.search(r"kamera(yı|y[ıi])? kapat", n):
            self.emit("camera", action="close")
            return self.say("Kamerayı kapattım.")
        if re.search(r"kamera(da|ya) (ne|bak)|beni görüyor musun|elimde ne var|bu ne\b.*kamera|(fotoğraf|resim) çek", n):
            self.show_window()
            if re.search(r"(fotoğraf|resim) çek", n):
                self.emit("camera", action="photo")
                return self.say("Fotoğraf çekiyorum.")
            self.emit("camera", action="ask", question=text)
            return self.set_state("thinking", "Kameraya bakıyorum")
        # --- telefon bağlantısı ---
        if re.search(r"telefon(umu|u)? bağla|telefon bağlantısı|qr kod", n):
            if re.search(r"uygulama|phone link", n):
                commands.run_app("ms-phone:")
                return self.say("Telefon Bağlantısı uygulamasını açtım.")
            self.settings.update({"phone_enabled": True})
            ok = self.phone.start()
            self.show_window()
            self.emit("panel", name="phone")
            return self.say("Telefonunla ekrandaki QR kodu okut. Telefonun bu bilgisayarla aynı Wi-Fi'da olmalı."
                            if ok else "Telefon bağlantısı başlatılamadı.")

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
        # --- akıllı ev: robot süpürge ---
        vi = smarthome.intent(n)
        if vi:
            return self.say(self.vacuum_do(*vi))

        # --- pratik komutlar ---
        if re.search(r"tam ekran", n):
            ui.window_show("front")
            time.sleep(0.2)
            social._keys(0x7A)                 # F11
            return self.say("Tamam.")
        if re.fullmatch(r"(harita(yı)?|haritalar(ı)?) (aç|göster)", n):
            self.show_window()
            self.emit("panel", name="map")
            return self.say("Harita açık.")
        if re.search(r"(tekrar et|tekrarla|ne dedin|bir daha söyle)", n) and self.last_said:
            return self.say(self.last_said)
        if re.search(r"daha (yavaş|ağır) konuş", n):
            self.settings.update({"rate": max(-40, int(self.settings.get("rate") or 0) - 10)})
            return self.say("Tamam, daha yavaş konuşuyorum.")
        if re.search(r"daha hızlı konuş", n):
            self.settings.update({"rate": min(40, int(self.settings.get("rate") or 0) + 10)})
            return self.say("Tamam, daha hızlı konuşuyorum.")
        m = re.search(r"(\d+(?:[.,]\d+)?) (dolar|euro|avro|sterlin|gram altın|altın)\w* (kaç |ne kadar )?(tl|lira|türk lirası)", n)
        if m:
            r = widgets.rates()
            key = {"dolar": "USD", "euro": "EUR", "avro": "EUR", "sterlin": "GBP"}.get(m.group(2), "ALTIN")
            val = (r.get("rates") or {}).get(key)
            if not val:
                return self.say("Kurlara şu an ulaşamadım.")
            amount = float(m.group(1).replace(",", "."))
            tl = f"{amount * val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return self.say(f"{m.group(1)} {m.group(2)} yaklaşık {tl} lira eder.")
        if re.search(r"\bip adres", n):
            lan = phone_mod.lan_ip()
            try:
                import requests as _rq
                pub = _rq.get("https://api.ipify.org", timeout=5).text.strip()
            except Exception:
                pub = "alınamadı"
            return self.say(f"Yerel IP adresin {lan}, internetteki adresin {pub}.")
        m = re.search(r"^(.+?)'?(?:y?[ıiuü]|n[ıiuü])? (kapat|sonlandır)$", n)
        if m and not re.search(r"bilgisayar|ekran|pencere|sistem|oturum|kamera|ses|müzik|zamanlayıcı|alarm|telefon", m.group(1)):
            exe = extras.PROCESS.get(re.sub(r"'.*$", "", m.group(1)).strip())
            if exe:
                extras.kill(exe)
                return self.say(f"{m.group(1).split(chr(39))[0].capitalize()} kapatıldı.")
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
                reply = self.ask_brain(text, image_png=image)
                if reply is None:          # kullanıcı araya girdi
                    return
                self.last_reply = reply
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
        self.last_said = text
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
        chunks = tts.split_sentences(text)
        if not self.window_open():                  # arka plan: sesi doğrudan Windows çalar
            for chunk in chunks:
                if not self.speaking.is_set():
                    break
                voice, pitch, rate, fx = chips.voice(self.settings)
                audio = tts.synth(chunk, voice, rate, pitch)
                tts.play_local(audio, self.speaking)
            self.speaking.clear()
            time.sleep(0.25)
            self.listener.hold.clear()
            return self.idle_state()
        # Cümle cümle seslendir: ilk cümle hemen çalarken sonrakiler hazırlanır
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

    # ---------------- akıllı ev ----------------
    def vacuum_do(self, action, arg=None):
        if not self.vacuum.configured():
            self.show_window()
            self.emit("panel", name="home")
            return "Robot süpürge henüz bağlı değil. Ev menüsündeki adımlarla Tuya hesabını bir kez bağlaman gerekiyor."
        try:
            if action == "status":
                st = self.vacuum.status()
                self.emit("home", status=st)
                pil = f", şarjı yüzde {st['battery']}" if st["battery"] is not None else ""
                return f"Süpürge {st['status_tr']}{pil}."
            if action == "suction":
                lvl = self.vacuum.suction(arg)
                reply = f"Emiş gücü {lvl} yapıldı."
            else:
                getattr(self.vacuum, action)(*( [arg] if arg else []))
                reply = {"start": "Süpürge temizliğe başladı.", "pause": "Süpürgeyi durdurdum.",
                         "dock": "Süpürge şarj istasyonuna dönüyor.", "seek": "Süpürge ses çıkarıyor, sesi takip et.",
                         "mode": f"Süpürge {arg} modunda temizliyor."}[action]
            threading.Thread(target=self._home_refresh, daemon=True).start()
            return reply
        except Exception as e:
            log.warning("Süpürge hatası: %s", e)
            return str(e)

    def _home_refresh(self):
        time.sleep(3)
        try:
            self.emit("home", status=self.vacuum.status())
        except Exception:
            pass

    # ---------------- mesajlaşma ----------------
    def message_flow(self, m):
        plat = social.PLATFORMS[m["platform"]]
        if m["platform"] != "x" and not m.get("contact"):
            m["stage"] = "to"
            self.pending = m
            return self.say("Kime göndereyim? Uygulamada kayıtlı olduğu adı söyle.")
        body = (m.get("text") or "").strip()
        low = commands.norm(body)
        # "bunu / hazırladığın mesajı / şiiri gönder" → son yanıtı gönder
        if (not body or re.fullmatch(r"(bunu|onu|bu mesajı|mesajı|bu şiiri|şiiri|hazırladığın mesajı|"
                                     r"hazırladığın şiiri|yazdığın mesajı|son mesajı|o mesajı)", low)) and self.last_reply:
            m["text"] = self.last_reply
        elif not body:
            m["stage"] = "text"
            self.pending = m
            return self.say("Ne yazayım?" if m["platform"] != "x" else "Ne paylaşayım?")
        # "aşk dolu bir şiir / güzel bir mesaj hazırla" → mesajı yapay zekâ yazsın
        elif re.search(r"\b(şiir\w*|hazırla\w*|romantik|aşk dolu|duygusal|komik|doğum günü|tebrik|kutla\w*|özür|"
                       r"teşekkür|güzel bir|anlamlı|günaydın mesajı|iyi geceler mesajı|bir mesaj)\b", low) \
                and len(low.split()) <= 12:
            who = (m.get("contact") or {}).get("name", "")
            brief = re.sub(r"\b(bana|hazırla\w*|ve|yaz|gönder)\b", " ", body).strip()
            self.set_state("thinking", "Mesajı yazıyorum")
            try:
                gen = self.brain.ask(
                    f"{who + ' adlı kişiye ' if who else ''}gönderilecek bir mesaj yaz: {brief}. "
                    "Yalnızca mesaj metnini yaz; tırnak, başlık ya da açıklama ekleme. En fazla 5 kısa cümle.")
                m["text"] = gen.strip().strip('"“”')
            except BrainError as e:
                return self.say(f"Mesajı yazamadım: {e}")
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
        try:
            self.tray.stop()
        except Exception:
            pass
        self.phone.stop()
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

    def phone_info(self):
        return self._n.phone.info()

    def phone_toggle(self, on):
        self._n.settings.update({"phone_enabled": bool(on)})
        if on:
            self._n.phone.start()
        else:
            self._n.phone.stop()
        return self._n.phone.info()

    def phone_reset(self):
        import secrets as _s
        self._n.settings.update({"phone_token": _s.token_urlsafe(12)})
        return self._n.phone.info()

    def save_photo(self, data_url):
        import datetime as _dt
        from pathlib import Path
        raw = base64.b64decode(data_url.split(",", 1)[1])
        folder = Path.home() / "Pictures" / "NOVA"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"kamera_{_dt.datetime.now():%Y%m%d_%H%M%S}.png"
        path.write_bytes(raw)
        return {"ok": True, "path": str(path)}

    def camera_vision(self, data_url, question=""):
        png = base64.b64decode(data_url.split(",", 1)[1])
        self._n.jobs.put(("vision_img", (png, question)))
        return True

    def show_window(self):
        threading.Thread(target=self._n.show_window, daemon=True).start()
        return True

    def hide(self):
        threading.Thread(target=self._n.hide_window, daemon=True).start()
        return True

    def home_info(self):
        v = self._n.vacuum
        out = {"configured": v.configured(), "region": self._n.settings.get("tuya_region"),
               "regions": smarthome.REGIONS}
        if v.configured():
            try:
                out["status"] = v.status()
            except Exception as e:
                out["error"] = str(e)
        return out

    def home_save(self, values):
        vals = {k: (values or {}).get(k, "") for k in ("tuya_key", "tuya_secret", "tuya_region", "tuya_device")}
        if not vals["tuya_secret"]:
            vals.pop("tuya_secret")            # boş bırakılırsa eskisi kalsın
        self._n.settings.update(vals)
        self._n.vacuum.reset()
        return self.home_info()

    def home_scan(self):
        return smarthome.lan_scan()

    def home_devices(self):
        try:
            return {"ok": True, "devices": self._n.vacuum.devices()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def home_cmd(self, action, arg=None):
        if action not in ("start", "pause", "dock", "seek", "suction", "mode", "status"):
            return {"ok": False}
        text = self._n.vacuum_do(action, arg)
        self._n.emit("toast", text="🧹 " + text)
        return {"ok": True, "text": text}

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
        self._n.apply_autostart()
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
    # Zaten çalışıyor: penceresi varsa öne getir, arka plandaysa pencereyi açmasını iste
    if ui.window_show("front"):
        return False
    try:
        import json as _json
        import urllib.request
        info = _json.loads((nova_log.data_dir() / "nova.run.json").read_text(encoding="utf-8"))
        req = urllib.request.Request(f"http://127.0.0.1:{info['port']}/api/show_window", data=b"[]", method="POST",
                                     headers={"X-Nova-Token": info["token"], "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
        return False
    except Exception as e:
        log.warning("Çalışan NOVA'ya ulaşılamadı (%s); yeni kopya başlatılıyor", e)
        return True


def main():
    log.info("NOVA %s başlıyor (Python %s, %s, %s)", VERSION, sys.version.split()[0], sys.platform,
             "exe" if getattr(sys, "frozen", False) else "kaynak")
    if not single_instance():
        log.info("NOVA zaten açık; pencere öne getirildi")
        return
    nova = Nova()
    api = Api(nova)
    nova.ui = ui.UIServer(resource("web"), api)
    try:
        (nova_log.data_dir() / "nova.run.json").write_text(
            json.dumps({"port": nova.ui.port, "token": nova.ui.token}), encoding="utf-8")
    except OSError:
        pass
    profile = nova_log.data_dir() / "pencere-v2"
    nova.profile = profile
    hidden_start = "--arka-plan" in sys.argv
    if not hidden_start:
        nova.browser = ui.open_window(nova.ui.url, profile, bool(nova.settings.get("fullscreen")))

    def boot():
        if hidden_start:
            log.info("Arka planda başladı")
            nova.start()
            return
        if nova.ui.hub.ever_connected.wait(40):
            time.sleep(0.4)
            nova.start()
        else:
            log.error("Arayüz 40 sn içinde bağlanmadı")
            message_box("NOVA arayüzü açılamadı. Microsoft Edge kurulu mu?\n\n"
                        f"Ayrıntılar: {LOG_PATH}")
            nova.quit()

    threading.Thread(target=boot, daemon=True, name="nova-boot").start()

    # Pencere kapanınca: arka plan açıksa dinlemeye devam et, değilse kapan
    announced = False
    while not nova.quit_event.is_set():
        if nova.browser is not None and nova.browser.poll() is not None:
            nova.browser = None
        closed = nova.browser is None and nova.ui.hub.ever_connected.is_set() and nova.ui.hub.count() == 0 \
            and time.time() - nova.ui.hub.last_seen > 4
        if closed:
            if not nova.settings.get("background"):
                log.info("Pencere kapandı, NOVA kapanıyor")
                break
            if not announced:
                log.info("Pencere kapandı, arka planda çalışıyor")
                announced = True
        elif nova.ui.hub.count() > 0:
            announced = False
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
