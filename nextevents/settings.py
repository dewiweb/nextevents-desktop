"""Réglages persistés (settings.json dans OUT_DIR) + état runtime partagé."""

import json
import os
import threading
from pathlib import Path

from .paths import OUT_DIR as DEFAULT_OUT

OUT_DIR = Path(os.environ.get("OUT_DIR", DEFAULT_OUT))
SETTINGS_FILE = Path(os.environ.get("SETTINGS_FILE", OUT_DIR / "settings.json"))

DEFAULTS = {
    "interval_hours": 0,
    "max_events": 0,
    "limit_mode": "count",   # count | days | date
    "limit_days": 14,
    "limit_date": "",        # ISO YYYY-MM-DD
    "oa_api_key": "",
    "oa_agenda": "leschampslibres",
    "data_source": "site",   # site | openagenda
    "resolution": "uhd",
    "gen_landscape": 1,
    "gen_portrait": 0,
    "gen_categories": "rencontres-aux-champs-libres,"
                      "concerts-aux-champs-libres,"
                      "projections-aux-champs-libres,"
                      "spectacles-aux-champs-libres,"
                      "evenements-aux-champs-libres",
    "ftp_host": "",
    "ftp_port": 21,
    "ftp_user": "",
    "ftp_pass": "",
    "ftp_path": "/",
    "ftp_tls": 0,
    "ftp_send_landscape": 1,
    "ftp_send_portrait": 0,
    "smb_host": "",
    "smb_share": "",
    "smb_path": "",
    "smb_user": "",
    "smb_pass": "",
    "smb_send_landscape": 1,
    "smb_send_portrait": 0,
    "local_dir": "",
    "out_dir": "",
    "close_to_tray": 1,
    "start_minimized": 0,
    "autostart_slideshow": "none",
    "ss_delay": 8,
    "ss_transition": "fade",
    "ss_tdur": 1500,
    "ss_delay_p": 8,
    "ss_transition_p": "fade",
    "ss_tdur_p": 1500,
}

# état runtime du serveur (génération en cours, journal, dernier run)
state = {"running": False, "last_run": None, "last_error": None, "log": []}
lock = threading.Lock()

# last_run persisté : lu une seule fois au démarrage — les appels
# suivants de load_settings() ne doivent pas écraser la valeur
# courante (course avec le writer de run_generation).
try:
    state["last_run"] = json.loads(
        SETTINGS_FILE.read_text()).get("last_run")
except Exception:
    pass


def load_settings():
    try:
        s = json.loads(SETTINGS_FILE.read_text())
    except Exception:
        s = {}
    out = dict(DEFAULTS)
    for k, d in DEFAULTS.items():
        v = s.get(k, d)
        if isinstance(d, int):
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass
        else:
            out[k] = str(v)
    return out


def resolve_out_dir(cfg=None):
    """Dossier de sortie effectif : réglage `out_dir` (disque local,
    lecteur mappé, UNC) s'il est rempli, sinon OUT_DIR env/défaut."""
    if cfg is None:
        cfg = load_settings()
    d = (cfg.get("out_dir") or "").strip()
    return Path(d) if d else OUT_DIR


def save_settings(s):
    """Écriture atomique (tmp + os.replace) : un crash en cours
    d'écriture ne peut pas tronquer settings.json."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(s)
    if state["last_run"]:
        payload["last_run"] = state["last_run"]
    tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, SETTINGS_FILE)
