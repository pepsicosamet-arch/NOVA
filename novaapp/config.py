"""Ayarlar ve dosya yolları."""

import json
import os
import sys
import threading
from pathlib import Path

from . import APP_NAME

DEFAULTS = {
    "user_name": "",
    "provider": "gemini",              # "gemini" | "openai" | "custom"
    "gemini_key": "",
    "gemini_model": "gemini-3.8-flash",
    "openai_key": "",
    "openai_model": "gpt-4o-mini",
    # Kendi yapay zekan / yerel model (OpenAI uyumlu: Ollama, LM Studio, kendi API sunucun)
    "custom_url": "http://localhost:11434/v1",
    "custom_key": "",
    "custom_model": "llama3.1",
    "web_search": True,                # Gemini: Google Arama ile güncel bilgi
    "voice": "tr-TR-AhmetNeural",
    "rate": 0,                         # yüzde, -40..+40
    "speak": True,
    "continuous": True,                # mikrofona basmadan sürekli dinleme
    "sensitivity": 1.0,                # 0.5 .. 2.0
    "language": "tr-TR",
    "city": "İstanbul",
    "fullscreen": True,
    "wake_words": "nova, uyan",
    "auto_update": True,
    "update_repo": "pepsicosamet-arch/nova",
    # Çipler (kişilikler): nova | atlas | lyra | kronos
    "chip": "nova",
    "chip_voice": True,                # çipin kendi sesini ve ses efektini kullan
    "chip_name_nova": "",
    "chip_name_atlas": "",
    "chip_name_lyra": "",
    "chip_name_kronos": "",
    # Mesajlaşma ve paylaşım
    "contacts": "",                    # her satır: Ad = telefon = @telegram
    "msg_confirm": False,              # göndermeden önce sesli onay iste
    "msg_auto_send": True,             # sohbet açılınca Enter'a kendisi bassın
    "msg_wait": 4.0,                   # uygulamanın açılmasını bekleme süresi (sn)
    "tg_bot_token": "",                # isteğe bağlı: Telegram Bot ile arka planda gönderim
    "show_transcript": False,          # konuşma yazılarını ekranda göster
    "background": True,                # pencere kapanınca arka planda dinlemeye devam et
    "autostart": False,                # Windows açılınca arka planda başlat
    "phone_enabled": False,            # telefon bağlantısı (aynı Wi-Fi, QR kod)
    "phone_port": 8765,
    "phone_token": "",
    "show_brief": False,               # (kullanılmıyor) haberler ana ekranda kendiliğinden açılmaz
    # Müzik: youtube | ytmusic | spotify
    "music_source": "youtube",
    "sleep_words": "uyu, uyku moduna geç, beklemeye geç",
}


def resource(*parts: str) -> str:
    """Paketlenmiş (PyInstaller) ya da kaynak koddan çalışırken dosya yolu."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def data_dir() -> Path:
    root = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    p = Path(root) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self.path = data_dir() / "settings.json"
        self.data = dict(DEFAULTS)
        try:
            if self.path.exists():
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                self.data.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def update(self, values: dict):
        with self._lock:
            for k, v in (values or {}).items():
                if k not in DEFAULTS:
                    continue
                d = DEFAULTS[k]
                try:
                    if isinstance(d, bool):
                        v = bool(v)
                    elif isinstance(d, int) and not isinstance(d, bool):
                        v = int(float(v))
                    elif isinstance(d, float):
                        v = float(v)
                    else:
                        v = str(v).strip()
                except (TypeError, ValueError):
                    continue
                self.data[k] = v
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def words(self, key):
        return [w.strip() for w in str(self.get(key, "")).split(",") if w.strip()]

    def public(self):
        """Arayüze gönderilecek ayarlar (anahtarlar dahil — yalnızca yerel pencere görür)."""
        return dict(self.data)
