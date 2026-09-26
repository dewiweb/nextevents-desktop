# PyInstaller spec — nextevents desktop (Windows portable / Linux AppImage)
# Build : pyinstaller --clean --noconfirm app.spec
# Sortie : dist/nextevents/ (dossier portable à zipper/copier tel quel)

import sys

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [("assets", "assets"), ("nextevents.ico", "."),
         ("appimage/nextevents.png", ".")]
binaries = []
# imports au niveau fonction — explicites ; les hooks PySide6
# embarquent plugins plateforme, ressources et libs Qt
hiddenimports = [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "PySide6.QtNetwork",  # instance unique (QLocalServer/Socket)
    "smbprotocol", "qrcode", "playwright",
]

# Playwright embarque son driver (node) — nécessaire même en canal
# "msedge" (le navigateur est celui du système, pas de téléchargement)
tmp = collect_all("playwright")
datas += tmp[0]
binaries += tmp[1]
hiddenimports += tmp[2]

# keyring choisit son backend par entry points : métadonnées +
# backends requis (Credential Manager Windows, Secret Service Linux)
tmp = collect_all("keyring")
datas += tmp[0] + copy_metadata("keyring")
binaries += tmp[1]
hiddenimports += tmp[2]

# Windows n'a pas de base tz système : zoneinfo a besoin du package
# tzdata (données pures, rien d'importé en clair → hiddenimports)
tmp = collect_all("tzdata")
datas += tmp[0]
binaries += tmp[1]
hiddenimports += tmp[2]

a = Analysis(
    ["desktop.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtWebEngineQuick", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtQuick",
              "PySide6.QtQml", "flask", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe_kwargs = {}
if sys.platform == "win32":
    exe_kwargs = {"icon": "nextevents.ico", "version": "version.txt"}
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nextevents",
    console=False,  # app fenêtrée — journal dans data/app.log
    **exe_kwargs,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="nextevents",
)
