#!/usr/bin/env python3
"""Lanceur desktop nextevents (Windows portable).

App en zone de notification : le serveur webui tourne en arrière-plan
sur 127.0.0.1:8095, le rendu passe par l'Edge installé (canal Playwright
"msedge" — aucun téléchargement de navigateur).

L'utilisateur pilote tout depuis l'icône : générer, choisir le dossier
de destination (disque local, lecteur réseau mappé ou UNC — Windows
gère l'auth SMB), ouvrir les diapos. La webui reste accessible via
« Réglages avancés » pour la configuration experte (FTP/SMB, diapo du
jour, formats…).

Données dans ./data à côté de l'exe ; journal dans ./data/app.log.
--diag : diagnostique le lancement d'Edge (data/diag.log).
"""

import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

if getattr(sys, "frozen", False):
    # bundle PyInstaller : exe à la racine, code dans _internal/
    BASE = Path(sys.executable).resolve().parent
    ASSETS = Path(sys._MEIPASS) / "assets"
    ICON = Path(sys._MEIPASS) / "nextevents.ico"
else:
    BASE = Path(__file__).resolve().parent
    ASSETS = BASE / "upstream" / "assets"
    ICON = BASE / "nextevents.ico"
    sys.path.insert(0, str(BASE / "upstream"))

DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

os.environ.setdefault("OUT_DIR", str(DATA / "diaporama"))
os.environ.setdefault("SETTINGS_FILE", str(DATA / "settings.json"))
os.environ.setdefault("NEXTEVENTS_ASSET_DIR", str(ASSETS))
os.environ.setdefault("NEXTEVENTS_FONT_DIR", str(DATA / "fonts"))
os.environ.setdefault("NEXTEVENTS_CACHE_DIR", str(DATA / "cache"))
# Chromium headless embarqué dans le bundle (driver-appairé, immunisé
# aux maj Edge). Pour forcer l'Edge système : NEXTEVENTS_BROWSER_CHANNEL=msedge
# os.environ.setdefault("NEXTEVENTS_BROWSER_CHANNEL", "msedge")
PORT = int(os.environ.get("PORT", "8095"))
OUT_DIR = Path(os.environ["OUT_DIR"])

# Les réseaux d'entreprise interceptent TLS avec une CA interne :
# on fait confiance au magasin Windows (comme Edge) plutôt qu'à certifi.
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


def _api(path, body=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


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
                v = subprocess.run([exe, "--version"], capture_output=True,
                                   text=True, timeout=15)
                w(f"  --version -> {v.stdout.strip()} {v.stderr.strip()}")
            except Exception as e:
                w(f"  --version failed: {e}")
            try:
                d = subprocess.run(
                    [exe, "--headless", "--dump-dom", "about:blank"],
                    capture_output=True, text=True, timeout=30)
                w(f"  headless dump-dom -> rc={d.returncode} "
                  f"len={len(d.stdout)} err={d.stderr.strip()[:300]}")
            except Exception as e:
                w(f"  headless dump-dom failed: {e}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        w(f"playwright import: {e}")
        return

    for label, kw in [
        ("chromium headless (embarqué)", dict()),
        ("msedge headless", dict(channel="msedge")),
        ("msedge headless +disable-gpu",
         dict(channel="msedge", args=["--disable-gpu"])),
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


def _pick_dir_subprocess(outfile):
    """Point d'entrée `nextevents.exe --pick-dir <fichier>` : affiche le
    sélecteur de dossier natif et écrit le choix dans <fichier>.

    Tourne dans un processus dédié — sa boucle de messages est isolée
    (pas de gel depuis le thread du tray) et sans console."""
    import pythoncom
    from win32com.shell import shell, shellcon
    pythoncom.CoInitialize()
    try:
        # 0x40 = BIF_NEWDIALOGSTYLE (absent de shellcon) ;
        # BIF_EDITBOX permet de coller un chemin UNC directement
        pidl, _, _ = shell.SHBrowseForFolder(
            0, None, "Dossier de destination des diapos",
            shellcon.BIF_RETURNONLYFSDIRS | shellcon.BIF_EDITBOX | 0x40)
        if pidl:
            path = shell.SHGetPathFromIDList(pidl)
            if isinstance(path, bytes):
                path = path.decode("mbcs")
            Path(outfile).write_text(path, encoding="utf-8")
    finally:
        pythoncom.CoUninitialize()


def _pick_dir(icon):
    """Explorateur Windows → dossier de destination (local/mappé/UNC) :
    relance l'exe en mode --pick-dir pour isoler le dialogue."""
    import subprocess
    import tempfile
    d = None
    try:
        with tempfile.NamedTemporaryFile(
                suffix=".txt", delete=False) as tf:
            outfile = tf.name
        if getattr(sys, "frozen", False):
            cmd = [str(sys.executable), "--pick-dir", outfile]
        else:
            cmd = [sys.executable, str(Path(__file__).resolve()),
                   "--pick-dir", outfile]
        subprocess.run(cmd, timeout=300)
        d = Path(outfile).read_text(encoding="utf-8").strip() or None
        Path(outfile).unlink(missing_ok=True)
    except Exception:
        pass
    if d:
        # les diapos sont générées directement dedans — une seule copie
        _api("/api/settings", {"out_dir": d})
        icon.notify(f"Dossier de sortie : {d}", "Nextevents")


def _run_server():
    from nextevents.runner import scheduler
    from nextevents.settings import load_settings
    from nextevents.webapp import app

    load_settings()
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host="127.0.0.1", port=PORT, use_reloader=False)


def _poll_status(icon):
    """Met à jour l'infobulle et notifie les fins de génération."""
    was_running = False
    while True:
        try:
            s = _api("/api/status")
            n = s["slides_count"]
            last = s["last_run_iso"] or "jamais"
            icon.title = (f"Nextevents — {n} diapos · {last}"
                          + (" · génération…" if s["running"] else ""))
            if was_running and not s["running"]:
                if s["last_error"]:
                    icon.notify(f"Échec : {s['last_error'][:200]}",
                                "Nextevents — génération")
                else:
                    icon.notify(f"{n} diapos générées",
                                "Nextevents — génération terminée")
            was_running = s["running"]
        except Exception:
            icon.title = "Nextevents"
        time.sleep(5)


def _tray():
    import pystray
    from PIL import Image

    icon = pystray.Icon(
        "nextevents", Image.open(ICON), "Nextevents",
        menu=pystray.Menu(
            pystray.MenuItem(
                "Générer maintenant",
                lambda i, it: _api("/api/run", {}),
                default=True),
            pystray.MenuItem(
                "Dossier de destination…",
                lambda i, it: _pick_dir(i)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Ouvrir les diapos",
                lambda i, it: os.startfile(
                    _api("/api/status")["settings"].get("out_dir")
                    or OUT_DIR)),
            pystray.MenuItem(
                "Réglages avancés",
                lambda i, it: webbrowser.open(f"http://127.0.0.1:{PORT}/")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", lambda i, it: i.stop()),
        ))
    threading.Thread(target=_poll_status, args=(icon,), daemon=True).start()
    icon.run()


def main():
    threading.Thread(target=_run_server, daemon=True).start()
    if getattr(sys, "frozen", False):
        _tray()
    else:
        # mode dev : console + ouverture auto de la webui
        def _open_when_ready():
            for _ in range(100):
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{PORT}/", timeout=1)
                    break
                except Exception:
                    time.sleep(0.3)
            else:
                return
            webbrowser.open(f"http://127.0.0.1:{PORT}/")
        threading.Thread(target=_open_when_ready, daemon=True).start()
        print(f"Nextevents — http://127.0.0.1:{PORT}  (Ctrl+C pour quitter)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    if "--diag" in sys.argv:
        _diag()
    elif "--pick-dir" in sys.argv:
        _pick_dir_subprocess(sys.argv[sys.argv.index("--pick-dir") + 1])
    else:
        main()
