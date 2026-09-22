#!/usr/bin/env python3
"""Lanceur desktop nextevents (Windows portable).

Démarre le serveur webui en local (127.0.0.1) et ouvre le navigateur.
Les données vivent dans ./data à côté de l'exécutable ; le rendu passe
par l'Edge installé (canal Playwright "msedge") — aucun téléchargement
de navigateur requis.

L'app est auto-contenue : OUT_DIR/SETTINGS_FILE et les caches sont
redirigés via variables d'environnement *avant* l'import de nextevents.
"""

import os
import sys
import threading
import webbrowser
from pathlib import Path

if getattr(sys, "frozen", False):
    # bundle PyInstaller : exe à la racine, code dans _internal/
    BASE = Path(sys.executable).resolve().parent
    ASSETS = Path(sys._MEIPASS) / "assets"
else:
    BASE = Path(__file__).resolve().parent
    ASSETS = BASE / "upstream" / "assets"
    sys.path.insert(0, str(BASE / "upstream"))

DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

os.environ.setdefault("OUT_DIR", str(DATA / "diaporama"))
os.environ.setdefault("SETTINGS_FILE", str(DATA / "settings.json"))
os.environ.setdefault("NEXTEVENTS_ASSET_DIR", str(ASSETS))
os.environ.setdefault("NEXTEVENTS_FONT_DIR", str(DATA / "fonts"))
os.environ.setdefault("NEXTEVENTS_CACHE_DIR", str(DATA / "cache"))
os.environ.setdefault("NEXTEVENTS_BROWSER_CHANNEL", "msedge")
PORT = int(os.environ.get("PORT", "8095"))


def _open_when_ready():
    """Ouvre le navigateur dès que le serveur répond."""
    import time
    import urllib.request
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1)
            break
        except Exception:
            time.sleep(0.3)
    else:
        return
    webbrowser.open(f"http://127.0.0.1:{PORT}/")


def main():
    from nextevents.runner import scheduler
    from nextevents.settings import load_settings
    from nextevents.webapp import app

    load_settings()
    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=_open_when_ready, daemon=True).start()
    print(f"Nextevents — http://127.0.0.1:{PORT}  (Ctrl+C pour quitter)")
    app.run(host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
