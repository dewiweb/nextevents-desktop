"""Fenêtre principale — remplace la webui (assets/webui.html).

Onglets : Général (génération, réglages, dossiers, journal),
Destinations (FTP/SMB), Diapo du jour, Diaporama (réglages de lecture,
players, galerie).
"""

import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    Qt, QDate, QEvent, QObject, QTimer, QUrl, Signal,
)
from PySide6.QtGui import (
    QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea, QAbstractSpinBox, QApplication, QCheckBox,
    QComboBox, QDateEdit, QDialog, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget,
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

from nextevents.runner import run_generation, slides, slides_portrait
from nextevents.settings import (
    OUT_DIR, DEFAULTS, load_settings, resolve_out_dir, save_settings,
    state,
)
from .slideshow import SlideshowWindow
from .today import TodayTab

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


class MainWindow(QMainWindow):
    generate_done = Signal()  # émis dans le thread UI à la fin d'un run
    test_done = Signal(str, str)     # proto, résultat (thread worker)
    series_done = Signal(list)       # détection des séries (worker)
    zip_done = Signal(str)           # message de fin d'export
    thumbs_ready = Signal(int, list) # génération, vignettes galerie
    thumbs_append = Signal(list, set)  # vignettes + rels décodés (worker)
    regen_done = Signal(str, str)    # rel diapo + message de fin

    def __init__(self, tray_ok, icon_path):
        super().__init__()
        self.setWindowTitle("Nextevents")
        self.resize(1180, 860)
        self._tray_ok = tray_ok
        self._icon_path = icon_path
        self._slideshows = []
        self._log_seen = 0
        self._log_ref = None
        self._n_slides = 0
        self._sched_interval = 0
        self._io_tick = 0
        self._gal_gen = 0
        self._gal_seen = set()
        self._gal_pending = set()
        self._was_running = False
        self._dirty = False

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())

        # barre de progression fine sous l'en-tête — indéterminée,
        # visible sur tous les onglets pendant une génération
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.hide()
        root.addWidget(self.progress)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        self._tab_general = self._general_tab()
        self._tab_dest = self._destinations_tab()
        self.today_tab = TodayTab(self)
        self._tab_ss = self._slideshow_tab()
        tabs.addTab(self._tab_general, "Général")
        tabs.addTab(self._tab_dest, "Destinations")
        tabs.addTab(self.today_tab, "Diapo du jour")
        tabs.addTab(self._tab_ss, "Diaporama")
        tabs.setCurrentIndex(0)
        root.addWidget(tabs, 1)
        self.setCentralWidget(central)

        # barre de statut : rappel du planificateur à droite
        self.sched_lbl = QLabel()
        self.statusBar().addPermanentWidget(self.sched_lbl)
        self.statusBar().showMessage(
            "Ctrl+G générer · Ctrl+S enregistrer · "
            "F11 diaporama · Échap quitter le diaporama")

        QShortcut(QKeySequence("Ctrl+G"), self, activated=self._run)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save)
        QShortcut(QKeySequence("F11"), self,
                  activated=lambda: self._open_slideshow(False))
        QShortcut(QKeySequence("F5"), self,
                  activated=self._refresh_gallery)

        self._load()
        self._wire_dirty()
        self.generate_done.connect(self._after_generate)
        self.test_done.connect(self._on_test_done)
        self.series_done.connect(self._on_series_done)
        self.zip_done.connect(
            lambda m: self.statusBar().showMessage(m, 6000))
        self.thumbs_ready.connect(self._fill_gallery)
        self.regen_done.connect(self._regen_done)
        self.thumbs_append.connect(self._append_gallery)

        self._timer = QTimer(self, interval=500, timeout=self._poll)
        self._timer.start()

    # ———————————————————— en-tête ————————————————————

    def _header(self):
        h = QFrame()
        h.setObjectName("appHeader")
        lay = QHBoxLayout(h)
        lay.setContentsMargins(18, 10, 18, 10)
        lay.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(QIcon(str(self._icon_path)).pixmap(34, 34))
        lay.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel("Nextevents")
        t.setObjectName("appTitle")
        s = QLabel("Diaporama · Champs Libres")
        s.setObjectName("appSub")
        col.addWidget(t)
        col.addWidget(s)
        lay.addLayout(col)
        lay.addStretch(1)

        self.status_chip = QLabel("…")
        self.status_chip.setObjectName("statusChip")
        lay.addWidget(self.status_chip)

        self.run_btn = QPushButton("Générer")
        self.run_btn.setProperty("accent", True)
        self.run_btn.setToolTip("Lancer une génération (Ctrl+G)")
        self.run_btn.clicked.connect(self._run)
        lay.addWidget(self.run_btn)
        self.save_btn = QPushButton("Enregistrer")
        self.save_btn.setToolTip(
            "Enregistrer les réglages (Ctrl+S)")
        self.save_btn.clicked.connect(self._save)
        lay.addWidget(self.save_btn)
        return h

    # ———————————————————— construction des onglets ————————————————————

    def _general_tab(self):
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QFrame.NoFrame)
        w = QWidget()
        scroll.setWidget(w)
        outer_lay.addWidget(scroll)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)

        sett = QGroupBox("Réglages")
        f = QFormLayout(sett)
        f.setLabelAlignment(Qt.AlignRight)
        self.interval = QSpinBox(minimum=0, maximum=999,
                                 suffix=" h (0 = off)")
        self.interval.setFixedWidth(160)
        # limitation des diapos : nombre, horizon en jours, ou date
        self.limit_mode = QComboBox()
        self.limit_mode.setFixedWidth(190)
        self.limit_mode.addItem("Premiers N événements", "count")
        self.limit_mode.addItem("Dans les N jours", "days")
        self.limit_mode.addItem("Jusqu'au …", "date")
        self._limit_stack = QStackedWidget()
        self.maxev = QSpinBox(minimum=0, maximum=999,
                              suffix=" (0 = tous)")
        self.maxev.setFixedWidth(160)
        self.limit_days = QSpinBox(minimum=1, maximum=365, value=14,
                                   suffix=" jours")
        self.limit_days.setFixedWidth(160)
        self.limit_date = QDateEdit(calendarPopup=True)
        self.limit_date.setFixedWidth(160)
        self.limit_date.setDate(
            QDate.currentDate().addDays(30))
        self.limit_date.setMinimumDate(QDate.currentDate())
        self._limit_stack.addWidget(self.maxev)
        self._limit_stack.addWidget(self.limit_days)
        self._limit_stack.addWidget(self.limit_date)
        self.limit_mode.currentIndexChanged.connect(
            self._limit_stack.setCurrentIndex)
        row = QHBoxLayout()
        row.addWidget(self.limit_mode)
        row.addWidget(self._limit_stack)
        row.addStretch(1)
        self.res = QComboBox()
        self.res.setFixedWidth(220)
        self.res.addItem("UHD 3840×2160", "uhd")
        self.res.addItem("HD 1920×1080", "hd")
        self.gen_ls = QCheckBox("Paysage — dans le dossier de sortie")
        self.gen_pt = QCheckBox("Portrait — sous-dossier portrait/")
        self.portrait_fmt = QComboBox()
        self.portrait_fmt.addItem("A4 — impression", "a4")
        self.portrait_fmt.addItem("Écran 9:16 — diffusion", "screen")
        self.portrait_fmt.setEnabled(False)
        self.gen_pt.toggled.connect(self.portrait_fmt.setEnabled)
        prow = QHBoxLayout()
        prow.addWidget(self.gen_pt)
        prow.addWidget(self.portrait_fmt)
        prow.addStretch(1)
        f.addRow("Rafraîchissement auto", self.interval)
        f.addRow("Diapos générées", row)
        f.addRow("Résolution", self.res)
        f.addRow("Layouts générés", self.gen_ls)
        f.addRow("", prow)
        lay.addWidget(sett)

        catsbox = QGroupBox("Catégories générées")
        f = QFormLayout(catsbox)
        f.setLabelAlignment(Qt.AlignRight)
        self._cat_boxes = {}
        grid = QGridLayout()
        from nextevents.scrape import CATEGORIES
        for i, (label, slug) in enumerate(CATEGORIES):
            cb = QCheckBox(label)
            self._cat_boxes[slug] = cb
            grid.addWidget(cb, i // 2, i % 2)
        f.addRow(grid)
        lay.addWidget(catsbox)

        sers = QGroupBox("Séries éditoriales — identifiant = Libellé "
                         "[| logo.png] par ligne (slug de page du site "
                         "ou mot-clé OpenAgenda)")
        f = QFormLayout(sers)
        self.series_map = QPlainTextEdit()
        self.series_map.setMaximumHeight(72)
        self.series_map.setPlaceholderText(
            "grandstemoins = Les grands témoins | logo-gt.png")
        f.addRow(self.series_map)
        row = QHBoxLayout()
        det = QPushButton("Détecter dans les sources")
        det.setProperty("ghost", True)
        det.setToolTip("Scanne les mots-clés OpenAgenda et les pages "
                       "série du site, puis ajoute les candidats au champ")
        det.clicked.connect(self._detect_series)
        row.addWidget(det)
        self.series_test = QLabel()
        row.addWidget(self.series_test, 1)
        f.addRow("", row)
        lay.addWidget(sers)

        oa = QGroupBox("Source des événements")
        f = QFormLayout(oa)
        f.setLabelAlignment(Qt.AlignRight)
        self.data_source = QComboBox()
        self.data_source.addItem("Site web (scraping)", "site")
        self.data_source.addItem("OpenAgenda", "openagenda")
        f.addRow("Source", self.data_source)
        self.oa_agenda = QLineEdit(placeholderText="leschampslibres")
        self.oa_key = _pw("(non défini)")
        f.addRow("Agenda", self.oa_agenda)
        f.addRow("Clé API", self.oa_key)
        row = QHBoxLayout()
        t = QPushButton("Tester la clé")
        t.setProperty("ghost", True)
        t.clicked.connect(lambda: self._test("oa"))
        row.addWidget(t)
        self.oa_test = QLabel("")
        row.addWidget(self.oa_test)
        row.addStretch(1)
        f.addRow(row)
        lay.addWidget(oa)

        appbox = QGroupBox("Application")
        f = QFormLayout(appbox)
        f.setLabelAlignment(Qt.AlignRight)
        self.close_to_tray = QCheckBox(
            "Réduire dans la zone de notification à la fermeture")
        self.close_to_tray.setToolTip(
            "Coché : fermer la fenêtre garde l'app active dans le tray "
            "(planificateur et notifications continuent).\n"
            "Décoché : fermer la fenêtre quitte l'application.")
        if not self._tray_ok:
            # désactivée mais conserve la valeur enregistrée : un save
            # sur une machine sans tray n'efface pas la préférence
            self.close_to_tray.setEnabled(False)
            self.close_to_tray.setText(
                "Réduire dans la zone de notification "
                "(indisponible sur ce système)")
        f.addRow("Fermeture", self.close_to_tray)
        self.start_min = QCheckBox(
            "Démarrer réduite dans la zone de notification")
        if not self._tray_ok:
            self.start_min.setEnabled(False)
            self.start_min.setText(
                "Démarrer réduite (zone de notification indisponible)")
        f.addRow("Démarrage", self.start_min)
        self.autostart_ss = QComboBox()
        self.autostart_ss.setFixedWidth(220)
        self.autostart_ss.addItem("Pas de diaporama", "none")
        self.autostart_ss.addItem("Diaporama paysage", "landscape")
        self.autostart_ss.addItem("Diaporama portrait", "portrait")
        f.addRow("Au démarrage", self.autostart_ss)
        lay.addWidget(appbox)

        log = QGroupBox("Journal")
        v = QVBoxLayout(log)
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setPlaceholderText(
            "Le journal de génération s'affichera ici.")
        self.log.setStyleSheet(
            "font-family:monospace;font-size:12.5px;color:#bfbbb8")
        v.addWidget(self.log)
        log.setMinimumHeight(180)
        lay.addWidget(log, 1)
        return outer

    def _destinations_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)

        local = QGroupBox("Dossiers locaux (disque / lecteur réseau)")
        f = QFormLayout(local)
        f.setLabelAlignment(Qt.AlignRight)
        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText(
            "(vide = dossier intégré de l'app)")
        row = QHBoxLayout()
        row.addWidget(self.out_dir, 1)
        b = QPushButton("…")
        b.setProperty("ghost", True)
        b.setFixedWidth(36)
        b.clicked.connect(lambda: self._browse(self.out_dir))
        row.addWidget(b)
        f.addRow("Dossier de sortie", row)
        self.local_dir = QLineEdit()
        self.local_dir.setPlaceholderText(
            "D:\\diaporama ou \\\\serveur\\partage\\dossier")
        row = QHBoxLayout()
        row.addWidget(self.local_dir, 1)
        b = QPushButton("…")
        b.setProperty("ghost", True)
        b.setFixedWidth(36)
        b.clicked.connect(lambda: self._browse(self.local_dir))
        row.addWidget(b)
        f.addRow("Copie miroir vers", row)
        row = QHBoxLayout()
        self.local_ls = QCheckBox("Paysage")
        self.local_pt = QCheckBox("Portrait")
        row.addWidget(QLabel("Envoie :"))
        row.addWidget(self.local_ls)
        row.addWidget(self.local_pt)
        row.addStretch(1)
        f.addRow(row)
        lay.addWidget(local)

        ftp = QGroupBox("Destination FTP")
        f = QFormLayout(ftp)
        f.setLabelAlignment(Qt.AlignRight)
        self.ftp_host = QLineEdit(placeholderText="nas.local")
        self.ftp_port = QSpinBox(minimum=1, maximum=65535, value=21)
        self.ftp_port.setFixedWidth(110)
        self.ftp_path = QLineEdit(placeholderText="/diaporama")
        self.ftp_user = QLineEdit()
        self.ftp_pass = _pw("(inchangé si vide)")
        self.ftp_tls = QCheckBox("FTPS")
        f.addRow("Serveur FTP", self.ftp_host)
        f.addRow("Port", self.ftp_port)
        f.addRow("Chemin distant", self.ftp_path)
        f.addRow("Utilisateur", self.ftp_user)
        f.addRow("Mot de passe", self.ftp_pass)
        f.addRow("", self.ftp_tls)
        row = QHBoxLayout()
        self.ftp_ls = QCheckBox("Paysage")
        self.ftp_pt = QCheckBox("Portrait")
        row.addWidget(QLabel("Envoie :"))
        row.addWidget(self.ftp_ls)
        row.addWidget(self.ftp_pt)
        row.addStretch(1)
        f.addRow(row)
        row = QHBoxLayout()
        t = QPushButton("Tester la connexion")
        t.setProperty("ghost", True)
        t.clicked.connect(lambda: self._test("ftp"))
        row.addWidget(t)
        self.ftp_test = QLabel("")
        row.addWidget(self.ftp_test)
        row.addStretch(1)
        f.addRow(row)
        lay.addWidget(ftp)

        smb = QGroupBox("Destination SMB")
        f = QFormLayout(smb)
        f.setLabelAlignment(Qt.AlignRight)
        self.smb_host = QLineEdit(placeholderText="192.168.1.20")
        self.smb_share = QLineEdit(placeholderText="diaporama")
        self.smb_path = QLineEdit(placeholderText="(optionnel)")
        self.smb_user = QLineEdit(placeholderText="DOMAINE\\user")
        self.smb_pass = _pw("(inchangé si vide)")
        f.addRow("Hôte SMB", self.smb_host)
        f.addRow("Partage", self.smb_share)
        f.addRow("Sous-dossier", self.smb_path)
        f.addRow("Utilisateur", self.smb_user)
        f.addRow("Mot de passe", self.smb_pass)
        row = QHBoxLayout()
        self.smb_ls = QCheckBox("Paysage")
        self.smb_pt = QCheckBox("Portrait")
        row.addWidget(QLabel("Envoie :"))
        row.addWidget(self.smb_ls)
        row.addWidget(self.smb_pt)
        row.addStretch(1)
        f.addRow(row)
        row = QHBoxLayout()
        t = QPushButton("Tester la connexion")
        t.setProperty("ghost", True)
        t.clicked.connect(lambda: self._test("smb"))
        row.addWidget(t)
        self.smb_test = QLabel("")
        row.addWidget(self.smb_test)
        row.addStretch(1)
        f.addRow(row)
        lay.addWidget(smb)
        lay.addStretch(1)
        return w

    def _slideshow_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)

        for orientation, label in (("", "Diapos paysage"),
                                   ("_p", "Diapos portrait — local")):
            g = QGroupBox(label)
            h = QHBoxLayout(g)
            delay = QSpinBox(minimum=2, maximum=3600,
                             suffix=" s")
            delay.setFixedWidth(110)
            trans = QComboBox()
            trans.setFixedWidth(160)
            trans.addItem("Aucune", "none")
            trans.addItem("Fondu", "fade")
            trans.addItem("Glissement", "slide")
            tdur = QSpinBox(minimum=0, maximum=10000, singleStep=100,
                            suffix=" ms")
            tdur.setFixedWidth(110)
            sfx = orientation or ""
            setattr(self, "ss_delay" + sfx, delay)
            setattr(self, "ss_transition" + sfx, trans)
            setattr(self, "ss_tdur" + sfx, tdur)
            h.addWidget(QLabel("Intervalle"))
            h.addWidget(delay)
            h.addWidget(QLabel("Transition"))
            h.addWidget(trans)
            h.addWidget(QLabel("Durée"))
            h.addWidget(tdur)
            h.addStretch(1)
            b = QPushButton("Ouvrir le slideshow")
            b.setProperty("ghost", True)
            b.clicked.connect(lambda _=False, p=bool(sfx):
                              self._open_slideshow(p))
            h.addWidget(b)
            lay.addWidget(g)

        gal = QGroupBox("Galerie")
        v = QVBoxLayout(gal)
        row = QHBoxLayout()
        rf = QPushButton("Actualiser")
        rf.setProperty("ghost", True)
        rf.setToolTip("Recharger la liste des diapos (F5)")
        rf.clicked.connect(self._refresh_gallery)
        row.addWidget(rf)
        od = QPushButton("Ouvrir le dossier de sortie")
        od.setProperty("ghost", True)
        od.clicked.connect(lambda: self._open_dir(resolve_out_dir()))
        row.addWidget(od)
        dl = QPushButton("Exporter en .zip")
        dl.setProperty("ghost", True)
        dl.clicked.connect(self._download_zip)
        row.addWidget(dl)
        rm = QPushButton("Supprimer")
        rm.setProperty("danger", True)
        rm.setToolTip("Supprimer la sélection (Suppr)")
        rm.clicked.connect(self._delete_selected)
        row.addWidget(rm)
        row.addStretch(1)
        v.addLayout(row)
        self.gallery = QListWidget()
        self.gallery.setSelectionMode(QListWidget.ExtendedSelection)
        self.gallery.setContextMenuPolicy(Qt.CustomContextMenu)
        self.gallery.customContextMenuRequested.connect(
            self._gallery_menu)
        self.gallery.setViewMode(QListWidget.IconMode)
        self.gallery.setResizeMode(QListWidget.Adjust)
        self.gallery.setIconSize(QPixmap(1, 1).scaled(280, 160).size())
        # grille uniforme : les noms de fichier longs ne décalent pas
        # les colonnes — le texte est élidé au centre
        self.gallery.setUniformItemSizes(True)
        self.gallery.setGridSize(
            QPixmap(1, 1).scaled(300, 205).size())
        self.gallery.setWordWrap(False)
        self.gallery.setTextElideMode(Qt.ElideMiddle)
        self.gallery.setSpacing(8)
        self.gallery.itemDoubleClicked.connect(self._preview_slide)
        QShortcut(QKeySequence.Delete, self.gallery,
                  context=Qt.WidgetWithChildrenShortcut,
                  activated=self._delete_selected)
        v.addWidget(self.gallery)
        lay.addWidget(gal, 1)
        return w

    # ———————————————————— réglages ————————————————————

    def _collect(self):
        """Lit les widgets → dict de réglages (mêmes clés que la webui)."""
        s = load_settings()
        s.update(
            interval_hours=self.interval.value(),
            max_events=self.maxev.value(),
            limit_mode=self.limit_mode.currentData(),
            limit_days=self.limit_days.value(),
            limit_date=self.limit_date.date().toString("yyyy-MM-dd"),
            resolution=self.res.currentData(),
            gen_landscape=int(self.gen_ls.isChecked()),
            gen_portrait=int(self.gen_pt.isChecked()),
            portrait_format=self.portrait_fmt.currentData(),
            gen_categories=",".join(
                slug for slug, cb in self._cat_boxes.items()
                if cb.isChecked()),
            ftp_host=self.ftp_host.text().strip(),
            ftp_port=self.ftp_port.value(),
            ftp_path=self.ftp_path.text().strip(),
            ftp_user=self.ftp_user.text().strip(),
            ftp_tls=int(self.ftp_tls.isChecked()),
            ftp_send_landscape=int(self.ftp_ls.isChecked()),
            ftp_send_portrait=int(self.ftp_pt.isChecked()),
            smb_host=self.smb_host.text().strip(),
            smb_share=self.smb_share.text().strip(),
            smb_path=self.smb_path.text().strip(),
            smb_user=self.smb_user.text().strip(),
            smb_send_landscape=int(self.smb_ls.isChecked()),
            smb_send_portrait=int(self.smb_pt.isChecked()),
            out_dir=self.out_dir.text().strip(),
            local_dir=self.local_dir.text().strip(),
            local_send_landscape=int(self.local_ls.isChecked()),
            local_send_portrait=int(self.local_pt.isChecked()),
            close_to_tray=int(self.close_to_tray.isChecked()),
            oa_agenda=self.oa_agenda.text().strip(),
            data_source=self.data_source.currentData(),
            series_map=self.series_map.toPlainText().strip(),
            start_minimized=int(self.start_min.isChecked()),
            autostart_slideshow=self.autostart_ss.currentData(),
            ss_delay=self.ss_delay.value(),
            ss_transition=self.ss_transition.currentData(),
            ss_tdur=self.ss_tdur.value(),
            ss_delay_p=self.ss_delay_p.value(),
            ss_transition_p=self.ss_transition_p.currentData(),
            ss_tdur_p=self.ss_tdur_p.value(),
        )
        # mot de passe / clé : vide = inchangé
        for k, w in (("ftp_pass", self.ftp_pass),
                     ("smb_pass", self.smb_pass),
                     ("oa_api_key", self.oa_key)):
            if w.text():
                s[k] = w.text()
        return s

    def _save(self):
        save_settings(self._collect())
        self._clear_dirty()
        self.statusBar().showMessage("Réglages enregistrés ✓", 4000)

    # ——— réglages modifiés non enregistrés ———

    def _wire_dirty(self):
        """Surveille les widgets de réglages (onglets Général,
        Destinations, Diaporama — pas la diapo du jour, qui édite du
        contenu) pour marquer les modifications non enregistrées."""
        for tab in (self._tab_general, self._tab_dest, self._tab_ss):
            for w in tab.findChildren(QLineEdit):
                w.textChanged.connect(self._mark_dirty)
            for w in tab.findChildren(QSpinBox):
                w.valueChanged.connect(self._mark_dirty)
            for w in tab.findChildren(QDateEdit):
                w.dateChanged.connect(self._mark_dirty)
            for w in tab.findChildren(QComboBox):
                w.currentIndexChanged.connect(self._mark_dirty)
            for w in tab.findChildren(QPlainTextEdit):
                if not w.isReadOnly():  # exclut le journal de génération
                    w.textChanged.connect(self._mark_dirty)
            for w in tab.findChildren(QCheckBox):
                w.toggled.connect(self._mark_dirty)

    def _mark_dirty(self, *a):
        if self._dirty:
            return
        self._dirty = True
        self.setWindowTitle("Nextevents — réglages modifiés *")
        self.save_btn.setProperty("accent", True)
        self.save_btn.style().unpolish(self.save_btn)
        self.save_btn.style().polish(self.save_btn)

    def _clear_dirty(self):
        self._dirty = False
        self.setWindowTitle("Nextevents")
        self.save_btn.setProperty("accent", False)
        self.save_btn.style().unpolish(self.save_btn)
        self.save_btn.style().polish(self.save_btn)

    @staticmethod
    def _secret_ph(key, value):
        """Placeholder d'un champ secret — indique où la valeur vit
        (trousseau OS, variable d'env ou fichier en clair)."""
        from nextevents import secrets
        if not value:
            return "(non défini)"
        src = secrets.where(key)
        if src == "env":
            return f"(via {secrets.env_name(key)})"
        return ("(enregistré dans le trousseau — vide = inchangé)"
                if src == "keyring"
                else "(enregistré en clair dans settings.json)")

    def _load(self):
        s = load_settings()
        self.interval.setValue(s["interval_hours"])
        self.maxev.setValue(s["max_events"])
        i = self.limit_mode.findData(s.get("limit_mode") or "count")
        self.limit_mode.setCurrentIndex(max(i, 0))
        self.limit_days.setValue(int(s.get("limit_days") or 14))
        try:
            self.limit_date.setDate(
                QDate.fromString(s.get("limit_date") or "", "yyyy-MM-dd"))
        except Exception:
            pass
        self.res.setCurrentIndex(
            max(0, self.res.findData(s["resolution"])))
        self.gen_ls.setChecked(bool(s["gen_landscape"]))
        self.gen_pt.setChecked(bool(s["gen_portrait"]))
        i = self.portrait_fmt.findData(s.get("portrait_format") or "a4")
        self.portrait_fmt.setCurrentIndex(max(i, 0))
        self.portrait_fmt.setEnabled(bool(s["gen_portrait"]))
        enabled = set((s.get("gen_categories") or "").split(","))
        for slug, cb in self._cat_boxes.items():
            cb.setChecked(slug in enabled)
        self.ftp_host.setText(s["ftp_host"])
        self.ftp_port.setValue(s["ftp_port"] or 21)
        self.ftp_path.setText(s["ftp_path"])
        self.ftp_user.setText(s["ftp_user"])
        self.ftp_tls.setChecked(bool(s["ftp_tls"]))
        self.ftp_ls.setChecked(bool(s["ftp_send_landscape"]))
        self.ftp_pt.setChecked(bool(s["ftp_send_portrait"]))
        self.ftp_pass.setPlaceholderText(
            self._secret_ph("ftp_pass", s["ftp_pass"]))
        self.smb_host.setText(s["smb_host"])
        self.smb_share.setText(s["smb_share"])
        self.smb_path.setText(s["smb_path"])
        self.smb_user.setText(s["smb_user"])
        self.smb_ls.setChecked(bool(s["smb_send_landscape"]))
        self.smb_pt.setChecked(bool(s["smb_send_portrait"]))
        self.smb_pass.setPlaceholderText(
            self._secret_ph("smb_pass", s["smb_pass"]))
        self.out_dir.setText(s["out_dir"])
        self.local_dir.setText(s["local_dir"])
        self.local_ls.setChecked(bool(s.get("local_send_landscape", 1)))
        self.local_pt.setChecked(bool(s.get("local_send_portrait", 0)))
        self.oa_agenda.setText(s.get("oa_agenda") or "leschampslibres")
        i = self.data_source.findData(s.get("data_source") or "site")
        self.data_source.setCurrentIndex(max(i, 0))
        self.series_map.setPlainText(s.get("series_map") or "")
        self.oa_key.setPlaceholderText(
            self._secret_ph("oa_api_key", s.get("oa_api_key")))
        self.close_to_tray.setChecked(bool(s.get("close_to_tray", 1)))
        self.start_min.setChecked(bool(s.get("start_minimized", 0)))
        i = self.autostart_ss.findData(
            s.get("autostart_slideshow") or "none")
        self.autostart_ss.setCurrentIndex(max(i, 0))
        self.ss_delay.setValue(s["ss_delay"] or 8)
        self.ss_transition.setCurrentIndex(
            max(0, self.ss_transition.findData(s["ss_transition"])))
        self.ss_tdur.setValue(s["ss_tdur"] or 1500)
        self.ss_delay_p.setValue(s["ss_delay_p"] or 8)
        self.ss_transition_p.setCurrentIndex(
            max(0, self.ss_transition_p.findData(s["ss_transition_p"])))
        self.ss_tdur_p.setValue(s["ss_tdur_p"] or 1500)
        self._refresh_gallery()

    # ———————————————————— actions ————————————————————

    def _run(self):
        if state["running"]:
            return
        self.run_btn.setEnabled(False)
        self.log.clear()
        self._log_seen = 0
        threading.Thread(target=self._run_bg, daemon=True).start()

    def _run_bg(self):
        run_generation()

    def _after_generate(self):
        self._refresh_gallery()
        self.today_tab.load_events()

    def _poll(self):
        # journal : une génération lancée par le scheduler/tray pose
        # une NOUVELLE liste state["log"] → détecter l'identité, pas
        # juste la longueur, sinon ces logs ne s'affichent jamais
        log = state["log"]
        if log is not self._log_ref:
            self._log_ref = log
            self._log_seen = 0
            self.log.clear()
        if len(log) > self._log_seen:
            self.log.appendPlainText("\n".join(log[self._log_seen:]))
            self._log_seen = len(log)
            sb = self.log.verticalScrollBar()
            sb.setValue(sb.maximum())
        # statut
        was = self._was_running
        running = state["running"]
        self._was_running = running
        if was and not running:
            self.generate_done.emit()
        self.run_btn.setEnabled(not running)
        self.run_btn.setText("Génération…" if running else "Générer")
        self.progress.setVisible(running or self.today_tab._busy)
        # I/O disque/réseau (glob du dossier de sortie, relecture des
        # réglages) : toutes les ~5 s et à chaque changement d'état —
        # un dossier réseau déconnecté ne doit pas geler l'UI à chaque
        # tick de 500 ms
        self._io_tick += 1
        if self._io_tick >= 10 or was != running:
            self._io_tick = 0
            self._n_slides = len(slides())
            self._sched_interval = load_settings()["interval_hours"]
            if running:
                self._gallery_incremental()
        lr = state["last_run"]
        try:
            last = (datetime.fromtimestamp(lr).strftime("%d/%m %H:%M")
                    if lr else "jamais")
        except (TypeError, ValueError, OSError):
            last = "jamais"
        err = state["last_error"]
        txt = (("⟳ génération… · " if running else "")
               + (f"⚠ {err} · " if err and not running else "")
               + f"{self._n_slides} diapos · {last}")
        self.status_chip.setText(txt)
        self.status_chip.setStyleSheet(
            "color:#f6e3bb" if running else
            "color:#c99483" if err else "")
        h = self._sched_interval
        self.sched_lbl.setText(
            f"auto : toutes les {h} h" if h else "auto : off")

    def _test(self, proto):
        self._save()
        lbl = getattr(self, f"{proto}_test")
        lbl.setText("test…")
        s = load_settings()

        def work():
            try:
                if proto == "ftp":
                    import ftplib
                    cls = ftplib.FTP_TLS if s["ftp_tls"] else ftplib.FTP
                    ftp = cls()
                    ftp.connect(s["ftp_host"], s["ftp_port"], timeout=15)
                    ftp.login(s["ftp_user"], s["ftp_pass"])
                    if s["ftp_tls"]:
                        ftp.prot_p()
                    # mkd avant cwd : la synchro crée les dossiers
                    # manquants, le test doit valider le même parcours
                    for p in [p for p in s["ftp_path"].split("/") if p]:
                        try:
                            ftp.cwd(p)
                        except ftplib.error_perm:
                            ftp.mkd(p)
                            ftp.cwd(p)
                    ftp.quit()
                elif proto == "oa":
                    import requests
                    r = requests.get(
                        "https://api.openagenda.com/v2/agendas/"
                        f"{s['oa_agenda']}/events",
                        params={"key": s["oa_api_key"], "size": 1},
                        timeout=15)
                    r.raise_for_status()
                else:
                    from smbclient import listdir, register_session
                    register_session(s["smb_host"], username=s["smb_user"],
                                     password=s["smb_pass"])
                    path = f"\\\\{s['smb_host']}\\{s['smb_share']}"
                    if s["smb_path"]:
                        path += "\\" + s["smb_path"].strip("/\\")
                    listdir(path)
                res = "connexion OK ✓"
            except Exception as e:
                res = f"échec : {e}"
            # Signal → livré dans le thread GUI (un QTimer.singleShot
            # émis depuis un worker sans event loop serait perdu)
            self.test_done.emit(proto, res)

        threading.Thread(target=work, daemon=True).start()

    def _on_test_done(self, proto, res):
        getattr(self, f"{proto}_test").setText(res)

    def _detect_series(self):
        """Scanne OA (keywords) et le site (pages série) en worker —
        ajoute les candidats manquants au champ, sans rien écraser."""
        self.series_test.setText("détection…")
        s = load_settings()

        def work():
            try:
                from nextevents.oa import detect_series
                found = detect_series(s.get("oa_agenda") or
                                      "leschampslibres")
            except Exception as e:
                found = [("__erreur__", str(e))]
            self.series_done.emit(found)

        threading.Thread(target=work, daemon=True).start()

    def _on_series_done(self, found):
        if found and found[0][0] == "__erreur__":
            self.series_test.setText(f"échec : {found[0][1]}")
            return
        existing = {l.split("=", 1)[0].strip() for l in
                    self.series_map.toPlainText().splitlines()
                    if "=" in l}
        added = [f"{k} = {v}" for k, v in found if k not in existing]
        if added:
            cur = self.series_map.toPlainText().rstrip()
            self.series_map.setPlainText(
                (cur + "\n" if cur else "") + "\n".join(added))
            self._mark_dirty()
        self.series_test.setText(
            f"{len(added)} série(s) ajoutée(s), "
            f"{len(found) - len(added)} déjà listée(s)")

    def _browse(self, field):
        d = QFileDialog.getExistingDirectory(
            self, "Choisir un dossier", field.text() or str(OUT_DIR))
        if d:
            field.setText(d)

    def _open_dir(self, path):
        import subprocess, sys
        try:
            path.mkdir(parents=True, exist_ok=True)
            p = str(path)
            if sys.platform == "win32":
                import os
                os.startfile(p)
            else:
                subprocess.Popen(["xdg-open", p])
        except OSError as e:
            self.statusBar().showMessage(
                f"Impossible d'ouvrir le dossier : {e}", 5000)

    def _open_slideshow(self, portrait):
        # une seule fenêtre par orientation : re-solliciter lève
        # l'existante plutôt que d'empiler les plein écran
        for w in self._slideshows:
            if w.portrait == portrait:
                w._reload()
                w.showFullScreen()
                w.raise_()
                w.activateWindow()
                return
        win = SlideshowWindow(portrait=portrait)
        win.setAttribute(Qt.WA_DeleteOnClose)
        self._slideshows.append(win)
        win.destroyed.connect(
            lambda *a, w=win: self._slideshows.remove(w)
            if w in self._slideshows else None)

    def _download_zip(self):
        out = resolve_out_dir()
        dest, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le zip", "nextevents-diapos.zip",
            "Archives zip (*.zip)")
        if not dest:
            return
        self.statusBar().showMessage("Export en cours…")

        def work():
            import zipfile
            try:
                with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                    for p in sorted(out.rglob("*")):
                        if p.is_file() and p.name != "settings.json":
                            try:
                                z.write(p, p.relative_to(out))
                            except OSError:
                                pass  # fichier disparu en cours d'export
                msg = f"Exporté → {dest}"
            except Exception as e:
                msg = f"Export échoué : {e}"
            self.zip_done.emit(msg)

        threading.Thread(target=work, daemon=True).start()

    def _preview_slide(self, it):
        """Aperçu intégré d'une diapo de la galerie (double-clic)."""
        rel = it.data(Qt.UserRole)
        if not rel:
            return
        p = resolve_out_dir() / rel
        scr = self.screen().availableGeometry()
        # décodage direct à la taille d'affichage : un PNG UHD complet
        # prendrait ~150 ms sur le thread GUI
        from PySide6.QtGui import QImageReader
        r = QImageReader(str(p))
        sz = r.size()
        if sz.isValid():
            sz.scale(scr.width() * 3 // 4, scr.height() * 3 // 4,
                     Qt.KeepAspectRatio)
            r.setScaledSize(sz)
        img = r.read()
        if img.isNull():
            return
        d = QDialog(self)
        d.setAttribute(Qt.WA_DeleteOnClose)
        d.setWindowTitle(it.text())
        v = QVBoxLayout(d)
        v.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel()
        lbl.setPixmap(QPixmap.fromImage(img))
        v.addWidget(lbl)
        d.exec()

    def _refresh_gallery(self):
        """Recharge la liste puis décode les vignettes dans un thread —
        un PNG UHD pèse plusieurs Mo, les décoder en série dans la
        boucle UI gèlerait la fenêtre plusieurs secondes."""
        self._gal_gen += 1
        gen = self._gal_gen
        d = resolve_out_dir()
        files = []
        for sub, names in (("landscape", slides()),
                           ("portrait", slides_portrait())):
            files += [d / sub / n for n in names]
        self.gallery.clear()
        if not files:
            self._gal_seen = set()   # le suivi incrémental part de zéro
            it = QListWidgetItem(
                "Aucune diapo — lancez une génération (Ctrl+G)")
            it.setFlags(Qt.NoItemFlags)
            it.setTextAlignment(Qt.AlignCenter)
            self.gallery.addItem(it)
            return

        def work():
            from PySide6.QtGui import QImageReader
            items = []
            for p in files:
                r = QImageReader(str(p))
                sz = r.size()
                if sz.isValid():
                    sz.scale(280, 160, Qt.KeepAspectRatio)
                    r.setScaledSize(sz)
                img = r.read()
                if img.isNull():
                    continue
                rel = str(p.relative_to(d))
                label = p.name.removeprefix("slide-").removesuffix(".png")
                # la variante portrait porte le même nom que la paysage
                # → suffixe pour distinguer les jumelles dans la grille
                if p.parent.name == "portrait":
                    label += "  ▯"
                items.append((rel, label, img, str(p)))
            self.thumbs_ready.emit(gen, items)

        threading.Thread(target=work, daemon=True).start()

    def _fill_gallery(self, gen, items):
        if gen != self._gal_gen:
            return  # un rafraîchissement plus récent est en cours
        self.gallery.clear()
        self._gal_seen = {rel for rel, _, _, _ in items}
        for rel, label, img, path in items:
            it = QListWidgetItem(label)
            it.setIcon(QPixmap.fromImage(img))
            it.setData(Qt.UserRole, rel)
            it.setToolTip(path)
            self.gallery.addItem(it)

    def _gallery_incremental(self):
        """Ajoute à la galerie les PNG apparus depuis le dernier
        passage — les diapos deviennent visibles pendant la génération
        au lieu d'attendre la fin du run."""
        d = resolve_out_dir()
        new = []
        for sub, names in (("landscape", slides()),
                           ("portrait", slides_portrait())):
            new += [d / sub / n for n in names]
        new = [p for p in new
               if (rel := str(p.relative_to(d))) not in self._gal_seen
               and rel not in self._gal_pending]
        if not new:
            return
        # « pending » évite les décodages en double tant que le worker
        # tourne ; « seen » n'est posé qu'au décodage réussi, sinon le
        # fichier est retenté au prochain passage
        self._gal_pending.update(str(p.relative_to(d)) for p in new)

        def work():
            from PySide6.QtGui import QImageReader
            items = []
            for p in new:
                rel = str(p.relative_to(d))
                r = QImageReader(str(p))
                sz = r.size()
                if sz.isValid():
                    sz.scale(280, 160, Qt.KeepAspectRatio)
                    r.setScaledSize(sz)
                img = r.read()
                if img.isNull():
                    items.append((rel, None, None, None))
                    continue
                label = p.name.removeprefix("slide-").removesuffix(".png")
                if p.parent.name == "portrait":
                    label += "  ▯"
                items.append((rel, label, img, str(p)))
            self.thumbs_append.emit(
                items, {str(p.relative_to(d)) for p in new})

        threading.Thread(target=work, daemon=True).start()

    def _append_gallery(self, items, decoded):
        self._gal_pending -= decoded
        # un refresh complet a pu afficher ces fichiers entre-temps
        items = [t for t in items if t[2] is not None
                 and t[0] not in self._gal_seen]
        self._gal_seen.update(t[0] for t in items)
        if not items:
            return
        # retire le placeholder « aucune diapo » s'il est encore là
        if (self.gallery.count() == 1
                and not self.gallery.item(0).data(Qt.UserRole)):
            self.gallery.clear()
        for rel, label, img, path in items:
            it = QListWidgetItem(label)
            it.setIcon(QPixmap.fromImage(img))
            it.setData(Qt.UserRole, rel)
            it.setToolTip(path)
            self.gallery.addItem(it)

    def _event_for(self, stem):
        """Retrouve l'événement dans events.json à partir du nom de la
        diapo (fiche OA/site, régénération à la demande)."""
        import json
        try:
            events = json.loads(
                (resolve_out_dir() / "events.json").read_text("utf-8"))
        except Exception:
            return None
        for e in events:
            s = e.get("slide")
            # collisions date+titre : slide_name suffixe « -N »
            if s == stem or (s and stem.startswith(s + "-")
                             and stem[len(s) + 1:].isdigit()):
                return e
        return None

    def _regen_slide(self, it):
        """Re-rend une seule diapo depuis events.json (image servie par
        le cache — pas de re-téléchargement si elle n'a pas changé)."""
        from nextevents.slide import (
            DEFAULT_SIZE, SIZES, portrait_key, portrait_size)
        rel = it.data(Qt.UserRole)
        ev = self._event_for(Path(rel).stem)
        if not ev:
            self.statusBar().showMessage(
                "Événement introuvable — régénérez tout d'abord", 4000)
            return
        if state["running"]:
            self.statusBar().showMessage(
                "Génération en cours — régénération impossible", 4000)
            return
        stem = Path(rel).stem
        portrait = rel.startswith("portrait/")
        sub = Path(rel).parent
        if str(sub) == ".":  # rel ancien format sans sous-dossier
            sub = Path("portrait" if portrait else "landscape")
        cfg = load_settings()
        size = SIZES.get(cfg.get("resolution"), DEFAULT_SIZE)
        fmt = cfg.get("portrait_format") or "a4"
        orientation = portrait_key(fmt) if portrait else "landscape"
        psize = portrait_size(size, fmt) if portrait else size
        self.statusBar().showMessage(f"Régénération de {stem}…")

        def work():
            try:
                from nextevents.media import download_image, ensure_fonts
                from nextevents.slide import render_all, slide_html
                download_image(ev)
                fonts = ensure_fonts()
                dest = resolve_out_dir() / sub
                (dest / "html").mkdir(exist_ok=True)
                hp = dest / "html" / f"{stem}.html"
                hp.write_text(
                    slide_html(ev, 0, fonts, orientation),
                    encoding="utf-8")
                # render_all est un générateur : il faut l'itérer
                # pour que le rendu s'exécute
                if not list(render_all(
                        [(hp, dest / f"{stem}.png")], psize,
                        orientation)):
                    raise RuntimeError("rendu vide")
                self.regen_done.emit(rel, f"{stem} régénérée")
            except Exception as e:
                self.regen_done.emit("", f"Régénération KO : {e}")

        threading.Thread(target=work, daemon=True).start()

    def _regen_done(self, rel, msg):
        """Fin de régénération : recharge la vignette concernée."""
        self.statusBar().showMessage(msg, 5000)
        if not rel:
            return
        for i in range(self.gallery.count()):
            it = self.gallery.item(i)
            if it.data(Qt.UserRole) == rel:
                # même décodage réduit que les vignettes du worker
                from PySide6.QtGui import QImageReader
                r = QImageReader(str(resolve_out_dir() / rel))
                sz = r.size()
                if sz.isValid():
                    sz.scale(280, 160, Qt.KeepAspectRatio)
                    r.setScaledSize(sz)
                img = r.read()
                if not img.isNull():
                    it.setIcon(QPixmap.fromImage(img))
                break

    def _gallery_menu(self, pos):
        """Menu contextuel de la galerie : aperçu / fiche / suppression."""
        from PySide6.QtWidgets import QMenu
        it = self.gallery.itemAt(pos)
        m = QMenu(self)
        if it and it.data(Qt.UserRole):
            m.addAction("Aperçu").triggered.connect(
                lambda: self._preview_slide(it))
            ev = self._event_for(Path(it.data(Qt.UserRole)).stem)
            if ev:
                m.addAction("Régénérer cette diapo").triggered.connect(
                    lambda: self._regen_slide(it))
            url = (ev or {}).get("url")
            if url:
                m.addAction("Ouvrir la fiche de l'événement").triggered\
                    .connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        if self.gallery.selectedItems():
            m.addAction("Supprimer la sélection…").triggered.connect(
                self._delete_selected)
        if m.actions():
            m.exec(self.gallery.viewport().mapToGlobal(pos))

    def _delete_selected(self):
        """Supprime les diapos sélectionnées : PNG paysage + portrait +
        HTML source (toutes les variantes), puis met manifest.txt à jour
        pour que la prochaine synchro propage la suppression."""
        items = [it for it in self.gallery.selectedItems()
                 if it.data(Qt.UserRole)]
        if not items:
            return
        if state["running"]:
            self.statusBar().showMessage(
                "Génération en cours — suppression impossible", 4000)
            return
        from PySide6.QtWidgets import QMessageBox
        n_diapos = len({Path(it.data(Qt.UserRole)).name
                        for it in items})
        r = QMessageBox.question(
            self, "Supprimer",
            f"Supprimer {n_diapos} diapo(s) ?\n\n"
            "Toutes les variantes sont supprimées (paysage, portrait, "
            "HTML). La synchro les retirera aussi des destinations.\n"
            "Attention : une diapo sera régénérée à la prochaine "
            "génération si son événement est toujours publié.",
            QMessageBox.Yes | QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        d = resolve_out_dir()
        for it in items:
            base = Path(it.data(Qt.UserRole)).name
            stem = Path(base).stem
            for p in {d / "landscape" / base, d / "portrait" / base,
                      d / "landscape" / "html" / f"{stem}.html",
                      d / "portrait" / "html" / f"{stem}.html"}:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
        # manifeste : refléter la suppression dès maintenant (les
        # synchros suppriment à distance ce qui est absent en local)
        for sub in ("landscape", "portrait"):
            dd = d / sub
            mf = dd / "manifest.txt"
            if mf.exists():
                mf.write_text(
                    "".join(f"{p.name}\n"
                            for p in sorted(dd.glob("*.png"))),
                    encoding="utf-8")
        self.statusBar().showMessage(
            f"{n_diapos} diapo(s) supprimée(s)", 4000)
        self._refresh_gallery()

    def confirm_quit(self):
        """True si on peut quitter — propose d'enregistrer si des
        réglages sont modifiés."""
        if not self._dirty:
            return True
        from PySide6.QtWidgets import QMessageBox
        r = QMessageBox.question(
            self, "Réglages modifiés",
            "Enregistrer les modifications avant de quitter ?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            self._save()
        return True

    def closeEvent(self, e):
        # fermeture : réduire dans le tray si l'option est active
        # (réglage persisté — les modifs non enregistrées restent en
        # mémoire, rien n'est perdu) ; sinon on quitte réellement →
        # confirmations génération en cours / réglages modifiés
        if self._tray_ok and load_settings().get("close_to_tray", 1):
            e.ignore()
            self.hide()
            return
        from PySide6.QtWidgets import QMessageBox
        if state["running"]:
            r = QMessageBox.question(
                self, "Quitter Nextevents",
                "Une génération est en cours — quitter quand même ?",
                QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
        if not self.confirm_quit():
            e.ignore()
            return
        e.accept()
        # quitOnLastWindowClosed est False quand un tray existe :
        # fermer ne suffit pas à terminer le process
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()
