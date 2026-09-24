#!/usr/bin/env python3
"""App desktop nextevents (Windows portable / AppImage Linux).

UI native Qt (PySide6 Widgets) : fenêtre de contrôle (génération,
réglages, destinations FTP/SMB, diapo du jour, galerie, journal),
player de diaporama plein écran, icône de zone de notification
(Win32 / SNI) et planificateur. Toute la logique métier est embarquée
dans le package local `nextevents/` — pas de serveur web, pas de
dépendance à un dépôt externe.

Données dans ./data à côté de l'exe/AppImage ; journal dans
./data/app.log. --diag : diagnostique le rendu (data/diag.log).
"""

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # bundle PyInstaller : exe à la racine, code dans _internal/
    # AppImage : l'exécutable est dans le mount squashfs (lecture seule)
    # → données à côté du fichier .AppImage, sémantique portable
    # identique à Windows.
    if "APPIMAGE" in os.environ:
        BASE = Path(os.environ["APPIMAGE"]).resolve().parent
    else:
        BASE = Path(sys.executable).resolve().parent
    ASSETS = Path(sys._MEIPASS) / "assets"
    ICON = Path(sys._MEIPASS) / "nextevents.png"
else:
    BASE = Path(__file__).resolve().parent
    ASSETS = BASE / "assets"
    ICON = BASE / "appimage" / "nextevents.png"

DATA = BASE / "data"
try:
    DATA.mkdir(exist_ok=True)
except OSError:
    # exe/AppImage dans un dossier en lecture seule → repli profil
    DATA = Path.home() / ".nextevents"
    DATA.mkdir(exist_ok=True)

os.environ.setdefault("OUT_DIR", str(DATA / "diaporama"))
os.environ.setdefault("SETTINGS_FILE", str(DATA / "settings.json"))
os.environ.setdefault("NEXTEVENTS_ASSET_DIR", str(ASSETS))
os.environ.setdefault("NEXTEVENTS_FONT_DIR", str(DATA / "fonts"))
os.environ.setdefault("NEXTEVENTS_CACHE_DIR", str(DATA / "cache"))

# Amorce les fontes embarquées (assets/fonts) dans data/fonts : rendu
# correct hors-ligne dès le premier démarrage ; le dossier reste
# inscriptible pour un éventuel re-téléchargement.
_seed = ASSETS / "fonts"
if _seed.is_dir():
    _fonts = DATA / "fonts"
    _fonts.mkdir(exist_ok=True)
    for _f in _seed.iterdir():
        _d = _fonts / _f.name
        if not _d.exists():
            _d.write_bytes(_f.read_bytes())
# Chromium headless embarqué dans le bundle (driver-appairé, immunisé
# aux maj Edge). Pour forcer l'Edge système : NEXTEVENTS_BROWSER_CHANNEL=msedge
# os.environ.setdefault("NEXTEVENTS_BROWSER_CHANNEL", "msedge")

# Les réseaux d'entreprise interceptent TLS avec une CA interne :
# on fait confiance au magasin système plutôt qu'à certifi.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

if getattr(sys, "frozen", False):
    # Mode fenêtré : pas de console — journal dans data/app.log (UTF-8,
    # évite aussi les crashs d'encodage cp1252 sur les symboles du journal)
    _log = open(DATA / "app.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log


def _diag():
    """Diagnostique le rendu navigateur — écrit data/diag.log."""
    import subprocess
    import traceback

    log = DATA / "diag.log"

    def w(msg):
        print(msg)
        with open(log, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")

    log.unlink(missing_ok=True)
    w(f"python {sys.version}  frozen={getattr(sys, 'frozen', False)}")
    if sys.platform == "win32":
        exes = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
    else:
        exes = ["/usr/bin/google-chrome", "/usr/bin/chromium",
                "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"]
    for exe in exes:
        p = Path(exe)
        w(f"{exe}: exists={p.exists()}")
        if p.exists():
            try:
                v = subprocess.run([exe, "--version"], capture_output=True,
                                   text=True, timeout=15)
                w(f"  --version -> {v.stdout.strip()} {v.stderr.strip()}")
            except Exception as e:
                w(f"  --version failed: {e}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        w(f"playwright import: {e}")
        return

    attempts = [("chromium headless (embarqué)", dict())]
    if sys.platform == "win32":
        attempts += [
            ("msedge headless", dict(channel="msedge")),
            ("msedge headless +disable-gpu",
             dict(channel="msedge", args=["--disable-gpu"])),
        ]
    else:
        attempts += [("chrome système headless", dict(channel="chrome"))]
    for label, kw in attempts:
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
    from ui.app import run
    run(ICON)


if __name__ == "__main__":
    if "--diag" in sys.argv:
        _diag()
    else:
        main()
