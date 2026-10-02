"""Impression des diapos via QtPrintSupport — une diapo par page,
ajustée à la feuille. Le dialogue natif couvre aussi « imprimer en
PDF » (Microsoft Print to PDF, CUPS PDF) — un export PDF de la
galerie est donc inclus sans code supplémentaire."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPageLayout, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QMessageBox


def print_images(paths, parent=None):
    """Imprime `paths` (PNG), une image par page ajustée à la feuille
    (KeepAspectRatio, centrée, orientation de page suivant le format
    de la diapo — portrait pour les diapos A4).
    Retourne True si l'impression a été lancée."""
    paths = [Path(p) for p in paths]
    if not paths:
        return False
    printer = QPrinter(QPrinter.HighResolution)
    dlg = QPrintDialog(printer, parent)
    dlg.setWindowTitle(
        f"Imprimer {len(paths)} diapo(s)")
    if dlg.exec() != QPrintDialog.Accepted:
        return False

    painter = QPainter(printer)
    for i, p in enumerate(paths):
        img = QImage(str(p))
        if img.isNull():
            continue
        # orientation de la page suivant le ratio de la diapo —
        # changement effectif pour la page courante ET les suivantes,
        # donc appliqué avant chaque newPage
        lay = printer.pageLayout()
        lay.setOrientation(
            QPageLayout.Landscape if img.width() > img.height()
            else QPageLayout.Portrait)
        printer.setPageLayout(lay)
        if i:
            printer.newPage()
        rect = printer.pageRect(QPrinter.DevicePixel)
        scaled = img.scaled(
            int(rect.width()), int(rect.height()),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawImage(
            int((rect.width() - scaled.width()) / 2),
            int((rect.height() - scaled.height()) / 2), scaled)
    painter.end()
    return True


def ask_print_all(count, parent=None):
    """Confirmation avant d'imprimer toute une galerie (potentiellement
    plusieurs dizaines de pages)."""
    r = QMessageBox.question(
        parent, "Imprimer",
        f"Imprimer les {count} diapos de la galerie ?\n\n"
        "Une diapo par page. Choisis « Microsoft Print to PDF » dans "
        "le dialogue pour produire un PDF plutôt que du papier.",
        QMessageBox.Yes | QMessageBox.No)
    return r == QMessageBox.Yes
