"""Pré-flight : vérifie que les réglages permettent une génération
utile avant de la lancer.

Pur — ni Qt ni réseau : testable en CI et réutilisable depuis la
fenêtre (bouton Générer), le tray ou l'assistant de premier lancement.
Un `blocker` empêche le run, un `warn` est listé mais contournable.
"""

import importlib.util
import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Issue:
    level: str   # "blocker" | "warn"
    msg: str
    tab: str     # onglet où corriger : "Général" | "Destinations"


def validate_settings(s):
    """Liste les problèmes des réglages `s` (load_settings())."""
    out = []

    if not s.get("gen_landscape") and not s.get("gen_portrait"):
        out.append(Issue(
            "blocker", "Aucun format de diapo n'est coché "
            "(paysage / portrait) — la génération ne produirait rien.",
            "Général"))

    # dossier de sortie : un chemin existant qui n'est pas un dossier
    # (fichier, lien cassé) ferait échouer le mkdir de generate()
    out_dir = (s.get("out_dir") or "").strip()
    if out_dir:
        d = Path(out_dir).expanduser()
        if d.exists() and not d.is_dir():
            out.append(Issue(
                "blocker", f"Le dossier de sortie pointe sur un "
                f"fichier : {d}", "Destinations"))

    if (s.get("data_source") == "openagenda"
            and not (s.get("oa_api_key") or "").strip()):
        out.append(Issue(
            "warn", "Source OpenAgenda sans clé API — la génération "
            "repliera sur le scraping du site.", "Général"))

    # destinations : un hôte sans identifiants/partage échouera à la
    # synchro (warning seulement — les diapos locales restent bonnes)
    if (s.get("ftp_host") or "").strip() and (
            not (s.get("ftp_user") or "").strip()
            or not (s.get("ftp_pass") or "").strip()):
        out.append(Issue(
            "warn", "Destination FTP configurée sans identifiant "
            "complet — la synchro échouera.", "Destinations"))
    if (s.get("smb_host") or "").strip() \
            and not (s.get("smb_share") or "").strip():
        out.append(Issue(
            "warn", "Destination SMB sans nom de partage — la synchro "
            "échouera.", "Destinations"))
    local = (s.get("local_dir") or "").strip()
    if local and not Path(local).expanduser().exists():
        out.append(Issue(
            "warn", f"Le dossier miroir n'existe pas : {local}",
            "Destinations"))

    # heures fixes : _times_due ignore silencieusement les tokens
    # invalides — autant le signaler à l'utilisateur
    bad = [t for t in (s.get("sched_times") or "").split(",")
           if t.strip() and not re.fullmatch(r"\d{1,2}:\d{2}", t.strip())]
    if bad:
        out.append(Issue(
            "warn", f"Heures fixes mal formées (ignorées) : "
            f"{', '.join(bad)}", "Général"))

    # rendu : le module playwright peut être présent sans ses
    # binaires (« playwright install » pas fait) — executable_path
    # pointe le chrome complet alors que le headless utilise
    # chrome-headless-shell : seule sonde fiable, un vrai lancement.
    # Résultat mis en cache : un succès ne sera pas invalidé en cours
    # de session ; un échec est re-tenté (l'utilisateur a peut-être
    # installé entre-temps).
    if importlib.util.find_spec("playwright") is None:
        # repli firefox headless prévu par render_all — warn, pas blocker
        out.append(Issue(
            "warn", "Le moteur de rendu playwright n'est pas installé "
            "— repli sur firefox headless au rendu.", "Général"))
    elif _browser_ok() is not True:
        out.append(Issue(
            "blocker",
            "Le navigateur de rendu ne se lance pas — installez-le "
            "(playwright install chromium --only-shell) ou définissez "
            "NEXTEVENTS_BROWSER_CHANNEL pour un navigateur système.",
            "Général"))

    return out


_browser_probe = None


def _browser_ok():
    """Tente un lancement chromium headless (comme render_all) —
    ~300 ms la première fois, résultat ensuite mis en cache tant
    qu'il est positif."""
    global _browser_probe
    if _browser_probe is True:
        return True
    ch = os.environ.get("NEXTEVENTS_BROWSER_CHANNEL")
    try:
        from playwright.sync_api import sync_playwright
        kw = {"channel": ch} if ch else {}
        with sync_playwright() as p:
            b = p.chromium.launch(**kw)
            b.close()
        _browser_probe = True
    except Exception:
        _browser_probe = False
    return _browser_probe
