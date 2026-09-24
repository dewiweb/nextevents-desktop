"""Fenêtre principale — remplace la webui (assets/webui.html).

Onglets : Général (génération, réglages, dossiers, journal),
Destinations (FTP/SMB), Diapo du jour, Diaporama (réglages de lecture,
players, galerie).
"""

import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
    QWidget,
)

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
QPushButton {{ background:#302f2e; color:{INK}; border:0;
    border-radius:8px; padding:9px 20px; font-weight:500 }}
QPushButton:disabled {{ opacity:.45 }}
QPushButton[accent="true"] {{ background:{ACCENT}; color:#fff }}
QTabWidget::pane {{ border:0 }}
QTabBar::tab {{ background:{CARD}; color:{SUB}; padding:9px 20px;
    border:1px solid #302f2e; border-bottom:0;
    border-top-left-radius:9px; border-top-right-radius:9px }}
QTabBar::tab:selected {{ color:{INK}; border-color:#4a4846 }}
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
    zip_done = Signal(str)           # message de fin d'export
    thumbs_ready = Signal(int, list) # génération, vignettes galerie

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
        self.zip_done.connect(
            lambda m: self.statusBar().showMessage(m, 6000))
        self.thumbs_ready.connect(self._fill_gallery)

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
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)

        sett = QGroupBox("Réglages")
        f = QFormLayout(sett)
        f.setLabelAlignment(Qt.AlignRight)
        self.interval = QSpinBox(minimum=0, maximum=999,
                                 suffix=" h (0 = off)")
        self.maxev = QSpinBox(minimum=0, maximum=999,
                              suffix=" (0 = tous)")
        self.res = QComboBox()
        self.res.addItem("UHD 3840×2160", "uhd")
        self.res.addItem("HD 1920×1080", "hd")
        self.gen_ls = QCheckBox("Paysage — poussé vers les partages")
        self.gen_pt = QCheckBox("Portrait — local seulement "
                                "(portrait/, zip)")
        f.addRow("Rafraîchissement auto", self.interval)
        f.addRow("Nb max d'événements", self.maxev)
        f.addRow("Résolution", self.res)
        f.addRow("Layouts générés", self.gen_ls)
        f.addRow("", self.gen_pt)
        lay.addWidget(sett)

        dirs = QGroupBox("Dossiers locaux (disque / lecteur réseau)")
        f = QFormLayout(dirs)
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
        lay.addWidget(dirs)

        log = QGroupBox("Journal")
        v = QVBoxLayout(log)
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setStyleSheet(
            "font-family:monospace;font-size:12.5px;color:#bfbbb8")
        v.addWidget(self.log)
        lay.addWidget(log, 1)
        return w

    def _destinations_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)

        ftp = QGroupBox("Destination FTP")
        f = QFormLayout(ftp)
        f.setLabelAlignment(Qt.AlignRight)
        self.ftp_host = QLineEdit(placeholderText="nas.local")
        self.ftp_port = QSpinBox(minimum=1, maximum=65535, value=21)
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
            trans = QComboBox()
            trans.addItem("Aucune", "none")
            trans.addItem("Fondu", "fade")
            trans.addItem("Glissement", "slide")
            tdur = QSpinBox(minimum=0, maximum=10000, singleStep=100,
                            suffix=" ms")
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
        rm.setProperty("ghost", True)
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
            resolution=self.res.currentData(),
            gen_landscape=int(self.gen_ls.isChecked()),
            gen_portrait=int(self.gen_pt.isChecked()),
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
            ss_delay=self.ss_delay.value(),
            ss_transition=self.ss_transition.currentData(),
            ss_tdur=self.ss_tdur.value(),
            ss_delay_p=self.ss_delay_p.value(),
            ss_transition_p=self.ss_transition_p.currentData(),
            ss_tdur_p=self.ss_tdur_p.value(),
        )
        # mot de passe vide = inchangé
        for k, w in (("ftp_pass", self.ftp_pass),
                     ("smb_pass", self.smb_pass)):
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
            for w in tab.findChildren(QComboBox):
                w.currentIndexChanged.connect(self._mark_dirty)
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

    def _load(self):
        s = load_settings()
        self.interval.setValue(s["interval_hours"])
        self.maxev.setValue(s["max_events"])
        self.res.setCurrentIndex(
            self.res.findData(s["resolution"]))
        self.gen_ls.setChecked(bool(s["gen_landscape"]))
        self.gen_pt.setChecked(bool(s["gen_portrait"]))
        self.ftp_host.setText(s["ftp_host"])
        self.ftp_port.setValue(s["ftp_port"] or 21)
        self.ftp_path.setText(s["ftp_path"])
        self.ftp_user.setText(s["ftp_user"])
        self.ftp_tls.setChecked(bool(s["ftp_tls"]))
        self.ftp_ls.setChecked(bool(s["ftp_send_landscape"]))
        self.ftp_pt.setChecked(bool(s["ftp_send_portrait"]))
        self.ftp_pass.setPlaceholderText(
            "(enregistré — vide = inchangé)" if s["ftp_pass"]
            else "(non défini)")
        self.smb_host.setText(s["smb_host"])
        self.smb_share.setText(s["smb_share"])
        self.smb_path.setText(s["smb_path"])
        self.smb_user.setText(s["smb_user"])
        self.smb_ls.setChecked(bool(s["smb_send_landscape"]))
        self.smb_pt.setChecked(bool(s["smb_send_portrait"]))
        self.smb_pass.setPlaceholderText(
            "(enregistré — vide = inchangé)" if s["smb_pass"]
            else "(non défini)")
        self.out_dir.setText(s["out_dir"])
        self.local_dir.setText(s["local_dir"])
        self.ss_delay.setValue(s["ss_delay"] or 8)
        self.ss_transition.setCurrentIndex(
            self.ss_transition.findData(s["ss_transition"]))
        self.ss_tdur.setValue(s["ss_tdur"] or 1500)
        self.ss_delay_p.setValue(s["ss_delay_p"] or 8)
        self.ss_transition_p.setCurrentIndex(
            self.ss_transition_p.findData(s["ss_transition_p"]))
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
        was = getattr(self, "_was_running", False)
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
        pix = QPixmap(str(p))
        if pix.isNull():
            return
        d = QDialog(self)
        d.setAttribute(Qt.WA_DeleteOnClose)
        d.setWindowTitle(it.text())
        v = QVBoxLayout(d)
        v.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel()
        scr = self.screen().availableGeometry()
        lbl.setPixmap(pix.scaled(scr.width() * 3 // 4,
                                 scr.height() * 3 // 4,
                                 Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation))
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
        for sub, names in (("", slides()),
                           ("portrait", slides_portrait())):
            base = d / sub if sub else d
            files += [base / n for n in names]
        self.gallery.clear()
        if not files:
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
        for rel, label, img, path in items:
            it = QListWidgetItem(label)
            it.setIcon(QPixmap.fromImage(img))
            it.setData(Qt.UserRole, rel)
            it.setToolTip(path)
            self.gallery.addItem(it)

    def _gallery_menu(self, pos):
        """Menu contextuel de la galerie : aperçu / suppression."""
        from PySide6.QtWidgets import QMenu
        it = self.gallery.itemAt(pos)
        m = QMenu(self)
        if it and it.data(Qt.UserRole):
            m.addAction("Aperçu").triggered.connect(
                lambda: self._preview_slide(it))
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
            for p in {d / base, d / "portrait" / base,
                      d / "html" / f"{stem}.html",
                      d / "portrait" / "html" / f"{stem}.html"}:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
        # manifeste : refléter la suppression dès maintenant (les
        # synchros suppriment à distance ce qui est absent en local)
        for sub in ("", "portrait"):
            dd = d / sub if sub else d
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
        # fermeture = réduire dans le tray si possible (les réglages
        # modifiés restent en mémoire, rien n'est perdu) ; sinon on
        # quitte réellement → confirmation si non enregistré
        if self._tray_ok:
            e.ignore()
            self.hide()
        elif self.confirm_quit():
            e.accept()
        else:
            e.ignore()
