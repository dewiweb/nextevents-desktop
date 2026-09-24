"""Chemins du projet — racine, assets, cache.

Surchargeables par variables d'environnement (usage desktop figé :
assets en lecture seule dans le bundle, cache/fontes dans ./data) :
NEXTEVENTS_ASSET_DIR, NEXTEVENTS_FONT_DIR, NEXTEVENTS_CACHE_DIR,
NEXTEVENTS_OUT_DIR."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = Path(os.environ.get("NEXTEVENTS_ASSET_DIR", ROOT / "assets"))
FONT_DIR = Path(os.environ.get("NEXTEVENTS_FONT_DIR", ASSET_DIR / "fonts"))
CACHE_DIR = Path(os.environ.get("NEXTEVENTS_CACHE_DIR", ASSET_DIR / "cache"))
OA_MAP_FILE = CACHE_DIR / "oa-map.json"
OUT_DIR = Path(os.environ.get("NEXTEVENTS_OUT_DIR", ROOT / "diaporama"))
