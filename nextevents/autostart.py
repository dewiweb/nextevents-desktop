"""Lancement automatique de l'app à l'ouverture de session.

Windows : valeur « Nextevents » dans HKCU\\…\\CurrentVersion\\Run.
Linux   : ~/.config/autostart/nextevents.desktop (freedesktop).

Cible pointée : l'exe/AppImage en mode frozen, python + desktop.py
en dev. Indépendant de `autostart_slideshow` (ce réglage choisit ce
que l'app ouvre une fois lancée)."""

import os
import sys
from pathlib import Path

NAME = "Nextevents"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _cmd():
    """Ligne de commande à lancer au login, ou None si indéterminable."""
    if getattr(sys, "frozen", False):
        if "APPIMAGE" in os.environ:
            return f'"{os.environ["APPIMAGE"]}"'
        return f'"{sys.executable}"'
    # dev : python + desktop.py à côté du package
    root = Path(__file__).resolve().parent.parent
    return f'"{sys.executable}" "{root / "desktop.py"}"'


def _linux_file():
    return Path.home() / ".config" / "autostart" / "nextevents.desktop"


def is_enabled():
    """L'état réel côté OS (pas le réglage — l'utilisateur a pu
    déplacer l'exe ou nettoyer la clé à la main)."""
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                v, _ = winreg.QueryValueEx(k, NAME)
            return bool(v)
        return _linux_file().exists()
    except Exception:
        return False


def apply(enabled):
    """Installe/retire l'entrée autostart. Renvoie un message pour le
    journal/statusbar, ou lève une exception si l'OS refuse."""
    cmd = _cmd()
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY,
                            0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except FileNotFoundError:
                    pass
        return f"autostart {'activé' if enabled else 'désactivé'} : {cmd}"
    f = _linux_file()
    if enabled:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={NAME}\n"
            f"Exec={cmd}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n",
            encoding="utf-8")
    else:
        f.unlink(missing_ok=True)
    return f"autostart {'activé' if enabled else 'désactivé'} : {cmd}"
