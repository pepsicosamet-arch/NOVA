"""GitHub Releases üzerinden otomatik güncelleme.

Yeni sürüm yayınlamak için: GitHub'da v1.3.1 gibi bir etiket (tag) gönder. Actions derleyip
NOVA-x.y.z-Windows-Setup.exe dosyasını sürüme ekler. NOVA açılışta bunu görür ve tek tıkla kurar.
"""

import logging
import os
import re
import subprocess
import sys
import tempfile

import requests

from . import VERSION

log = logging.getLogger("nova.updater")
DEFAULT_REPO = "pepsicosamet-arch/nova"


def _ver(s: str):
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def check(repo: str = DEFAULT_REPO):
    repo = (repo or DEFAULT_REPO).strip().strip("/")
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", timeout=10,
                         headers={"Accept": "application/vnd.github+json", "User-Agent": "NOVA-Asistan"})
    except requests.RequestException as e:
        return {"ok": False, "error": f"GitHub'a ulaşılamadı: {e}"}
    if r.status_code == 404:
        return {"ok": True, "available": False, "current": VERSION, "note": "Henüz yayınlanmış sürüm yok."}
    if r.status_code != 200:
        return {"ok": False, "error": f"GitHub hata verdi (kod {r.status_code})"}
    j = r.json()
    latest = j.get("tag_name", "").lstrip("vV")
    asset = next((a for a in j.get("assets", []) if a["name"].lower().endswith(".exe")), None)
    available = _ver(latest) > _ver(VERSION) and asset is not None
    return {"ok": True, "available": available, "current": VERSION, "latest": latest,
            "notes": (j.get("body") or "")[:1500], "url": asset["browser_download_url"] if asset else None,
            "size": asset["size"] if asset else 0, "page": j.get("html_url")}


def download_and_install(url: str, progress=None) -> str:
    """Kurulum dosyasını indirir ve sessiz kurulumu başlatır. Çağıran taraf NOVA'yı kapatmalıdır."""
    if not url or not url.startswith("https://github.com/"):
        raise ValueError("Geçersiz güncelleme adresi")
    path = os.path.join(tempfile.gettempdir(), "NOVA-Guncelleme-Setup.exe")
    with requests.get(url, stream=True, timeout=60, headers={"User-Agent": "NOVA-Asistan"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(round(done * 100 / total))
    log.info("Güncelleme indirildi: %s", path)
    if sys.platform.startswith("win"):
        subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                         creationflags=0x00000008)  # DETACHED_PROCESS
    return path
