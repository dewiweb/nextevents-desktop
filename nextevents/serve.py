"""Serveur HTTP minimal — diffusion des diapos vers des écrans distants.

Un écran Android, une TV connectée, un Raspberry Pi ou tout navigateur
kiosk pointé sur `http://<poste>:<port>` affiche le diaporama à jour :
la page se rafraîchit seule (liste re-lue toutes les 15 s, images
cache-bustées par date de modification — une régénération apparaît sans
rien toucher).

Routage (tout est en lecture seule, dossier de sortie uniquement) :
  /                      page diaporama auto-plein-écran
                         (?fmt=landscape|portrait — sinon déduit de
                         l'orientation de l'écran, repli paysage)
  /slides.json?fmt=…     liste [nom, mtime_ns] + délai des réglages
  /png/<fmt>/<fichier>   un PNG généré (noms strictement validés)
  /today/…               la diapo du jour (index.html autonome)

Réseau interne seulement : pas d'authentification — les PNG sont
publics de fait, mais le serveur n'expose rien d'autre que le dossier
de sortie et ne répond qu'en GET.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .settings import load_settings, resolve_out_dir

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.png$")
_FMTS = ("landscape", "portrait")

_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<title>nextevents</title><style>
html,body{margin:0;height:100%;background:#000;overflow:hidden}
img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;
    opacity:0;transition:opacity 1.2s}
img.on{opacity:1}
#empty{position:absolute;inset:0;z-index:2;display:none;background:#000;
    color:#555;font:24px sans-serif;place-items:center;text-align:center}
</style></head><body>
<img id="a"><img id="b"><div id="empty">aucune diapo</div>
<script>
const p = new URLSearchParams(location.search);
const fmt = p.get("fmt") ||
    (matchMedia("(orientation: portrait)").matches
        ? "portrait" : "landscape");
const imgs = [document.getElementById("a"), document.getElementById("b")];
const empty = document.getElementById("empty");
let cur = 0, idx = 0, slides = [], delay = 8, tickTimer = null;

function show(i) {            // fondu vers slides[i] (re-téléchargée si mtime≠)
    const [name, mtime] = slides[i % slides.length];
    const nxt = imgs[1 - cur];
    nxt.onload = () => { nxt.classList.add("on");
                         imgs[cur].classList.remove("on");
                         cur = 1 - cur; };
    nxt.src = `/png/${fmt}/${name}?v=${mtime}`;
}
function restart() {          // (re)lance la rotation au délai courant
    clearInterval(tickTimer); tickTimer = null;
    if (!slides.length) return;
    show(idx);
    tickTimer = setInterval(
        () => { idx = (idx + 1) % slides.length; show(idx); },
        delay * 1000);
}
async function poll() {
    try {
        const r = await fetch(`/slides.json?fmt=${fmt}`,
                              {cache: "no-store"});
        const d = await r.json();
        const changed = JSON.stringify(d.slides) !==
                        JSON.stringify(slides) || d.delay !== delay;
        slides = d.slides; delay = d.delay || 8;
        empty.style.display = slides.length ? "none" : "grid";
        if (idx >= slides.length) idx = 0;
        if (changed || !tickTimer) restart();
    } catch (e) { /* réseau coupé : le prochain poll retentera */ }
}
poll();
setInterval(poll, 15000);
</script></body></html>"""


def _fmt(params):
    fmt = (params.get("fmt") or ["landscape"])[0]
    return fmt if fmt in _FMTS else "landscape"


class _Handler(BaseHTTPRequestHandler):
    """GET uniquement — tout est calculé depuis le dossier de sortie
    à chaque requête (pas de liste figée au démarrage)."""

    server_version = "nextevents-serve"

    def log_message(self, fmt, *args):  # silence → app.log déjà verbeux
        pass

    def _send(self, code, body=b"", ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        u = urlparse(unquote(self.path))
        params = parse_qs(u.query)
        path = u.path
        out = resolve_out_dir()

        if path == "/":
            self._send(200, _PAGE.encode(), "text/html; charset=utf-8")
            return

        if path == "/slides.json":
            fmt = _fmt(params)
            d = out / fmt
            slides = ([[p.name, p.stat().st_mtime_ns] for p in
                       sorted(d.glob("*.png"))] if d.is_dir() else [])
            # le délai suit le réglage du diaporama natif (re-lu à
            # chaque poll — un changement s'applique sans reload)
            sfx = "_p" if fmt == "portrait" else ""
            delay = (load_settings().get(f"ss_delay{sfx}") or 8)
            self._send(200, json.dumps(
                {"slides": slides, "delay": delay}).encode(),
                "application/json")
            return

        m = re.match(r"^/png/(landscape|portrait)/([^/]+)$", path)
        if m and _NAME_RE.match(m.group(2)):
            p = out / m.group(1) / m.group(2)
            if p.is_file():
                self._send(200, p.read_bytes(), "image/png")
                return
            self._send(404)
            return

        # diapo du jour : répertoire today/ servi en statique
        # (index.html autonome — un écran peut n'afficher qu'elle)
        if path.startswith("/today/"):
            rel = path[len("/today/"):] or "index.html"
            # pas de traversal : segments simples uniquement
            if re.match(r"^[A-Za-z0-9._/-]+$", rel) and ".." not in rel:
                p = (out / "today" / rel).resolve()
                base = (out / "today").resolve()
                if base in p.parents and p.is_file():
                    ctype = ("text/html; charset=utf-8"
                             if p.suffix == ".html" else
                             "image/png" if p.suffix == ".png" else
                             "application/octet-stream")
                    self._send(200, p.read_bytes(), ctype)
                    return
            self._send(404)
            return

        self._send(404)


class _Server:
    """Un serveur par process, reconfigurable à chaud (port/actif)."""

    def __init__(self):
        self.httpd = None
        self.port = None
        self._lock = threading.Lock()

    def stop(self):
        with self._lock:
            if self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
                self.httpd = None
                self.port = None

    def start(self, port):
        with self._lock:
            if self.httpd and self.port == port:
                return
            if self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
            self.httpd = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
            self.port = port
            threading.Thread(target=self.httpd.serve_forever,
                             daemon=True).start()

    def apply(self, cfg):
        """Synchronise l'état du serveur avec les réglages."""
        if cfg.get("serve_enabled"):
            try:
                self.start(int(cfg.get("serve_port") or 8090))
                return self.port
            except OSError:
                return None     # port déjà pris, etc.
        self.stop()
        return None


SERVER = _Server()


def lan_url(port):
    """URL joignable depuis le réseau local (IP « sortante » via une
    socket UDP — aucun paquet n'est émis ; repli loopback hors ligne)."""
    import socket
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect(("8.8.8.8", 80))
        ip = sk.getsockname()[0]
        sk.close()
    except OSError:
        ip = "127.0.0.1"
    return f"http://{ip}:{port}/"
