"""Aperçu image partagé (galerie, diapo du jour) — fenêtré ↔ plein
écran. Décodage à la résolution d'écran et rendu par _Slide, qui
re-met à l'échelle à chaque resize : l'image reste nette en plein
écran comme en fenêtré.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QImageReader, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QVBoxLayout

from .slideshow import _Slide


def preview_image(parent, path, title):
    """Dialogue modal à la fenêtre affichant `path` — F11 plein écran,
    Échap ferme. Un seul aperçu à la fois : un précédent encore ouvert
    est fermé. Retourne False si l'image est illisible."""
    scr = parent.screen().availableGeometry()
    r = QImageReader(str(path))
    sz = r.size()
    if sz.isValid():
        sz.scale(scr.width(), scr.height(), Qt.KeepAspectRatio)
        r.setScaledSize(sz)
    img = r.read()
    if img.isNull():
        return False
    # un seul aperçu à la fois : un dialogue non modal pouvait rester
    # ouvert derrière la fenêtre — le suivant s'ouvrait dessous et
    # l'utilisateur revoyait la diapo qu'il venait de « fermer »
    old = getattr(parent, "_preview_dlg", None)
    if old is not None:
        try:
            old.close()      # wrapper valide seulement s'il est ouvert
        except RuntimeError:
            pass             # déjà détruit (WA_DeleteOnClose)
    d = QDialog(parent)
    d.setAttribute(Qt.WA_DeleteOnClose)
    d.setWindowModality(Qt.WindowModal)  # la fermer avant de recliquer
    d.setWindowTitle(title + "  ·  F11 plein écran")
    d.setStyleSheet("background:#000")
    d.resize(scr.width() * 3 // 4, scr.height() * 3 // 4)
    v = QVBoxLayout(d)
    v.setContentsMargins(0, 0, 0, 0)
    sl = _Slide(d)
    sl.set_slide(None, img)
    v.addWidget(sl)
    QShortcut(QKeySequence("F11"), d, activated=lambda:
              d.showNormal() if d.isFullScreen() else d.showFullScreen())
    parent._preview_dlg = d
    d.show()
    d.raise_()
    d.activateWindow()
    return True
