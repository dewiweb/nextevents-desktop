#!/bin/sh
# maquette.sh — itérer sur la charte des diapos sans environnement dev.
#
#   ./maquette.sh [chemin/vers/nextevents-linux-*.AppImage]
#
# 1re exécution : extrait les gabarits de l'AppImage dans
# ./maquette-assets/ puis lance l'app dessus (NEXTEVENTS_ASSET_DIR,
# respecté par desktop.py via setdefault). Boucle ensuite :
#
#   éditer maquette-assets/slide_base.css (charte commune) ou le bloc
#   :root en tête d'un maquette-assets/slide_template*.html (métriques
#   du format) → régénérer une diapo depuis la galerie → ajuster.
#
# Le HTML produit (data/diaporama/html/*.html) est autonome : il
# s'ouvre tel quel dans un navigateur pour un contrôle hors de l'app.
set -eu

APPIMAGE=${1:-$(ls -t ./*linux*.AppImage 2>/dev/null | head -1 || true)}
if [ -z "$APPIMAGE" ]; then
    echo "AppImage introuvable — passe-la en argument :" >&2
    echo "  $0 /chemin/nextevents-linux-*.AppImage" >&2
    exit 1
fi

WORK=maquette-assets
if [ ! -d "$WORK" ]; then
    echo "Extraction des gabarits depuis $APPIMAGE…"
    "$APPIMAGE" --appimage-extract >/dev/null
    cp -r squashfs-root/opt/nextevents/_internal/assets "$WORK"
    rm -rf squashfs-root
    echo "→ gabarits éditables dans $WORK/"
    echo "   slide_base.css          : charte commune (pastille, specs, footer…)"
    echo "   slide_template*.html    : métriques du format (bloc :root en tête)"
fi

export NEXTEVENTS_ASSET_DIR="$PWD/$WORK"
exec "$APPIMAGE"
