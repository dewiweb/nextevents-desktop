"""nextevents — diaporama des événements des Champs Libres.

Modules :
  paths     chemins (racine, assets, cache)
  scrape    scraping leschampslibres.fr (listes, détails, couleurs de card)
  media     fontes, images OpenAgenda, cache
  slide     template HTML + rendu PNG (Playwright / chromium headless)
  sync      envoi FTP / SMB vers le poste de diffusion
  generate  orchestration de la génération complète
  settings  réglages persistés + état runtime
  runner    exécution des générations + planificateur
  today     diapo du jour (édition, rendu, envoi)
"""

from .generate import generate, SIZES, DEFAULT_SIZE  # noqa: F401
