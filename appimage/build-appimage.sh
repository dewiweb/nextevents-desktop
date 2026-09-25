#!/usr/bin/env bash
# Assemble dist/nextevents/ en AppImage distributable.
#
# Prérequis :
#   - build PyInstaller fait :  pyinstaller --clean --noconfirm app.spec
#   - libs du headless shell installées (playwright install-deps chromium)
#     pour que linuxdeploy puisse les résoudre et les embarquer
#   - linuxdeploy + appimagetool téléchargés automatiquement ci-dessous
#
# Usage :  appimage/build-appimage.sh [nom-sortie]
# Sortie : dist/nextevents-linux[-<nom-sortie>].AppImage
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:-}"
OUT="dist/nextevents-linux${TAG:+-$TAG}.AppImage"
APPDIR=dist/Nextevents.AppDir
TOOLS=dist/.tools

# Les outils sont eux-mêmes des AppImages — extraction à la volée si
# FUSE absent (CI, conteneurs).
export APPIMAGE_EXTRACT_AND_RUN=1

fetch() {  # url dest
    if [ ! -x "$2" ]; then
        curl -fsSL "$1" -o "$2" && chmod +x "$2"
    fi
}

mkdir -p "$TOOLS"
fetch https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage \
      "$TOOLS/linuxdeploy"
fetch https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
      "$TOOLS/appimagetool"

# --- AppDir -------------------------------------------------------------
rm -rf "$APPDIR"
mkdir -p "$APPDIR/opt" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a dist/nextevents "$APPDIR/opt/nextevents"
cp appimage/AppRun "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp appimage/nextevents.desktop "$APPDIR/nextevents.desktop"
cp appimage/nextevents.desktop \
   "$APPDIR/usr/share/applications/nextevents.desktop"
cp appimage/nextevents.png "$APPDIR/nextevents.png"
cp appimage/nextevents.png \
   "$APPDIR/usr/share/icons/hicolor/256x256/apps/nextevents.png"

# --- libs système à embarquer -------------------------------------------
# linuxdeploy résout (ldd récursif) les dépendances des exécutables
# listés ; sa liste d'exclusion épargne libc/libstdc++/libGL… qui doivent
# venir de l'hôte. Les .so des wheels Python sont auto-suffisants (deps
# hashées à côté) — on ne les passe pas, linuxdeploy les prend en compte
# quand même comme dépendances des exécutables.
args=(-e "$APPDIR/opt/nextevents/nextevents")
while IFS= read -r f; do args+=(-e "$f"); done < <(
    find "$APPDIR" -type f \( -name node -o -name 'chrome-headless-shell' \))

"$TOOLS/linuxdeploy" --appdir "$APPDIR" "${args[@]}"

# linuxdeploy copie les exécutables dans usr/bin/ — inutiles : ceux qui
# tournent sont dans opt/nextevents/ (PyInstaller exige _internal à côté).
rm -f "$APPDIR/usr/bin/nextevents" "$APPDIR/usr/bin/node" \
      "$APPDIR/usr/bin/chrome-headless-shell"

# plugin imageformat TIFF : inutile (webui = png/jpg/webp) et il exige
# libtiff.so.5 — vieille ABI des wheels manylinux, absente des hôtes
# récents → on le retire plutôt que d'embarquer une lib obsolète
rm -f "$APPDIR"/opt/nextevents/_internal/PySide6/Qt/plugins/imageformats/libqtiff.so

# Libs que linuxdeploy refuse d'embarquer (sa liste d'exclusion suppose
# GL/X11 fournis par l'hôte) mais dont Qt6 a des NEEDED stricts :
#   - libEGL.so.1 + dispatchers libglvnd : sans elles l'app ne démarre
#     pas sur un système sans mesa ; ce sont de purs aiguilleurs vers
#     le driver de l'hôte (mesa, nvidia…) — sûrs à embarquer
#   - libxcb-shape.so.0 : extension xcb requise par libQt6XcbQpa /
#     libqxcb — l'app échouerait sur X11 sans elle
for lib in libEGL.so.1 libGLdispatch.so.0 libGLX.so.0 libOpenGL.so.0 \
           libxcb-shape.so.0; do
    src=$(ldconfig -p | awk -v l="$lib" \
        '$1==l && /x86-64/{print $NF; exit}')
    if [ -n "$src" ]; then
        cp -L "$src" "$APPDIR/usr/lib/$lib"
    else
        echo "ATTENTION : $lib introuvable sur l'hôte de build" >&2
    fi
done

# --- vérification : aucune dépendance non résolue -------------------------
QTLIB=$(find "$APPDIR/opt/nextevents/_internal/PySide6/Qt/lib" \
        -maxdepth 0 -type d 2>/dev/null || true)
missing=""
while IFS= read -r f; do
    m=$(LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/opt/nextevents/_internal:$QTLIB" \
        ldd "$f" 2>/dev/null | awk '/not found/{print $1}' || true)
    if [ -n "$m" ]; then missing="$missing$f\n$m\n"; fi
done < <(find "$APPDIR" -type f -name '*.so*' -o -type f -perm -u+x)
if [ -n "$missing" ]; then
    echo "ERREUR — dépendances non résolues :" >&2
    echo -e "$missing" >&2
    exit 1
fi

# --- AppImage -------------------------------------------------------------
rm -f "$OUT"
"$TOOLS/appimagetool" "$APPDIR" "$OUT"
echo "OK — $OUT"
