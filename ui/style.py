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

import sys
from pathlib import Path

# url() d'une stylesheet Qt : chemin absolu, slashs POSIX (Windows
# inclus) — en mode frozen les assets vivent dans _MEIPASS
_base = Path(getattr(sys, "_MEIPASS",
                     Path(__file__).resolve().parent.parent))
CHECK_IMG = (_base / "assets" / "check.svg").as_posix()
ARROW_DOWN = (_base / "assets" / "arrow-down.svg").as_posix()
ARROW_UP = (_base / "assets" / "arrow-up.svg").as_posix()
ARROW_LEFT = (_base / "assets" / "arrow-left.svg").as_posix()
ARROW_RIGHT = (_base / "assets" / "arrow-right.svg").as_posix()
FOLDER_IMG = (_base / "assets" / "folder.svg").as_posix()
HELP_IMG = (_base / "assets" / "help.svg").as_posix()
PLUS_IMG = (_base / "assets" / "plus.svg").as_posix()
X_IMG = (_base / "assets" / "x.svg").as_posix()

STYLE = f"""
QMainWindow, QWidget {{ background:{BG}; color:{INK};
    font-family:'Oldschool Grotesk',system-ui,sans-serif }}
QGroupBox {{ background:{CARD}; border:1px solid #302f2e;
    border-radius:12px; margin-top:14px; padding:14px 16px 12px;
    font-size:15px }}
QGroupBox::title {{ subcontrol-origin:margin; left:14px;
    padding:0 6px; color:{INK} }}
QLabel {{ color:{SUB}; background:transparent }}
QCheckBox, QRadioButton {{ background:transparent; spacing:8px;
    color:{INK} }}
QCheckBox::indicator, QRadioButton::indicator {{
    width:15px; height:15px; background:{BG};
    border:1px solid #565452; border-radius:4px }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color:{SUB} }}
QCheckBox::indicator:checked {{ background:{ACCENT};
    border-color:{ACCENT}; image:url({CHECK_IMG}) }}
QRadioButton::indicator {{ border-radius:8px }}
QRadioButton::indicator:checked {{ background:{ACCENT};
    border-color:{ACCENT}; image:url({CHECK_IMG}) }}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{ background:{BG};
    border:1px solid #302f2e; color:{INK}; border-radius:7px;
    padding:6px 10px }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus {{ border-color:#5a5652 }}
QComboBox::drop-down {{ width:24px; border:0 }}
QComboBox::down-arrow {{ image:url({ARROW_DOWN});
    width:11px; height:11px }}
QComboBox::down-arrow:disabled {{ image:none }}
QComboBox QAbstractItemView {{ background:{CARD}; color:{INK};
    border:1px solid #302f2e;
    selection-background-color:#302f2e; outline:0 }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    background:#262524; width:18px; border:0 }}
QAbstractSpinBox::up-button:hover,
QAbstractSpinBox::down-button:hover {{ background:#3a3836 }}
QAbstractSpinBox::up-arrow {{ image:url({ARROW_UP});
    width:9px; height:9px }}
QAbstractSpinBox::down-arrow {{ image:url({ARROW_DOWN});
    width:9px; height:9px }}
QScrollBar:vertical {{ background:transparent; width:12px; margin:0 }}
QScrollBar:horizontal {{ background:transparent; height:12px; margin:0 }}
QScrollBar::handle {{ background:#302f2e; border-radius:6px;
    min-height:30px; min-width:30px }}
QScrollBar::handle:hover {{ background:#3a3836 }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; width:0;
    border:0; background:transparent }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent }}
QTabBar QToolButton {{ color:{INK}; background:{CARD} }}
QTabBar QToolButton:hover {{ color:{ACCENT} }}
QCalendarWidget QToolButton {{ color:{INK} }}
QCalendarWidget QToolButton#qt_calendar_prev {{
    qproperty-icon:url({ARROW_LEFT}) }}
QCalendarWidget QToolButton#qt_calendar_next {{
    qproperty-icon:url({ARROW_RIGHT}) }}
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


def browse_btn(cb):
    """Bouton fantôme « choisir un dossier » — icône dossier claire
    (le glyphe « … » était quasi invisible sur le thème sombre)."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QPushButton
    b = QPushButton()
    b.setProperty("ghost", True)
    b.setIcon(QIcon(FOLDER_IMG))
    b.setIconSize(QSize(15, 15))
    b.setFixedWidth(36)
    b.setToolTip("Choisir un dossier…")
    b.clicked.connect(cb)
    return b
