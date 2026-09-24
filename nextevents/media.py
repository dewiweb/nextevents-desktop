"""Médias : fontes du site, images d'événements, cache, résolution OpenAgenda."""

import base64
import json
import re
import threading
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .paths import FONT_DIR, CACHE_DIR, OA_MAP_FILE
from .scrape import BASE, get

FONTS = {
    "regular": (
        "OldschoolGrotesk-Regular-subset.914288c7.woff2",
        "/build/app/shop/fonts/OldschoolGrotesk-Regular-subset.914288c7.woff2",
    ),
    "medium": (
        "OldschoolGrotesk-Medium-subset.1b1f1e8e.woff2",
        "/build/app/shop/fonts/OldschoolGrotesk-Medium-subset.1b1f1e8e.woff2",
    ),
}

_OA_LOCK = threading.Lock()


def b64_file(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def ensure_fonts():
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, (fname, url) in FONTS.items():
        p = FONT_DIR / fname
        if not p.exists():
            print(f"  fonte {fname}")
            p.write_bytes(get(BASE + url).content)
        out[name] = b64_file(p)
    return out


def openagenda_image(uid):
    """Résout l'image originale d'un événement OpenAgenda à partir de son
    UID (extrait de l'URL /media/.../open-agenda/<uid>-... du site).
    Retourne l'URL img.openagenda.com en pleine résolution, ou None.
    La correspondance uid → URL est mise en cache (page ~470 Ko)."""
    try:
        m = json.loads(OA_MAP_FILE.read_text())
    except Exception:
        m = {}
    if uid in m:
        return m[uid]
    try:
        h = get(f"https://openagenda.com/events/{uid}").text
        og = next(
            (
                re.search(r'content="([^"]+)"', t).group(1)
                for t in re.findall(r"<meta[^>]+>", h)
                if "og:image" in t and 'content="' in t
            ),
            None,
        )
        if og and "img.openagenda.com" in og:
            url = re.sub(r"/u/[^/]+/", "/u/3840x0/", og)
            with _OA_LOCK:
                try:
                    m = json.loads(OA_MAP_FILE.read_text())
                except Exception:
                    m = {}
                m[uid] = url
                OA_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
                OA_MAP_FILE.write_text(json.dumps(m, indent=0))
            return url
    except Exception as e:
        print(f"  ! openagenda {uid} : {e}")
    return None


def download_image(ev):
    """Télécharge l'image et la retourne en data URI (HTML autonome).
    Cache local : les URLs d'images sont versionnées, on ne retélécharge
    jamais deux fois la même (sobriété)."""
    url = ev.get("image") or ev.get("card_img")
    uid = re.search(r"open-agenda/(\d+)", url or "")
    # candidats dans l'ordre : original OpenAgenda pleine résolution,
    # puis repli sur l'image du site si son téléchargement échoue
    urls = ([openagenda_image(uid.group(1))] if uid else []) + [url]
    for u in urls:
        if not u:
            continue
        cache = CACHE_DIR / Path(urlsplit(u).path).name
        try:
            if cache.exists():
                data, mime = cache.read_bytes(), "image/jpeg"
            else:
                r = get(u)
                data = r.content
                mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
            ev["img_data"] = f"data:{mime};base64,{base64.b64encode(data).decode()}"
            return ev
        except Exception as e:
            print(f"  ! image KO {u} : {e}")
    ev["img_data"] = None
    return ev
