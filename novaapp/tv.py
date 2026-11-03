"""Canlı TV: kanalların resmî canlı yayın sayfalarını uygulama penceresinde açar.

Yayınlar kanalların kendi sitelerinden izlenir; NOVA yayını kopyalamaz ya da kaydetmez.
Bir adres değişirse yalnızca bu listeyi güncellemek yeterli.
"""

import re
import subprocess
import sys
import webbrowser

CHANNELS = [
    # id, ad, grup, renk, resmî canlı yayın sayfası, sesli komutta duyulabilecek adlar
    ("trt1", "TRT 1", "Ulusal", "#1f6feb", "https://www.tabii.com/tr/watch/live/trt1", ["trt 1", "trt bir", "trt1"]),
    ("atv", "ATV", "Ulusal", "#0aa5e8", "https://www.atv.com.tr/canli-yayin", ["atv", "a tv"]),
    ("show", "Show TV", "Ulusal", "#e3262f", "https://www.showtv.com.tr/canli-yayin", ["show tv", "şov tv", "show"]),
    ("star", "Star TV", "Ulusal", "#f2b705", "https://www.startv.com.tr/canli-yayin", ["star tv", "star"]),
    ("kanald", "Kanal D", "Ulusal", "#2b59c3", "https://www.kanald.com.tr/canli-yayin", ["kanal d", "kanal de"]),
    ("now", "NOW", "Ulusal", "#ff5a1f", "https://www.nowtv.com.tr/canli-yayin", ["now tv", "now", "fox tv"]),
    ("tv8", "TV8", "Ulusal", "#8a2be2", "https://www.tv8.com.tr/canli-yayin", ["tv8", "tv 8", "tv sekiz"]),
    ("kanal7", "Kanal 7", "Ulusal", "#c2185b", "https://www.kanal7.com/canli-izle", ["kanal 7", "kanal yedi"]),
    ("trthaber", "TRT Haber", "Haber", "#d32f2f", "https://www.tabii.com/tr/watch/live/trthaber", ["trt haber"]),
    ("ntv", "NTV", "Haber", "#0057b8", "https://www.ntv.com.tr/canli-yayin/ntv", ["ntv", "en tv"]),
    ("haberturk", "Habertürk", "Haber", "#b71c1c", "https://www.haberturk.com/canliyayin", ["habertürk", "haber türk"]),
    ("cnnturk", "CNN Türk", "Haber", "#cc0000", "https://www.cnnturk.com/canli-yayin", ["cnn türk", "cnn"]),
    ("ahaber", "A Haber", "Haber", "#e53935", "https://www.ahaber.com.tr/canli-yayin", ["a haber"]),
    ("halktv", "Halk TV", "Haber", "#e65100", "https://halktv.com.tr/canli-yayin", ["halk tv"]),
    ("sozcu", "Sözcü TV", "Haber", "#424242", "https://www.szctv.com.tr/canli-yayin-izle", ["sözcü tv", "sözcü"]),
    ("tv100", "tv100", "Haber", "#00897b", "https://www.tv100.com/canli-yayin", ["tv100", "tv 100", "tv yüz"]),
    ("trtspor", "TRT Spor", "Spor ve çocuk", "#2e7d32", "https://www.tabii.com/tr/watch/live/trtspor", ["trt spor"]),
    ("trtcocuk", "TRT Çocuk", "Spor ve çocuk", "#fb8c00", "https://www.tabii.com/tr/watch/live/trtcocuk", ["trt çocuk"]),
]


def public():
    return [{"id": c[0], "name": c[1], "group": c[2], "color": c[3]} for c in CHANNELS]


def find(text_norm: str):
    best = None
    for c in CHANNELS:
        for alias in c[5]:
            if re.search(rf"(^|\s){re.escape(alias)}(\b|')", text_norm) and (not best or len(alias) > best[1]):
                best = (c, len(alias))
    return best[0] if best else None


def open_channel(cid: str):
    ch = next((c for c in CHANNELS if c[0] == cid), None)
    if not ch:
        return None
    url = ch[4]
    try:
        from .server import find_browser
        exe = find_browser()
        if exe:
            flags = 0x08000000 if sys.platform.startswith("win") else 0
            subprocess.Popen([exe, f"--app={url}", "--window-size=1280,760", "--autoplay-policy=no-user-gesture-required"],
                             creationflags=flags)
            return ch
    except Exception:
        pass
    webbrowser.open(url, new=2)
    return ch
