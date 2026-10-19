"""Lancement du navigateur de rendu — stratégie partagée entre la
sonde pré-flight (preflight._browser_ok) et le rendu
(slide.render_all) : la sonde doit voir les mêmes échecs que le
rendu, sinon elle bloque des générations qui auraient réussi."""

import os
import time

# Sur poste géré, le launch peut échouer de façon transitoire
# (AV qui scanne le profil temporaire, Edge en maj…) : on retente,
# puis on bascule en fenêtré si le headless reste bloqué.
# backoff long : une maj Edge ou un scan AV peut bloquer le
# lancement pendant une minute — on étale les tentatives
LAUNCH_WAITS = (0, 5, 15, 30)


def launch_browser(p, log=print, waits=LAUNCH_WAITS):
    """Tente p.chromium.launch avec retries — retourne le browser ou
    None si toutes les tentatives ont échoué.

    NEXTEVENTS_BROWSER_CHANNEL permet d'utiliser un navigateur
    système (ex. "msedge" pour l'app desktop — pas de téléchargement).
    `waits` est paramétrable pour les tests (pas de sleep réel)."""
    channel = os.environ.get("NEXTEVENTS_BROWSER_CHANNEL")
    attempts = [(channel, True)] * len(waits) + \
        ([(channel, False)] if channel else [])
    for i, (ch, headless) in enumerate(attempts):
        if i:
            time.sleep(waits[min(i, len(waits) - 1)])
        try:
            kw = {"headless": headless}
            if ch:
                kw["channel"] = ch
            return p.chromium.launch(**kw)
        except Exception as e:
            log(f"  ✗ lancement navigateur ({ch or 'chromium'}, "
                f"headless={headless}) : {type(e).__name__}")
    return None
