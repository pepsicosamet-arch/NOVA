"""WhatsApp / Telegram masaüstü uygulamasını Windows UI Otomasyonu ile kullanarak mesaj gönderir.

Numara gerekmez: uygulamanın kendi arama kutusuna kişinin adı yazılır, sonuçlardan o sohbet
seçilir, mesaj kutusuna metin yapıştırılır ve Enter'a basılır. Her adım nova.log'a yazılır;
bir adım başarısız olursa kullanıcıya hangi adımda takıldığı söylenir.
"""

import logging
import re
import time

from . import social

log = logging.getLogger("nova.wa")

SEARCH_NAMES = ("Ara veya yeni sohbet başlat", "Search or start a new chat", "Sohbet ara", "Search", "Ara",
                "Arama", "Search for chats", "Kişi veya sohbet ara")
BOX_NAMES = ("Bir mesaj yazın", "Mesaj yazın", "Type a message", "Bir mesaj yaz", "Mesaj yaz", "Message",
             "Write a message", "Mesaj")


def _uia():
    try:
        import uiautomation as auto
        auto.SetGlobalSearchTimeout(2)
        return auto
    except Exception as e:  # paket yok ya da Windows değil
        log.warning("UI Otomasyonu kullanılamıyor: %s", e)
        return None


def _paste(text):
    social.set_clipboard(text)
    time.sleep(0.15)
    social._keys(social.VK_CONTROL, social.VK_V)


def _find_edit(win, names, depth=60):
    for nm in names:
        c = win.EditControl(searchDepth=depth, SubName=nm)
        if c.Exists(0.4, 0.1):
            return c
    return None


def _chat_item(win, name):
    rx = re.compile(re.escape(name), re.I)
    for ctl_type in ("ListItemControl", "DataItemControl", "ButtonControl", "TextControl"):
        try:
            ctl = getattr(win, ctl_type)(searchDepth=60, Compare=lambda c, d: bool(rx.search(c.Name or "")))
            if ctl.Exists(1.5, 0.2):
                # arama kutusunun kendisini değil, sonuç öğesini istiyoruz
                if ctl_type == "TextControl":
                    parent = ctl.GetParentControl()
                    return parent or ctl
                return ctl
        except Exception:
            continue
    return None


def send(app: str, name: str, text: str, auto_send: bool = True, wait: float = 4.0):
    """(başarılı mı, kullanıcıya söylenecek metin)"""
    title = "WhatsApp" if app == "whatsapp" else "Telegram"
    social._open("whatsapp:" if app == "whatsapp" else "tg://")
    auto = _uia()
    if auto is None:
        return _keyboard_fallback(title, name, text, auto_send, wait)
    # NOVA bu işi arka plan iş parçacığında yapar; UI Otomasyonu (COM) her iş parçacığında başlatılmalı
    with auto.UIAutomationInitializerInThread():
        return _send_uia(auto, app, title, name, text, auto_send, wait)


def _send_uia(auto, app, title, name, text, auto_send, wait):
    steps = []
    try:
        win = auto.WindowControl(searchDepth=1, RegexName=rf"(?i).*{title}.*")
        if not win.Exists(max(6, wait + 6), 0.5):
            return False, f"{title} penceresi açılmadı. {title} uygulamasının açık ve giriş yapılmış olduğundan emin ol."
        try:
            win.SetActive()
        except Exception:
            pass
        social.focus_window(title)
        time.sleep(0.6)
        steps.append("pencere")

        # 1) arama kutusu
        search = _find_edit(win, SEARCH_NAMES)
        if search:
            search.Click(simulateMove=False)
        else:
            if app == "telegram":
                social._keys(0x1B); time.sleep(0.2)
            social._keys(social.VK_CONTROL, 0x46)       # Ctrl+F
        time.sleep(0.4)
        social._keys(social.VK_CONTROL, 0x41)            # Ctrl+A (eski aramayı sil)
        _paste(name)
        steps.append("arama")
        time.sleep(2.0)

        # 2) sohbeti aç
        item = _chat_item(win, name)
        if item:
            item.Click(simulateMove=False)
            steps.append("sohbet")
        else:
            log.warning("Sohbet öğesi bulunamadı, Enter deneniyor")
            social._keys(0x28); time.sleep(0.2)          # Aşağı ok
            social._keys(social.VK_RETURN)
            steps.append("sohbet?")
        time.sleep(1.3)

        # 3) mesaj kutusu
        box = _find_edit(win, BOX_NAMES)
        if box:
            box.Click(simulateMove=False)
            steps.append("kutu")
        else:
            log.warning("Mesaj kutusu bulunamadı; odaktaki yere yazılıyor")
        time.sleep(0.3)
        _paste(text)
        time.sleep(0.4)
        if auto_send:
            social._keys(social.VK_RETURN)
            steps.append("gönderildi")
        log.info("WhatsApp otomasyonu adımları: %s", " → ".join(steps))
        if not item:
            return True, (f"{name} sohbetini tam bulamadım, ilk sonuca yazdım. {title}'ta doğru kişiye gidip "
                          f"gitmediğine bak; gitmediyse kişinin {title}'ta kayıtlı adını söyle.")
        return True, (f"{title}'tan {name} kişisine gönderdim." if auto_send else
                      f"Mesajı {name} sohbetine yazdım, göndermek için Enter'a bas.")
    except Exception as e:
        log.exception("WhatsApp otomasyonu hatası (adımlar: %s)", " → ".join(steps))
        return False, f"{title} ile gönderirken bir sorun çıktı ({e})."


def _keyboard_fallback(title, name, text, auto_send, wait):
    time.sleep(wait)
    social.focus_window(title)
    time.sleep(0.5)
    social._keys(social.VK_CONTROL, 0x46)
    time.sleep(0.5)
    social._keys(social.VK_CONTROL, 0x41)
    _paste(name)
    time.sleep(2.0)
    social._keys(0x28); time.sleep(0.2)
    social._keys(social.VK_RETURN)
    time.sleep(1.4)
    _paste(text)
    if auto_send:
        time.sleep(0.4)
        social._keys(social.VK_RETURN)
    return True, f"{title}'tan {name} kişisine gönderdim."
