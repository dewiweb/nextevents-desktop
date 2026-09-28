"""Exécution des générations : thread, journal capturé, planificateur."""

import contextlib
import io
import sys
import threading
import time

from .generate import generate
from .slide import SIZES, DEFAULT_SIZE
from .settings import (
    load_settings, resolve_out_dir, save_settings, lock, state,
)


class LogWriter(io.TextIOBase):
    """Capture les print() de la génération vers state["log"] tout en
    les répercutant vers le vrai stdout (data/app.log en frozen)."""

    def __init__(self, orig):
        self._orig = orig

    def write(self, s):
        for line in s.splitlines():
            if line.strip():
                state["log"].append(line)
                del state["log"][:-500]
        try:
            self._orig.write(s)
        except Exception:
            pass
        return len(s)


def run_generation():
    with lock:
        if state["running"]:
            return
        state.update(running=True, last_error=None, log=[])
    try:
        s = load_settings()
        with contextlib.redirect_stdout(LogWriter(sys.stdout)):
            generate(
                out_dir=resolve_out_dir(s), max_events=s["max_events"], cfg=s,
                size=SIZES.get(s["resolution"], DEFAULT_SIZE),
            )
        state["last_run"] = time.time()
    except Exception as e:
        state["last_error"] = str(e)
    finally:
        state["running"] = False
        save_settings(load_settings())


def _interval_min(s):
    """Rafraîchissement en minutes — interval_min nouveau format,
    repli sur interval_hours des réglages antérieurs."""
    return (s["interval_min"] if "interval_min" in s
            else s.get("interval_hours", 0) * 60)


def _times_due(spec, last_run, now=None):
    """Heures fixes « HH:MM, HH:MM » — vrai si la plus récente
    occurrence passée (aujourd'hui ou hier) est postérieure à
    last_run. last_run None → l'occurrence passée du jour est due
    (rattrapage au lancement)."""
    import datetime as dt
    now = now or dt.datetime.now()
    times = []
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            h, m = (int(x) for x in tok.split(":"))
            times.append(dt.time(h % 24, m % 60))
        except ValueError:
            continue
    if not times:
        return False
    past = [dt.datetime.combine(d, t).timestamp()
            for d in (now.date(), now.date() - dt.timedelta(days=1))
            for t in times
            if dt.datetime.combine(d, t).timestamp() <= now.timestamp()]
    return bool(past) and (last_run is None or last_run < max(past))


def scheduler():
    while True:
        time.sleep(60)
        try:
            s = load_settings()
            mins = _interval_min(s)
            due = not state["running"] and (
                (mins > 0 and (
                    state["last_run"] is None
                    or time.time() - state["last_run"] >= mins * 60))
                or _times_due(s.get("sched_times", ""),
                              state["last_run"]))
            if due:
                threading.Thread(target=run_generation, daemon=True).start()
        except Exception:
            pass


def slides():
    """Diapos paysage (sous-dossier landscape/ de la sortie)."""
    d = resolve_out_dir() / "landscape"
    if not d.exists():
        return []
    return sorted(p.name for p in d.glob("*.png"))


def slides_portrait():
    """Diapos portrait (sous-dossier portrait/ de la sortie)."""
    d = resolve_out_dir() / "portrait"
    if not d.exists():
        return []
    return sorted(p.name for p in d.glob("*.png"))
