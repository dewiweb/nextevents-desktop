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
        self.interval = QSpinBox(minimum=0, maximum=720,
                                 suffix=" min (0 = off)")
        self.interval.setSingleStep(5)
        self.interval.setFixedWidth(160)
        self.interval.setToolTip(
            "Régénère les diapos automatiquement toutes les N minutes.\n"
            "0 = pas de rafraîchissement automatique (génération "
            "manuelle ou heures fixes).")
        self.sched_times = QLineEdit()
        self.sched_times.setPlaceholderText("ex. 06:00, 18:30")
        self.sched_times.setFixedWidth(190)
        self.sched_times.setToolTip(
            "Heures fixes de génération au format HH:MM, séparées par "
            "des virgules — cumulables avec l'intervalle. Les diapos "
            "sont aussi à jour dès l'ouverture du poste si « Lancer "
            "l'application à l'ouverture de session » est coché.")
        # limitation des diapos : nombre, horizon en jours, ou date
        self.limit_mode = QComboBox()
        self.limit_mode.setFixedWidth(190)
        self.limit_mode.setToolTip(
            "Quelles diapos produire : les N premiers événements à "
            "venir, tout ce qui a lieu dans les N prochains jours, "
            "ou tout jusqu'à une date. Un événement en cours "
            "(expo permanente…) reste affiché.")
        self.limit_mode.addItem("Premiers N événements", "count")
        self.limit_mode.addItem("Dans les N jours", "days")
        self.limit_mode.addItem("Jusqu'au …", "date")
        self._limit_stack = QStackedWidget()
        self.maxev = QSpinBox(minimum=0, maximum=999,
                              suffix=" (0 = tous)")
        self.maxev.setFixedWidth(160)
        self.maxev.setToolTip(
            "Nombre maximum de diapos générées (0 = tous les "
            "événements).")
        self.limit_days = QSpinBox(minimum=1, maximum=365, value=14,
                                   suffix=" jours")
        self.limit_days.setFixedWidth(160)
        self.limit_days.setToolTip(
            "Inclut les événements dont la fenêtre touche les N "
            "prochains jours.")
        self.limit_date = QDateEdit(calendarPopup=True)
        self.limit_date.setToolTip(
            "Inclut les événements jusqu'à cette date (incluse).")
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
        self.res.setToolTip(
            "Taille des PNG générés. UHD pour les écrans 4K ; HD "
            "suffit pour la plupart des diffusions et des impressions "
            "courantes.")
        self.res.addItem("UHD 3840×2160", "uhd")
        self.res.addItem("HD 1920×1080", "hd")
        self.gen_ls = QCheckBox("Paysage — dans le dossier de sortie")
        self.gen_ls.setToolTip(
            "Produit les diapos 16:9 dans landscape/ — TV, diaporama "
            "paysage, écrans de la médiathèque.")
        self.gen_pt = QCheckBox("Portrait — sous-dossier portrait/")
        self.gen_pt.setToolTip(
            "Produit les diapos dans portrait/ — impression A4 ou "
            "écran pivoté 9:16 selon le format choisi.")
        self.portrait_fmt = QComboBox()
        self.portrait_fmt.setToolTip(
            "A4 : pour l'impression (marges et densité adaptées).\n"
            "Écran 9:16 : écran 16:9 monté en vertical (totem, "
            "borne).")
        self.portrait_fmt.addItem("A4 — impression", "a4")
        self.portrait_fmt.addItem("Écran 9:16 — diffusion", "screen")
        self.portrait_fmt.setEnabled(False)
        self.gen_pt.toggled.connect(self.portrait_fmt.setEnabled)
        prow = QHBoxLayout()
        prow.addWidget(self.gen_pt)
        prow.addWidget(self.portrait_fmt)
        prow.addStretch(1)
        f.addRow("Rafraîchissement auto", self.interval)
        f.addRow("… et/ou à heures fixes", self.sched_times)
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
            cb.setToolTip(
                "Inclure cette catégorie d'événements dans la "
                "génération — décocher pour l'exclure.")
            self._cat_boxes[slug] = cb
            grid.addWidget(cb, i // 2, i % 2)
        f.addRow(grid)
        lay.addWidget(catsbox)

        sp = QGroupBox("Informations affichées (specs)")
        f = QFormLayout(sp)
        f.setLabelAlignment(Qt.AlignRight)
        # une ligne par spec : case « afficher » + champ de valeur
        # forcée (vide = valeur de la source). Date : toujours
        # affichée, elle sert au nommage des fichiers.
        self._spec_rows = {}
        for key in ("Durée", "Lieu", "Tarif", "Public",
                    "Accessibilité"):
            cb = QCheckBox(key)
            cb.setChecked(True)
            cb.setToolTip(
                f"Afficher « {key} » sur les diapos — décocher pour "
                "masquer cette information partout.")
            ov = QLineEdit(placeholderText="valeur forcée (optionnel)")
            ov.setToolTip(
                f"Force la valeur affichée pour « {key} » sur toutes "
                "les diapos (ex. Lieu = Auditorium). Vide = valeur "
                "de la source.")
            ov.setMinimumWidth(220)
            row = QHBoxLayout()
            row.addWidget(cb)
            row.addWidget(ov, 1)
            f.addRow(row)
            self._spec_rows[key] = (cb, ov)
        self.spec_drops = QLineEdit()
        self.spec_drops.setPlaceholderText(
            "Dispositifs d'écoute amplifiée, …")
        self.spec_drops.setToolTip(
            "Valeurs à retirer des specs, séparées par des virgules — "
            "un item est enlevé d'une liste « a · b · c » sans perdre "
            "le reste ; si tous les items d'une spec sont masqués, "
            "la spec est omise")
        f.addRow("Valeurs masquées", self.spec_drops)
        self.next_label = QLineEdit()
        self.next_label.setToolTip(
            "Préfixe de la spec Date pour les événements à plusieurs "
            "séances — vide = afficher la date seule")
        f.addRow("Préfixe récurrent", self.next_label)
        lay.addWidget(sp)

        sers = QGroupBox("Séries éditoriales — identifiant = Libellé "
                         "[| logo.png] par ligne (slug de page du site "
                         "ou mot-clé OpenAgenda)")
        f = QFormLayout(sers)
        self.series_map = QPlainTextEdit()
        self.series_map.setMaximumHeight(72)
        self.series_map.setPlaceholderText(
            "grandstemoins = Les grands témoins | logo-gt.png")
        self.series_map.setToolTip(
            "Une ligne par série éditoriale :\n"
            "« identifiant = Libellé affiché »\n"
            "« identifiant = Libellé | logo.png » pour ajouter le "
            "logo de la série.\n"
            "L'identifiant est le slug de la page série du site ou "
            "un mot-clé OpenAgenda — le bouton « Détecter » propose "
            "les candidats trouvés dans les sources.")
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
        self.data_source.setToolTip(
            "« Site web » lit les événements sur leschampslibres.fr "
            "(couleur éditoriale de la carte incluse).\n"
            "« OpenAgenda » interroge l'API avec la clé ci-dessous — "
            "si elle est injoignable, la génération replie "
            "automatiquement sur le site.")
        self.data_source.addItem("Site web (scraping)", "site")
        self.data_source.addItem("OpenAgenda", "openagenda")
        f.addRow("Source", self.data_source)
        self.oa_agenda = QLineEdit(placeholderText="leschampslibres")
        self.oa_agenda.setToolTip(
            "Identifiant de l'agenda OpenAgenda (le slug visible dans "
            "l'URL openagenda.com/agendas/…).")
        self.oa_key = _pw("(non défini)")
        self.oa_key.setToolTip(
            "Clé API OpenAgenda (gratuite, compte sur openagenda.com)."
            "\nInutile si la source est « Site web ». Stockée dans "
            "le trousseau du système quand il existe.")
        f.addRow("Agenda", self.oa_agenda)
        f.addRow("Clé API", self.oa_key)
        row = QHBoxLayout()
        t = QPushButton("Tester la clé")
        t.setProperty("ghost", True)
        t.setToolTip(
            "Interroge l'API OpenAgenda avec l'agenda et la clé "
            "saisis — vérifie qu'ils répondent avant de générer.")
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
        self.autostart_ss.setToolTip(
            "Ouvre automatiquement le diaporama au lancement de "
            "l'app — à combiner avec « Lancer l'application à "
            "l'ouverture de session » sur un poste d'affichage.")
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

    def _check_update(self, quiet=False):
        """Interroge l'API GitHub releases en worker — résultat livré
        par le signal update_done dans le thread GUI. `quiet` (check
        automatique au démarrage) : « recherche… » et « à jour » ne
        polluent pas le libellé — seule une nouveauté s'affiche."""
        self._upd_quiet = quiet
        if not quiet:
            self.update_lbl.setText("recherche…")

        def work():
            try:
                from nextevents.net import get
                # releases/latest ignore les préreleases — or les betas
                # sont marquées prerelease. On prend donc la liste, et
                # pick_newer en extrait la plus récente admissible
                # (l'API ne trie pas par version)
                from nextevents.version import pick_newer
                d = get("https://api.github.com/repos/dewiweb/"
                        "nextevents-desktop/releases?per_page=20").json()
                tag, url = pick_newer(d)
                self.update_done.emit(tag, url)
            except Exception as e:
                self.update_done.emit("", str(e))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_done(self, tag, url_or_err):
        quiet = getattr(self, "_upd_quiet", False)
        if not tag:
            if not quiet:
                self.update_lbl.setText(f"échec : {url_or_err}")
            return
        from nextevents.version import VERSION, newer_than_current
        if newer_than_current(tag):
            self.update_lbl.setText(
                f'<a href="{url_or_err}" style="color:#c99483">'
                f"{tag} disponible — télécharger</a>")
            if quiet:
                self.statusBar().showMessage(
                    f"Nouvelle version {tag} disponible — "
                    "voir l'onglet Général", 8000)
        elif not quiet:
            self.update_lbl.setText(f"à jour ({VERSION})")
