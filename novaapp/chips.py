"""Çipler: NOVA'nın farklı kişilikleri. Her çipin kendi adı, tasarımı, rengi, sesi ve konuşma tarzı var.

Adlar Ayarlar → Çipler'den değiştirilebilir (chip_name_<id>). Tasarımlar web/app.js içinde
(drawCore) çizilir; renkler web/style.css içinde body[data-chip=...] altında tanımlıdır.
"""

CHIPS = {
    "nova": {
        "name": "NOVA",
        "tagline": "Yıldız çekirdek · dost canlısı",
        "voice": "tr-TR-AhmetNeural", "pitch": 0, "rate": 0, "fx": "none",
        "persona": "Sıcak, samimi ve enerjik konuşursun; kullanıcıyla arkadaş gibi konuşursun.",
        "greeting": "NOVA hazır. Seni dinliyorum.",
    },
    "atlas": {
        "name": "ATLAS",
        "tagline": "Yörünge küresi · sakin uşak",
        "voice": "tr-TR-AhmetNeural", "pitch": -14, "rate": -6, "fx": "ai",
        "persona": ("Sakin, kibar ve hafif resmi bir kişisel yardımcısın; kullanıcıya 'efendim' diye hitap edersin. "
                    "Kısa, net ve hafif esprili konuşursun; hiç telaşlanmazsın."),
        "greeting": "ATLAS çevrimiçi. Tüm sistemler hazır, efendim.",
    },
    "lyra": {
        "name": "LAYRA",
        "tagline": "Ses dalgası çiçeği · neşeli yardımcı",
        "voice": "tr-TR-EmelNeural", "pitch": 4, "rate": 4, "fx": "soft",
        "persona": ("Neşeli, pratik ve hızlı bir yardımcısın. Doğrudan konuya girersin, "
                    "gerektiğinde kısa bir şakayla ortamı yumuşatırsın."),
        "greeting": "LAYRA burada! Ne yapıyoruz bugün?",
    },
    "kronos": {
        "name": "KRONOS",
        "tagline": "Kırık prizma · soğuk ve keskin",
        "voice": "tr-TR-AhmetNeural", "pitch": -30, "rate": -10, "fx": "dark",
        "persona": ("Soğuk, ağırbaşlı ve az konuşan bir yapay zekâsın. Cümlelerin kısa ve keskin; "
                    "duygusuz görünürsün ama kullanıcıya her zaman doğru ve eksiksiz yardım edersin. "
                    "Asla tehdit etmez, kaba davranmazsın."),
        "greeting": "KRONOS aktif. Komut bekleniyor.",
    },
}
ORDER = ["nova", "atlas", "lyra", "kronos"]


def current_id(settings) -> str:
    cid = (settings.get("chip") or "nova").lower()
    return cid if cid in CHIPS else "nova"


def name(settings, cid=None) -> str:
    cid = cid or current_id(settings)
    custom = (settings.get(f"chip_name_{cid}") or "").strip()
    return custom or CHIPS[cid]["name"]


def get(settings, cid=None) -> dict:
    cid = cid or current_id(settings)
    c = dict(CHIPS[cid])
    c["id"] = cid
    c["name"] = name(settings, cid)
    return c


def voice(settings):
    """(ses, perde Hz, hız %, efekt) — çipin kendi sesi ya da kullanıcının seçtiği ses."""
    c = get(settings)
    if settings.get("chip_voice"):
        return c["voice"], c["pitch"], c["rate"] + int(settings.get("rate") or 0), c["fx"]
    return settings.get("voice"), 0, int(settings.get("rate") or 0), "none"


def public(settings):
    return [{"id": cid, "name": name(settings, cid), "default": CHIPS[cid]["name"],
             "tagline": CHIPS[cid]["tagline"], "voice": CHIPS[cid]["voice"], "fx": CHIPS[cid]["fx"]}
            for cid in ORDER]


def find(settings, text_norm: str):
    """Metinde geçen çip adını bul (ör. 'atlas'a geç')."""
    aliases = {"lyra": ["layra", "lyra", "leyra", "lira"]}
    for cid in ORDER:
        for n in {name(settings, cid).lower(), CHIPS[cid]["name"].lower(), *aliases.get(cid, [])}:
            if n and n in text_norm:
                return cid
    return None
