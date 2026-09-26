"""Requêtes HTTP avec retry — un poste d'affichage n'a pas d'opérateur
pour relancer une génération tombée sur une microcoupure réseau."""

import time

import requests

RETRIES = 3
BACKOFF = 2.0


def get(url, session=None, retries=RETRIES, timeout=30, **kw):
    """GET avec retries : erreurs réseau et 5xx retentés (backoff
    linéaire 2 s, 4 s), 4xx levés immédiatement — réessayer un 404
    ou un 403 ne sert à rien."""
    req = session.get if session is not None else requests.get
    last = None
    for attempt in range(retries):
        try:
            r = req(url, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code < 500:
                raise  # 4xx : échec permanent, pas de retry
            last = e
        except requests.RequestException as e:
            last = e
        if attempt < retries - 1:
            time.sleep(BACKOFF * (attempt + 1))
    raise last
