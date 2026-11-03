"""Hakkında bölümünün tek kaynağı. Hesap adları Ayarlar'dan değiştirilebilir."""

from . import APP_NAME, VERSION


def _clean(user: str) -> str:
    return (user or "").strip().lstrip("@").strip("/") or "xsametsahinx"


def build(settings=None) -> dict:
    get = (lambda k: settings.get(k)) if settings else (lambda k: "")
    ig, tt, yt = (_clean(get(k)) for k in ("instagram_user", "tiktok_user", "youtube_user"))
    gh = (get("github_user") or "pepsicosamet-arch").strip().lstrip("@").strip("/")
    return {
        "app": APP_NAME,
        "version": VERSION,
        "maker": "Samet Şahin",
        "role": "NOVA'yı tasarlayan ve geliştiren kişi",
        "bio": (
            "NOVA'yı sıfırdan tasarlayıp geliştirdim. Yeni özellikleri, "
            "geliştirme sürecini ve perde arkasını sosyal medya hesaplarımda paylaşıyorum."
        ),
        "handle": "@" + ig,
        "socials": [
            {"id": "instagram", "name": "Instagram", "user": "@" + ig,
             "url": f"https://www.instagram.com/{ig}/", "note": "Yeni özellikler ve perde arkası"},
            {"id": "tiktok", "name": "TikTok", "user": "@" + tt,
             "url": f"https://www.tiktok.com/@{tt}", "note": "Kısa videolar ve denemeler"},
            {"id": "youtube", "name": "YouTube", "user": "@" + yt,
             "url": f"https://www.youtube.com/@{yt}", "note": "Uzun videolar ve anlatımlar"},
            {"id": "github", "name": "GitHub", "user": gh,
             "url": f"https://github.com/{gh}", "note": "Projeler ve kaynak kod"},
        ],
        "copyright": "© 2026 Samet Şahin. Tüm hakları saklıdır.",
    }


ABOUT = build()
