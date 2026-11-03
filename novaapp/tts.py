"""Seslendirme: Microsoft Edge nöral sesleri (edge-tts). Arayüzde çalınır."""

import asyncio

VOICES = [
    {"id": "tr-TR-AhmetNeural", "name": "Ahmet (Türkçe, erkek)"},
    {"id": "tr-TR-EmelNeural", "name": "Emel (Türkçe, kadın)"},
    {"id": "en-US-AndrewNeural", "name": "Andrew (İngilizce, erkek)"},
    {"id": "en-US-AvaNeural", "name": "Ava (İngilizce, kadın)"},
    {"id": "de-DE-ConradNeural", "name": "Conrad (Almanca, erkek)"},
    {"id": "ar-SA-HamedNeural", "name": "Hamed (Arapça, erkek)"},
]


def synth(text: str, voice: str = "tr-TR-AhmetNeural", rate: int = 0, pitch: int = 0) -> bytes | None:
    try:
        import edge_tts
    except ImportError:
        return None

    async def run():
        com = edge_tts.Communicate(text, voice, rate=f"{int(rate):+d}%", pitch=f"{int(pitch):+d}Hz")
        out = bytearray()
        async for chunk in com.stream():
            if chunk.get("type") == "audio":
                out += chunk["data"]
        return bytes(out)

    try:
        data = asyncio.run(run())
        return data or None
    except Exception:
        return None


def split_sentences(text: str, first_max: int = 60, max_len: int = 260) -> list[str]:
    """Metni seslendirme parçalarına böler. İlk parça kısa tutulur ki NOVA hemen konuşmaya başlasın."""
    import re
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", text or "") if s.strip()]
    if not sentences:
        return [text] if text else []
    chunks, cur = [], ""
    for s in sentences:
        limit = first_max if not chunks else max_len
        if cur and len(cur) + 1 + len(s) > limit:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


_play_lock = None


def play_local(mp3: bytes, stop_flag=None) -> bool:
    """Arayüz kapalıyken (arka plan) sesi doğrudan Windows ile çal (MCI). Çalma bitene kadar bekler."""
    import os
    import sys
    import tempfile
    import threading
    import time
    global _play_lock
    if not sys.platform.startswith("win") or not mp3:
        return False
    if _play_lock is None:
        _play_lock = threading.Lock()
    import ctypes
    mci = ctypes.windll.winmm.mciSendStringW
    path = os.path.join(tempfile.gettempdir(), f"nova_ses_{threading.get_ident()}.mp3")
    with _play_lock:
        with open(path, "wb") as f:
            f.write(mp3)
        alias = "novases"
        mci(f'close {alias}', None, 0, None)
        if mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, None) != 0:
            return False
        mci(f'play {alias}', None, 0, None)
        buf = ctypes.create_unicode_buffer(64)
        while True:
            time.sleep(0.1)
            mci(f'status {alias} mode', buf, 64, None)
            if buf.value != "playing" or (stop_flag is not None and not stop_flag.is_set()):
                break
        mci(f'stop {alias}', None, 0, None)
        mci(f'close {alias}', None, 0, None)
    return True
