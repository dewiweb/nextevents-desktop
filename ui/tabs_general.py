"""Onglet « Général » — mixin de MainWindow (aucun __init__ propre :
les méthodes sont appelées sur la fenêtre, qui fournit les signaux,
_mark_dirty et les widgets partagés)."""

import threading

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFormLayout, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QVBoxLayout, QWidget,
)

from nextevents.settings import load_settings
from .style import _pw


class GeneralTabMixin:

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
        self.autostart_app = QCheckBox(
            "Lancer l'application à l'ouverture de session")
        self.autostart_app.setToolTip(
            "Indispensable sur un poste d'affichage : sans ça, un "
            "redémarrage (Windows Update, coupure) laisse l'écran vide.")
        f.addRow("Session", self.autostart_app)
        self.autostart_ss = QComboBox()
        self.autostart_ss.setFixedWidth(220)
        self.autostart_ss.addItem("Pas de diaporama", "none")
        self.autostart_ss.addItem("Diaporama paysage", "landscape")
        self.autostart_ss.addItem("Diaporama portrait", "portrait")
        f.addRow("Au démarrage", self.autostart_ss)
        row = QHBoxLayout()
        u = QPushButton("Vérifier les mises à jour")
        u.setProperty("ghost", True)
        u.clicked.connect(self._check_update)
        row.addWidget(u)
        self.update_lbl = QLabel()
        self.update_lbl.setOpenExternalLinks(True)
        row.addWidget(self.update_lbl, 1)
        from nextevents.version import VERSION
        f.addRow(f"Version {VERSION}", row)
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

    def _check_update(self):
        """Interroge l'API GitHub releases en worker — résultat livré
        par le signal update_done dans le thread GUI."""
        self.update_lbl.setText("recherche…")

        def work():
            try:
                from nextevents.net import get
                d = get("https://api.github.com/repos/dewiweb/"
                        "nextevents-desktop/releases/latest").json()
                self.update_done.emit(d.get("tag_name") or "",
                                      d.get("html_url") or "")
            except Exception as e:
                self.update_done.emit("", str(e))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_done(self, tag, url_or_err):
        if not tag:
            self.update_lbl.setText(f"échec : {url_or_err}")
            return
        from nextevents.version import VERSION, newer_than_current
        if newer_than_current(tag):
            self.update_lbl.setText(
                f'<a href="{url_or_err}" style="color:#c99483">'
                f"{tag} disponible — télécharger</a>")
        else:
            self.update_lbl.setText(f"à jour ({VERSION})")
