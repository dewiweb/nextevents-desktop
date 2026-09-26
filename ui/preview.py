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
    """Dialogue non modal affichant `path` — F11 plein écran, Échap
    ferme. Retourne False si l'image est illisible."""
    scr = parent.screen().availableGeometry()
    r = QImageReader(str(path))
    sz = r.size()
    if sz.isValid():
        sz.scale(scr.width(), scr.height(), Qt.KeepAspectRatio)
        r.setScaledSize(sz)
    img = r.read()
    if img.isNull():
        return False
    d = QDialog(parent)
    d.setAttribute(Qt.WA_DeleteOnClose)
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
    d.show()
    return True
