"""Palette, feuille de style Qt et petits widgets utilitaires
partagés par les onglets de la fenêtre principale."""

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox,
    QLineEdit,
)


class WheelGuard(QObject):
    """Empêche la molette de changer les combos/spin non focalisés :
    l'événement est refilé au conteneur scrollable parent (QScrollArea),
    donc la page scolle normalement sans risquer d'altérer une valeur.
    Installé sur QApplication → couvre tous les onglets/dialogs."""
    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Wheel
                and isinstance(obj, (QComboBox, QAbstractSpinBox))
                and not obj.hasFocus()):
            p = obj.parentWidget()
            while p is not None and not isinstance(p, QAbstractScrollArea):
                p = p.parentWidget()
            if p is not None:
                vp = p.viewport()
                QApplication.sendEvent(vp, QWheelEvent(
                    obj.mapTo(vp, event.position().toPoint()),
                    event.globalPosition(), event.pixelDelta(),
                    event.angleDelta(), event.buttons(),
                    event.modifiers(), event.phase(),
                    event.inverted()))
            return True
        return False


INK, BG, CARD, SUB, ACCENT = "#efeae6", "#141414", "#1e1d1c", \
    "#8f8c8a", "#bf4c3c"

STYLE = f"""
QMainWindow, QWidget {{ background:{BG}; color:{INK};
    font-family:'Oldschool Grotesk',system-ui,sans-serif }}
QGroupBox {{ background:{CARD}; border:1px solid #302f2e;
    border-radius:12px; margin-top:14px; padding:14px 16px 12px;
    font-size:15px }}
QGroupBox::title {{ subcontrol-origin:margin; left:14px;
    padding:0 6px; color:{INK} }}
QLabel {{ color:{SUB} }}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{ background:{BG};
    border:1px solid #302f2e; color:{INK}; border-radius:7px;
    padding:6px 10px }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus {{ border-color:#5a5652 }}
QPushButton {{ background:#302f2e; color:{INK}; border:0;
    border-radius:8px; padding:9px 20px; font-weight:500 }}
QPushButton:hover {{ background:#3a3836 }}
QPushButton:pressed {{ background:#262524 }}
QPushButton:disabled {{ opacity:.45 }}
QPushButton[accent="true"] {{ background:{ACCENT}; color:#fff }}
QPushButton[accent="true"]:hover {{ background:#cd5847 }}
QPushButton[accent="true"]:pressed {{ background:#a84131 }}
QPushButton[ghost="true"] {{ background:transparent;
    border:1px solid #3a3836; color:{SUB}; font-weight:400 }}
QPushButton[ghost="true"]:hover {{ color:{INK};
    border-color:#5a5652 }}
QPushButton[danger="true"] {{ background:transparent;
    border:1px solid #5a2a24; color:#d98a7c }}
QPushButton[danger="true"]:hover {{ background:#38201c;
    border-color:{ACCENT}; color:#fff }}
QTabWidget::pane {{ border:0 }}
QTabBar::tab {{ background:{CARD}; color:{SUB}; padding:9px 20px;
    border:1px solid #302f2e; border-bottom:0;
    border-top-left-radius:9px; border-top-right-radius:9px }}
QTabBar::tab:hover {{ color:{INK} }}
QTabBar::tab:selected {{ color:{INK}; border-color:#4a4846;
    border-top:2px solid {ACCENT} }}
QListWidget {{ background:{CARD}; border:1px solid #302f2e;
    border-radius:10px }}
#appHeader {{ background:{CARD}; border-bottom:1px solid #302f2e }}
#appTitle {{ font-size:19px; font-weight:500; color:{INK} }}
#appSub {{ font-size:12px; color:{SUB} }}
#statusChip {{ border:1px solid #302f2e; border-radius:12px;
    padding:5px 14px; color:{INK}; font-size:13px }}
QStatusBar {{ background:{CARD}; color:{SUB}; font-size:12px }}
QStatusBar QLabel {{ color:{SUB}; font-size:12px }}
QProgressBar {{ border:1px solid #302f2e; border-radius:7px;
    background:{BG} }}
QProgressBar::chunk {{ background:{ACCENT}; border-radius:6px }}
"""


def _pw(ph):
    """Champ mot de passe : vide = inchangé (placeholder selon état)."""
    w = QLineEdit()
    w.setEchoMode(QLineEdit.Password)
    w.setPlaceholderText(ph)
    return w
