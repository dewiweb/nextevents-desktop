"""Stockage des secrets (ftp_pass, smb_pass, oa_api_key).

Ordre de résolution à la lecture :
1. variable d'environnement NEXTEVENTS_<CLE> (serveurs headless, CI)
2. trousseau de l'OS via `keyring` — Credential Manager sous Windows,
   Secret Service (GNOME Keyring / KWallet) sous Linux
3. settings.json en clair — repli quand aucun trousseau n'est
   disponible (Linux sans D-Bus/session graphique)

À l'écriture, un secret part dans le trousseau dès qu'il est
disponible ; settings.json n'en garde alors plus la valeur.
"""

import os

SERVICE = "nextevents"
KEYS = ("ftp_pass", "smb_pass", "oa_api_key")

_KR = None        # backend keyring utilisable, ou False
_KR_DONE = False  # probe déjà tentée


def env_name(key):
    return "NEXTEVENTS_" + key.upper()


def _keyring():
    """Backend keyring probé une fois ; None si absent/inutilisable
    (paquet manquant, ou Secret Service sans session D-Bus)."""
    global _KR, _KR_DONE
    if _KR_DONE:
        return _KR or None
    _KR_DONE = True
    try:
        import keyring
        from keyring.backends.fail import Keyring as _Fail
        kr = keyring.get_keyring()
        if isinstance(kr, _Fail):
            return None
        kr.get_password(SERVICE, "__probe__")  # sonde réelle (D-Bus…)
        _KR = kr
        return kr
    except Exception:
        return None


def where(key):
    """'env' | 'keyring' | None — d'où viendrait le secret si lu."""
    if os.environ.get(env_name(key)):
        return "env"
    return "keyring" if _keyring() else None


def load(key):
    """Valeur du secret, ou None si ni env ni trousseau ne la fournit
    (l'appelant retombe alors sur la valeur de settings.json)."""
    env = os.environ.get(env_name(key))
    if env:
        return env
    kr = _keyring()
    if kr:
        try:
            v = kr.get_password(SERVICE, key)
            if v:
                return v
        except Exception:
            pass
    return None


def store(key, value):
    """Persiste le secret hors settings.json si possible.
    Renvoie True si la valeur ne doit pas rester dans le fichier
    (env override actif — env gagne toujours — ou trousseau écrit)."""
    if not value:
        return False
    if os.environ.get(env_name(key)):
        return True  # l'env var fournit déjà la valeur à la lecture
    kr = _keyring()
    if kr:
        try:
            kr.set_password(SERVICE, key, value)
            return True
        except Exception:
            pass
    return False
