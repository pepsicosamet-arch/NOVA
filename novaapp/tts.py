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


def synth(text: str, voice: str = "tr-TR-AhmetNeural", rate: int = 0) -> bytes | None:
    try:
        import edge_tts
    except ImportError:
        return None

    async def run():
        com = edge_tts.Communicate(text, voice, rate=f"{int(rate):+d}%")
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
