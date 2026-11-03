"""Sürekli dinleme: mikrofon → konuşma algılama (enerji tabanlı) → konuşma parçası."""

import io
import json
import logging
import math
import queue
import threading
import time
import wave
from collections import deque

log = logging.getLogger("nova.listener")

RATE = 16000
BLOCK = 480                # 30 ms
PREROLL = 10               # konuşmadan önceki 300 ms
END_SILENCE = 27           # ~0.8 sn sessizlik = cümle bitti
MAX_BLOCKS = 500           # en fazla 15 sn
MIN_BLOCKS = 12            # 360 ms'den kısa sesleri at


def to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


class Listener(threading.Thread):
    def __init__(self, on_utterance, on_level, on_error, sensitivity=lambda: 1.0):
        super().__init__(daemon=True, name="nova-listener")
        self.on_utterance = on_utterance
        self.on_level = on_level
        self.on_error = on_error
        self.sensitivity = sensitivity
        self.enabled = threading.Event()   # mikrofon açık mı
        self.hold = threading.Event()      # NOVA konuşurken / düşünürken dinlemeyi tut
        self._halt = threading.Event()

    def stop(self):
        self._halt.set()

    def run(self):
        while not self._halt.is_set():
            try:
                self._loop()
            except Exception as e:  # mikrofon yok, sürücü hatası vb.
                log.exception("Mikrofon hatası")
                self.on_error(f"Mikrofon açılamadı: {e}. Windows Ayarlar → Gizlilik → Mikrofon iznini kontrol et.")
                time.sleep(4)

    def _loop(self):
        import numpy as np
        import sounddevice as sd

        q = queue.Queue()

        def cb(indata, frames, t, status):
            q.put(indata.copy())

        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK, callback=cb):
            noise = None
            pre = deque(maxlen=PREROLL)
            frames, speaking, voiced, silence, tick = [], False, 0, 0, 0
            while not self._halt.is_set():
                try:
                    block = q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if not self.enabled.is_set() or self.hold.is_set():
                    frames, speaking, voiced, silence = [], False, 0, 0
                    pre.clear()
                    tick += 1
                    if tick % 4 == 0:
                        self.on_level(0.0)
                    continue

                x = block.astype(np.float32)
                rms = float(math.sqrt(float(np.mean(x * x)) + 1e-9))
                noise = rms if noise is None else (noise * 0.97 + rms * 0.03 if not speaking else noise)
                thr = max(260.0, noise * 2.8) / max(0.3, float(self.sensitivity() or 1.0))

                tick += 1
                if tick % 3 == 0:
                    self.on_level(min(1.0, rms / 4000.0))

                if not speaking:
                    pre.append(block)
                    voiced = voiced + 1 if rms > thr else 0
                    if voiced >= 3:
                        speaking, frames, silence = True, list(pre), 0
                else:
                    frames.append(block)
                    silence = silence + 1 if rms < thr * 0.75 else 0
                    if silence >= END_SILENCE or len(frames) >= MAX_BLOCKS:
                        if len(frames) - silence >= MIN_BLOCKS:
                            pcm = np.concatenate(frames).tobytes()
                            threading.Thread(target=self.on_utterance, args=(pcm,), daemon=True).start()
                        frames, speaking, voiced, silence = [], False, 0, 0
                        pre.clear()


GOOGLE_URL = "http://www.google.com/speech-api/v2/recognize"
GOOGLE_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"  # Chromium'un herkese açık konuşma anahtarı


class NoSpeech(Exception):
    """Ses alındı ama içinde anlaşılır konuşma yok."""


def _flac(pcm: bytes) -> bytes | None:
    try:
        import numpy as np
        import soundfile as sf
        buf = io.BytesIO()
        sf.write(buf, np.frombuffer(pcm, dtype=np.int16), RATE, format="FLAC", subtype="PCM_16")
        return buf.getvalue()
    except Exception as e:
        log.warning("FLAC kodlanamadı: %s", e)
        return None


def google_free(pcm: bytes, language: str) -> str:
    """Google'ın ücretsiz konuşma tanıması. Ek program gerektirmez."""
    import requests
    flac = _flac(pcm)
    data, ctype = (flac, f"audio/x-flac; rate={RATE}") if flac else (pcm, f"audio/l16; rate={RATE}")
    r = requests.post(GOOGLE_URL, data=data, timeout=12, headers={"Content-Type": ctype},
                      params={"client": "chromium", "lang": language, "key": GOOGLE_KEY, "output": "json"})
    r.raise_for_status()
    for line in r.text.splitlines():
        line = line.strip()
        if not line:
            continue
        res = (json.loads(line).get("result") or [])
        for item in res:
            for alt in item.get("alternative") or []:
                if alt.get("transcript"):
                    return alt["transcript"]
    raise NoSpeech()


def recognize(pcm: bytes, language="tr-TR", fallbacks=()) -> str:
    """Sırayla: Google (ücretsiz) → Gemini → OpenAI. Konuşma yoksa boş metin döner."""
    try:
        return google_free(pcm, language)
    except NoSpeech:
        return ""
    except Exception as e:
        log.warning("Google konuşma tanıma çalışmadı: %s", e)
    wav = to_wav(pcm)
    for fb in fallbacks:
        try:
            text = fb(wav)
            if text:
                return text
        except Exception as e:
            log.warning("Yedek konuşma tanıma çalışmadı: %s", e)
    return ""
