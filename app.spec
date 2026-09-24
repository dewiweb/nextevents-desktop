# PyInstaller spec — nextevents desktop (Windows portable)
# Build : pyinstaller --clean --noconfirm app.spec
# Sortie : dist/nextevents/ (dossier portable à zipper/copier tel quel)

from PyInstaller.utils.hooks import collect_all

datas = [("upstream/assets", "assets"), ("nextevents.ico", ".")]
binaries = []
# backend win32 de pystray et dialogue natif sont importés dynamiquement
hiddenimports = ["pystray._win32", "win32com.shell"]

# Playwright embarque son driver (node) — nécessaire même en canal
# "msedge" (le navigateur est celui du système, pas de téléchargement)
tmp = collect_all("playwright")
datas += tmp[0]
binaries += tmp[1]
hiddenimports += tmp[2]

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
    console=False,  # tray app — journal dans data/app.log
    icon="nextevents.ico",
    version="version.txt",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="nextevents",
)
