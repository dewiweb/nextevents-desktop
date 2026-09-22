# PyInstaller spec — nextevents desktop (Windows portable)
# Build : pyinstaller --clean --noconfirm app.spec
# Sortie : dist/nextevents/ (dossier portable à zipper/copier tel quel)

import os

from PyInstaller.utils.hooks import collect_all

datas = [("upstream/assets", "assets")]
binaries = []
hiddenimports = []

# Chromium embarqué : `playwright install chromium` avec
# PLAYWRIGHT_BROWSERS_PATH=ms-playwright avant le build. Hors GPO/proxy
# du navigateur géré ; absent → repli sur l'Edge du poste (msedge).
if os.path.isdir("ms-playwright"):
    datas.append(("ms-playwright", "ms-playwright"))

# Playwright embarque son driver (node) — nécessaire même en canal
# "msedge" (le navigateur est celui du système, pas de téléchargement)
tmp = collect_all("playwright")
datas += tmp[0]
binaries += tmp[1]
hiddenimports += tmp[2]

# proxy d'entreprise (imports conditionnels dans desktop.py)
hiddenimports += ["pypac", "dukpy", "requests_negotiate_sspi"]

a = Analysis(
    ["desktop.py"],
    pathex=["upstream"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nextevents",
    console=True,  # console = journal de l'app
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="nextevents",
)
