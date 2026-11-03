"""Hata kaydı: %APPDATA%\\NOVA\\nova.log — bir sorun olursa bu dosyaya bak."""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .config import data_dir  # noqa: F401  (main.py de kullanır)


def setup(debug=False) -> str:
    path = data_dir() / "nova.log"
    handlers = [RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")]
    if sys.stdout is not None:  # --windowed EXE'de konsol yok
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("nova")
    for noisy in ("urllib3", "asyncio", "PIL", "websockets", "aiohttp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def hook(exc_type, exc, tb):
        log.critical("Yakalanmayan hata", exc_info=(exc_type, exc, tb))

    sys.excepthook = hook
    try:  # Python'u çökerten yerel (native) hataları da kaydet
        import faulthandler
        global _CRASH_FILE
        _CRASH_FILE = open(data_dir() / "nova-cokme.log", "a", encoding="utf-8")
        faulthandler.enable(_CRASH_FILE)
    except Exception:
        pass
    threading.excepthook = lambda a: log.critical("İş parçacığı hatası (%s)", a.thread and a.thread.name,
                                                  exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    return str(path)
