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

# Les réseaux d'entreprise interceptent TLS avec une CA interne :
# on fait confiance au magasin Windows (comme Edge) plutôt qu'à certifi.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass


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


def _diag():
    """Diagnostique le lancement d'Edge — écrit data/diag.log."""
    import subprocess
    import traceback

    log = DATA / "diag.log"

    def w(msg):
        print(msg)
        with open(log, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")

    log.unlink(missing_ok=True)
    w(f"python {sys.version}  frozen={getattr(sys, 'frozen', False)}")
    for exe in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        p = Path(exe)
        w(f"{exe}: exists={p.exists()}")
        if p.exists():
            try:
                v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15)
                w(f"  --version -> {v.stdout.strip()} {v.stderr.strip()}")
            except Exception as e:
                w(f"  --version failed: {e}")
            try:
                d = subprocess.run([exe, "--headless", "--dump-dom", "about:blank"],
                                   capture_output=True, text=True, timeout=30)
                w(f"  headless dump-dom -> rc={d.returncode} len={len(d.stdout)} err={d.stderr.strip()[:300]}")
            except Exception as e:
                w(f"  headless dump-dom failed: {e}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        w(f"playwright import: {e}")
        return

    for label, kw in [
        ("msedge headless", dict(channel="msedge")),
        ("msedge headless +disable-gpu", dict(channel="msedge", args=["--disable-gpu"])),
        ("msedge headed", dict(channel="msedge", headless=False)),
        ("chromium headless", dict()),
    ]:
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(**kw)
                pg = b.new_page()
                pg.set_content("<h1>diag</h1>")
                pg.screenshot(path=str(DATA / "diag.png"))
                b.close()
            w(f"launch {label}: OK")
            break
        except Exception:
            tb = traceback.format_exc()
            print(tb.splitlines()[-1])
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"launch {label}: FAILED\n{tb}\n")
    w(f"diag écrit dans {log}")


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
    if "--diag" in sys.argv:
        _diag()
    else:
        main()
