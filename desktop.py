#!/usr/bin/env python3
"""Lanceur desktop nextevents (Windows portable).

Démarre le serveur webui en local (127.0.0.1) et ouvre le navigateur.
Les données vivent dans ./data à côté de l'exécutable ; le rendu et la
fenêtre webui passent par le Chromium embarqué — hors GPO Edge et hors
proxy forcé du navigateur géré. Repli sur l'Edge du poste si absent.

L'app est auto-contenue : OUT_DIR/SETTINGS_FILE et les caches sont
redirigés via variables d'environnement *avant* l'import de nextevents.
"""

import os
import re
import sys
import threading
import webbrowser
from pathlib import Path

if getattr(sys, "frozen", False):
    # bundle PyInstaller : exe à la racine, code dans _internal/
    BASE = Path(sys.executable).resolve().parent
    ASSETS = Path(sys._MEIPASS) / "assets"
    BROWSERS = Path(sys._MEIPASS) / "ms-playwright"
    if BROWSERS.is_dir():
        # Chromium embarqué : hors GPO du navigateur géré
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS)
    else:
        os.environ.setdefault("NEXTEVENTS_BROWSER_CHANNEL", "msedge")
else:
    BASE = Path(__file__).resolve().parent
    ASSETS = BASE / "upstream" / "assets"
    sys.path.insert(0, str(BASE / "upstream"))
    os.environ.setdefault("NEXTEVENTS_BROWSER_CHANNEL", "msedge")

DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

os.environ.setdefault("OUT_DIR", str(DATA / "diaporama"))
os.environ.setdefault("SETTINGS_FILE", str(DATA / "settings.json"))
os.environ.setdefault("NEXTEVENTS_ASSET_DIR", str(ASSETS))
os.environ.setdefault("NEXTEVENTS_FONT_DIR", str(DATA / "fonts"))
os.environ.setdefault("NEXTEVENTS_CACHE_DIR", str(DATA / "cache"))
PORT = int(os.environ.get("PORT", "8095"))

# Les réseaux d'entreprise interceptent TLS avec une CA interne :
# on fait confiance au magasin Windows (comme Edge) plutôt qu'à certifi.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
_UI_PROC = None


def _find_edge():
    for exe in EDGE_PATHS:
        if Path(exe).exists():
            return exe
    return None


def _find_chromium():
    """Chromium embarqué dans le bundle (PLAYWRIGHT_BROWSERS_PATH)."""
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not root or not Path(root).is_dir():
        return None
    for pat in ("chromium-*/chrome-win*/chrome.exe",
                "chromium-*/chrome-linux*/chrome",
                "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"):
        exes = sorted(Path(root).glob(pat))
        if exes:
            return exes[-1]
    return None


def _open_ui(url):
    """Ouvre la webui dans une fenêtre dédiée, hors proxy d'entreprise.

    Le navigateur par défaut suit le PAC du poste, qui peut envoyer même
    127.0.0.1 au proxy → page bloquée. `--no-proxy-server` force le
    direct (la page est locale de toute façon). Le Chromium embarqué
    échappe en plus aux GPO Edge ; replis : Edge du poste, puis
    navigateur par défaut."""
    import subprocess

    exe = _find_chromium() or _find_edge()
    if exe:
        try:
            return subprocess.Popen([
                str(exe), f"--app={url}", "--no-proxy-server",
                f"--user-data-dir={DATA / 'ui-profile'}",
                "--no-first-run", "--no-default-browser-check",
            ])
        except Exception as e:
            print(f"fenêtre dédiée KO ({e}) — navigateur par défaut")
    webbrowser.open(url)
    return None


def _proxy_session():
    """Branche la session HTTP de nextevents sur le proxy d'entreprise.

    requests ne lit que le proxy *fixe* du registre Windows — pas les
    scripts PAC/WPAD. pypac résout le PAC du système ; l'auth proxy
    Negotiate/NTLM du compte ouvert passe par requests_negotiate_sspi.
    Dernier recours manuel : NEXTEVENTS_PROXY=http://proxy.dsi:3128.
    Sans PAC trouvé, PACSession se comporte comme une Session standard."""
    try:
        from pypac import PACSession
    except ImportError:
        return
    import nextevents.scrape as scrape
    try:
        from requests_negotiate_sspi import HttpNegotiateAuth
        s = PACSession(proxy_auth=HttpNegotiateAuth())
    except ImportError:
        s = PACSession()
    forced = os.environ.get("NEXTEVENTS_PROXY")
    if forced:
        s.proxies = {"http": forced, "https": forced}
    s.headers["User-Agent"] = scrape.UA
    scrape.session = s


def _open_when_ready():
    """Ouvre le navigateur dès que le serveur répond."""
    import socket
    import time
    for _ in range(100):
        try:
            # TCP brut : urllib passerait par le proxy éventuel du poste
            socket.create_connection(("127.0.0.1", PORT), timeout=1).close()
            break
        except OSError:
            time.sleep(0.3)
    else:
        return
    global _UI_PROC
    _UI_PROC = _open_ui(f"http://127.0.0.1:{PORT}/")


def _mask(v):
    """Masque un éventuel mot de passe dans une URL de proxy."""
    return re.sub(r"(://[^:/@]+):[^@]+@", r"\1:***@", str(v))


def _reg_values(hive, sub, want=None):
    """{nom: valeur} d'une clé de registre (want=None → toutes)."""
    import winreg

    out = {}
    with winreg.OpenKey(hive, sub) as k:
        i = 0
        while True:
            try:
                n, v, _ = winreg.EnumValue(k, i)
            except OSError:
                break
            i += 1
            if want is None or n in want:
                out[n] = _mask(v)
    return out


def _diag_policies(w):
    """Réglages proxy du poste (env, registre IE) et stratégies
    navigateur posées par GPO — un proxy imposé en *politique* Edge
    peut ignorer --no-proxy-server."""
    w("— proxy : variables d'env —")
    seen = False
    for v in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
              "http_proxy", "https_proxy", "no_proxy", "NEXTEVENTS_PROXY"):
        if os.environ.get(v):
            seen = True
            w(f"  {v}={_mask(os.environ[v])}")
    if not seen:
        w("  (aucune)")
    try:
        import winreg
    except ImportError:
        w("— registre/GPO : non-Windows —")
        return
    w("— proxy : registre Internet Settings —")
    want = {"ProxyEnable", "ProxyServer", "AutoConfigURL",
            "ProxyOverride", "AutoDetect", "ProxySettingsPerUser"}
    for hive, label in ((winreg.HKEY_CURRENT_USER, "HKCU"),
                        (winreg.HKEY_LOCAL_MACHINE, "HKLM")):
        for sub in (
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            r"Software\Policies\Microsoft\Windows\CurrentVersion\Internet Settings",
        ):
            try:
                vals = _reg_values(hive, sub, want)
            except OSError:
                continue
            if vals:
                w(f"  {label}\\{sub} : {vals}")
    w("— stratégies navigateur (GPO) —")
    found = False
    for hive, label in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"),
                        (winreg.HKEY_CURRENT_USER, "HKCU")):
        for sub in (r"SOFTWARE\Policies\Microsoft\Edge",
                    r"SOFTWARE\Policies\Chromium",
                    r"SOFTWARE\Policies\Google\Chrome"):
            try:
                vals = _reg_values(hive, sub)
            except OSError:
                continue
            found = True
            w(f"  {label}\\{sub} : {vals or '(aucune valeur)'}")
            if set(vals) & {"ProxyMode", "ProxyPacUrl", "ProxyServer"}:
                w("  ⚠ proxy imposé par stratégie : --no-proxy-server "
                  "peut être ignoré par ce navigateur")
    if not found:
        w("  aucune clé de stratégie Edge/Chromium/Chrome")


def _diag_applocker(w):
    """AppLocker/WDAC : actif seulement si AppIDSvc tourne — un exe non
    signé dans le dossier portable pourrait alors être bloqué."""
    w("— contrôle d'exécution —")
    if sys.platform != "win32":
        w("  (non applicable hors Windows)")
        return
    import subprocess
    try:
        r = subprocess.run(["sc.exe", "query", "appidsvc"],
                           capture_output=True, text=True, timeout=10)
        state = next((ln.strip() for ln in r.stdout.splitlines()
                      if "STATE" in ln), r.stdout.strip()[:120])
        w(f"  AppIDSvc (AppLocker) : {state}")
    except Exception as e:
        w(f"  AppIDSvc : {e}")


def _diag_network(w):
    """Réseau : proxy résolu par URL (PAC — 127.0.0.1 inclus, c'est lui
    qui décide si la webui passe), TCP direct vs proxy, GET réels,
    scrape d'une page."""
    import socket

    w("— réseau —")
    _proxy_session()
    import nextevents.scrape as scrape

    resolver = getattr(scrape.session, "proxy_resolver", None)
    urls = [scrape.BASE, "https://openagenda.com",
            f"http://127.0.0.1:{PORT}/"]
    for u in urls:
        try:
            px = (resolver.get_proxy_for_requests(u)
                  if resolver else dict(scrape.session.proxies))
            w(f"  proxy({u}) = {px or 'DIRECT'}")
        except Exception as e:
            w(f"  proxy({u}) : {e}")
    try:
        socket.create_connection(
            ("www.leschampslibres.fr", 443), timeout=8).close()
        w("  TCP direct :443 OK")
    except OSError as e:
        w(f"  TCP direct :443 KO ({e}) — proxy obligatoire")
    for u in urls[:2]:
        try:
            r = scrape.session.get(u, timeout=15)
            w(f"  GET {u} -> {r.status_code} ({len(r.content)} o)")
        except Exception as e:
            w(f"  GET {u} KO : {e}")
    try:
        evs = scrape.list_events(max_pages=1)
        w(f"  list_events(p1) : {len(evs)} événements")
    except Exception as e:
        w(f"  list_events KO : {e}")


def _diag_localhost_nav(w, sync_playwright):
    """Le test décisif : un mini-serveur local + navigation vers
    127.0.0.1 avec le proxy système (comportement du navigateur géré)
    puis avec --no-proxy-server (fenêtre dédiée de l'app)."""
    import functools
    import http.server

    w("— joignabilité 127.0.0.1 en navigateur —")
    (DATA / "diag-ui.html").write_text("diag ok", encoding="utf-8")

    class _H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(_H, directory=str(DATA)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        with sync_playwright() as p:
            for label, kw in [
                ("msedge, proxy système", dict(channel="msedge")),
                ("msedge, --no-proxy-server",
                 dict(channel="msedge", args=["--no-proxy-server"])),
                ("chromium embarqué, --no-proxy-server",
                 dict(args=["--no-proxy-server"])),
            ]:
                try:
                    b = p.chromium.launch(**kw)
                    resp = b.new_page().goto(
                        f"http://127.0.0.1:{port}/diag-ui.html",
                        timeout=15000)
                    b.close()
                    w(f"  {label} -> {resp.status if resp else '?'}")
                except Exception as e:
                    w(f"  {label} : KO — {str(e).splitlines()[-1][:200]}")
    finally:
        srv.shutdown()


def _diag():
    """Diagnostic complet d'un poste pro : port, proxy/PAC, stratégies
    navigateur GPO, AppLocker, réseau, Edge, joignabilité webui —
    écrit data/diag.log."""
    import subprocess
    import traceback

    log = DATA / "diag.log"

    def w(msg):
        print(msg)
        with open(log, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")

    log.unlink(missing_ok=True)
    w(f"python {sys.version}  frozen={getattr(sys, 'frozen', False)}")
    w(f"UI browser : {(_find_chromium() or _find_edge()) or 'défaut'}")
    w(f"PLAYWRIGHT_BROWSERS_PATH={os.environ.get('PLAYWRIGHT_BROWSERS_PATH')}")
    try:
        import socket
        socket.socket().bind(("127.0.0.1", PORT)).close()
        w(f"port {PORT} : libre")
    except OSError as e:
        w(f"port {PORT} : {e}")

    _diag_policies(w)
    _diag_applocker(w)
    _diag_network(w)

    w("— Edge du poste —")
    for exe in EDGE_PATHS:
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
        w(f"diag écrit dans {log}")
        return

    w("— rendu local (comme les diapos) —")
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

    _diag_localhost_nav(w, sync_playwright)
    w(f"diag écrit dans {log}")


def main():
    from nextevents.runner import scheduler
    from nextevents.settings import load_settings
    from nextevents.webapp import app

    _proxy_session()
    load_settings()
    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=_open_when_ready, daemon=True).start()
    print(f"Nextevents — http://127.0.0.1:{PORT}  (Ctrl+C pour quitter)")
    try:
        app.run(host="127.0.0.1", port=PORT)
    finally:
        if _UI_PROC:
            _UI_PROC.terminate()


if __name__ == "__main__":
    if "--diag" in sys.argv:
        _diag()
    else:
        main()
