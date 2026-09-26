"""Fenêtre principale — remplace la webui (assets/webui.html).

Onglets : Général (génération, réglages, dossiers, journal),
Destinations (FTP/SMB), Diapo du jour, Diaporama (réglages de lecture,
players, galerie).

Découpage : les trois onglets lourds vivent dans des mixins
(ui/tabs_general.py, ui/tabs_destinations.py, ui/tabs_gallery.py) —
ce module garde la fenêtre, l'en-tête, la collecte/sauvegarde des
réglages, le polling d'état et la gestion de sortie. Règle projet
(.devin/rules/large-files.md) : ne pas laisser ce fichier repasser
1000 lignes sans réétudier un split.
"""

import threading
from datetime import datetime

from PySide6.QtCore import (
    QDate, QTimer, Signal,
)
from PySide6.QtGui import (
    QIcon, QKeySequence, QShortcut,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QProgressBar,
    QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from nextevents.runner import run_generation, slides
from nextevents.settings import (
    load_settings, save_settings, state,
)
from .style import STYLE, WheelGuard  # noqa: F401 — ré-export pour ui.app
from .tabs_general import GeneralTabMixin
from .tabs_destinations import DestinationsTabMixin
from .tabs_gallery import GalleryTabMixin
from .today import TodayTab


class MainWindow(GeneralTabMixin, DestinationsTabMixin, GalleryTabMixin,
                 QMainWindow):
    generate_done = Signal()  # émis dans le thread UI à la fin d'un run
    test_done = Signal(str, str)     # proto, résultat (thread worker)
    series_done = Signal(list)       # détection des séries (worker)
    zip_done = Signal(str)           # message de fin d'export
    thumbs_ready = Signal(int, list) # génération, vignettes galerie
    thumbs_append = Signal(list, set)  # vignettes + rels décodés (worker)
    regen_done = Signal(str, str)    # rel diapo + message de fin
    update_done = Signal(str, str)   # tag release, url ou erreur

    def __init__(self, tray_ok, icon_path):
        super().__init__()
        self.setWindowTitle("Nextevents")
        # taille initiale bornée par l'écran : un poste en 1366×768
        # recevait une fenêtre de 860 px — plus haute que la zone utile
        from PySide6.QtWidgets import QApplication
        scr = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1180, int(scr.width() * 0.92)),
                    min(860, int(scr.height() * 0.92)))
        self.setMinimumSize(760, 460)
        self._tray_ok = tray_ok
        self._icon_path = icon_path
        self._slideshows = []
        self._log_seen = 0
        self._log_ref = None
        self._n_slides = 0
        self._sched_interval = 0
        self._sched_times = ""
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
        self._tab_ss = self._gallery_tab()
        tabs.addTab(self._tab_general, "Général")
        tabs.addTab(self._tab_dest, "Destinations")
        tabs.addTab(self.today_tab, "Diapo du jour")
        tabs.addTab(self._tab_ss, "Galerie")
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
        self.update_done.connect(self._on_update_done)

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
        from nextevents.version import VERSION
        s = QLabel(f"Diaporama · Champs Libres · v{VERSION}")
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

    # ———————————————————— réglages ————————————————————

    def _collect(self):
        """Lit les widgets → dict de réglages (mêmes clés que la webui)."""
        s = load_settings()
        s.pop("interval_hours", None)  # remplacé par interval_min
        s.update(
            interval_min=self.interval.value(),
            sched_times=self.sched_times.text().strip(),
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
            autostart_app=int(self.autostart_app.isChecked()),
            autostart_slideshow=self.autostart_ss.currentData(),
            ss_delay=self.ss_delay.value(),
            ss_transition=self.ss_transition.currentData(),
            ss_tdur=self.ss_tdur.value(),
            ss_screen=self.ss_screen.currentData(),
            ss_delay_p=self.ss_delay_p.value(),
            ss_transition_p=self.ss_transition_p.currentData(),
            ss_tdur_p=self.ss_tdur_p.value(),
            ss_screen_p=self.ss_screen_p.currentData(),
        )
        # mot de passe / clé : vide = inchangé
        for k, w in (("ftp_pass", self.ftp_pass),
                     ("smb_pass", self.smb_pass),
                     ("oa_api_key", self.oa_key)):
            if w.text():
                s[k] = w.text()
        return s

    def _save(self):
        s = self._collect()
        save_settings(s)
        # autostart : appliqué côté OS uniquement si l'état réel diffère
        # (idempotent — pas de clé/.desktop réécrit à chaque save)
        try:
            from nextevents import autostart
            want = bool(s.get("autostart_app"))
            if want != autostart.is_enabled():
                autostart.apply(want)
        except Exception as e:
            self.statusBar().showMessage(
                f"Réglages enregistrés — autostart KO : {e}", 6000)
            self._clear_dirty()
            return
        self._clear_dirty()
        self.statusBar().showMessage("Réglages enregistrés ✓", 4000)

    # ——— réglages modifiés non enregistrés ———

    def _wire_dirty(self):
        """Surveille les widgets de réglages (onglets Général,
        Destinations, Diaporama — pas la diapo du jour, qui édite du
        contenu) pour marquer les modifications non enregistrées."""
        from PySide6.QtWidgets import (
            QCheckBox, QComboBox, QDateEdit, QLineEdit, QPlainTextEdit,
            QSpinBox,
        )
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
        from nextevents.runner import _interval_min
        self.interval.setValue(_interval_min(s))
        self.sched_times.setText(s.get("sched_times") or "")
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
        self.autostart_app.setChecked(bool(s.get("autostart_app")))
        self.ss_delay.setValue(s["ss_delay"] or 8)
        self.ss_transition.setCurrentIndex(
            max(0, self.ss_transition.findData(s["ss_transition"])))
        self.ss_tdur.setValue(s["ss_tdur"] or 1500)
        i = self.ss_screen.findData(int(s.get("ss_screen") or -1))
        self.ss_screen.setCurrentIndex(max(i, 0))
        self.ss_delay_p.setValue(s["ss_delay_p"] or 8)
        self.ss_transition_p.setCurrentIndex(
            max(0, self.ss_transition_p.findData(s["ss_transition_p"])))
        self.ss_tdur_p.setValue(s["ss_tdur_p"] or 1500)
        i = self.ss_screen_p.findData(int(s.get("ss_screen_p") or -1))
        self.ss_screen_p.setCurrentIndex(max(i, 0))
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
            s = load_settings()
            from nextevents.runner import _interval_min
            self._sched_interval = _interval_min(s)
            self._sched_times = (s.get("sched_times") or "").strip()
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
        bits = []
        m = self._sched_interval
        if m:
            bits.append(f"{m} min" if m < 60 else f"{m//60} h")
        if self._sched_times:
            bits.append(self._sched_times)
        self.sched_lbl.setText(
            "auto : " + " + ".join(bits) if bits else "auto : off")

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

    # ———————————————————— sortie ————————————————————

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
