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


def scheduler():
    while True:
        time.sleep(60)
        try:
            s = load_settings()
            due = (
                s["interval_hours"] > 0
                and not state["running"]
                and (
                    state["last_run"] is None
                    or time.time() - state["last_run"] >= s["interval_hours"] * 3600
                )
            )
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
