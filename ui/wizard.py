"""Assistant de premier lancement.

Présenté par ui.app quand settings.json n'existe pas encore. Traduit
des usages déclarés — diffusion sur un écran du poste, impression,
copie miroir, envoi FTP/SMB — en réglages concrets : il écrit les
mêmes clés que les onglets, rien n'est propre à l'assistant. Tout
reste modifiable ensuite dans l'onglet correspondant.

Annuler : « me la reproposer » n'écrit rien (settings.json reste
absent → relancé au prochain démarrage) ; « ne plus proposer » pose
self.persist_defaults — app.py écrit alors les défauts.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWizard, QWizardPage,
)

from nextevents.settings import (
    OUT_DIR, load_settings, save_settings,
)
from .style import _pw

INTRO, SCREEN, OUTPUT, DEST, FINAL = range(5)


class _Page(QWizardPage):
    """WizardPage avec garde « déjà vue » : les préréglages dans
    initializePage() ne doivent pas écraser les choix de
    l'utilisateur quand il revient en arrière puis repasse."""

    def __init__(self, wizard, title, subtitle=""):
        super().__init__(wizard)
        self.w = wizard
        self._seen = False
        self.setTitle(title)
        if subtitle:
            self.setSubTitle(subtitle)
        self.lay = QVBoxLayout(self)

    def initializePage(self):
        if self._seen:
            return
        self._seen = True
        self.preset()

    def preset(self):
        pass


def _note(text):
    w = QLabel(text)
    w.setWordWrap(True)
    return w


class SetupWizard(QWizard):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nextevents — premier lancement")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoBackButtonOnStartPage)
        self.setButtonText(QWizard.NextButton, "Suivant")
        self.setButtonText(QWizard.BackButton, "Précédent")
        self.setButtonText(QWizard.FinishButton, "Terminer")
        self.setButtonText(QWizard.CancelButton, "Passer")
        self.persist_defaults = False   # « ne plus proposer »
        self.generate_now = False

        self.setPage(INTRO, _IntroPage(self))
        self.setPage(SCREEN, _ScreenPage(self))
        self.setPage(OUTPUT, _OutputPage(self))
        self.setPage(DEST, _DestPage(self))
        self.setPage(FINAL, _FinalPage(self))
        self.setStartId(INTRO)
        self.resize(640, 560)

    def nextId(self):
        # la page Écran n'a de sens que si la diffusion est cochée
        if self.currentId() == INTRO:
            return SCREEN if self.use_screen.isChecked() else OUTPUT
        return self.currentId() + 1 if self.currentId() < FINAL else -1

    def reject(self):
        box = QMessageBox(self)
        box.setWindowTitle("Passer la configuration assistée")
        box.setText("Tout reste configurable dans les onglets.")
        back = box.addButton("Revenir à l'assistant",
                             QMessageBox.RejectRole)
        box.addButton("Me la reproposer plus tard",
                      QMessageBox.AcceptRole)
        never = box.addButton("Ne plus proposer",
                              QMessageBox.DestructiveRole)
        box.exec()
        if box.clickedButton() is back:
            return
        self.persist_defaults = box.clickedButton() is never
        super().reject()

    def accept(self):
        s = load_settings()  # DEFAULTS — pas de fichier au 1er lancement
        s["gen_landscape"] = int(self.gen_ls.isChecked())
        s["gen_portrait"] = int(self.gen_pt.isChecked())
        s["portrait_format"] = self.portrait_fmt.currentData()
        s["resolution"] = self.res.currentData()
        d = self.out_dir.text().strip()
        if d:
            s["out_dir"] = d
        if self.use_screen.isChecked():
            port = self.screen_orient.currentData() == "portrait"
            s[f"ss_screen{'_p' if port else ''}"] = \
                self.screen_idx.currentData()
            s["autostart_app"] = int(self.auto_app.isChecked())
            s["autostart_slideshow"] = (
                ("portrait" if port else "landscape")
                if self.auto_show.isChecked() else "none")
        if self.use_mirror.isChecked():
            m = self.local_dir.text().strip()
            if m:
                # le miroir reçoit tout ce qui est généré
                s["local_dir"] = m
                s["local_send_landscape"] = 1
                s["local_send_portrait"] = 1
        if self.use_server.isChecked():
            for k, wdg in (
                    ("ftp_host", self.ftp_host),
                    ("ftp_path", self.ftp_path),
                    ("ftp_user", self.ftp_user),
                    ("ftp_pass", self.ftp_pass),
                    ("smb_host", self.smb_host),
                    ("smb_share", self.smb_share),
                    ("smb_path", self.smb_path),
                    ("smb_user", self.smb_user),
                    ("smb_pass", self.smb_pass)):
                v = wdg.text().strip()
                if v:
                    s[k] = v
            s["ftp_tls"] = int(self.ftp_tls.isChecked())
        save_settings(s)
        self.generate_now = self.gen_now.isChecked()
        super().accept()


class _IntroPage(_Page):

    def __init__(self, w):
        super().__init__(
            w, "Bienvenue",
            "Nextevents génère des diaporamas des événements des "
            "Champs Libres. Répondez à quelques questions pour "
            "préparer la première génération.")
        self.lay.addWidget(
            _note("À quoi va servir Nextevents sur ce poste ? "
                  "Plusieurs réponses possibles."))
        w.use_screen = QCheckBox(
            "Diffuser sur un écran raccordé à ce poste "
            "(TV, écran pivoté…)")
        w.use_print = QCheckBox("Imprimer des visuels A4")
        w.use_mirror = QCheckBox(
            "Copier les diapos vers un autre dossier "
            "(partage, clé USB, dossier des partenaires…)")
        w.use_server = QCheckBox(
            "Envoyer les diapos vers un serveur FTP ou SMB")
        for cb in (w.use_screen, w.use_print, w.use_mirror,
                   w.use_server):
            self.lay.addWidget(cb)
        self.lay.addStretch(1)
        self.lay.addWidget(
            _note("Aucune case cochée : génération paysage simple "
                  "dans le dossier intégré de l'application — un bon "
                  "point de départ pour essayer."))


class _ScreenPage(_Page):

    def __init__(self, w):
        super().__init__(
            w, "Diffusion sur écran",
            "Réglages du diaporama affiché par ce poste.")
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignRight)
        w.screen_orient = QComboBox()
        w.screen_orient.addItem("Paysage — TV ou écran classique",
                                "landscape")
        w.screen_orient.addItem("Portrait — écran pivoté 9:16",
                                "portrait")
        f.addRow("Orientation", w.screen_orient)
        w.screen_idx = QComboBox()
        w.screen_idx.addItem("Écran principal", -1)
        # mêmes indices que l'onglet Galerie : position dans
        # QApplication.screens()
        for i, scr in enumerate(QApplication.screens()):
            g = scr.geometry()
            w.screen_idx.addItem(
                f"Écran {i + 1} — {g.width()}×{g.height()}", i)
        f.addRow("Écran", w.screen_idx)
        self.lay.addLayout(f)
        w.auto_app = QCheckBox(
            "Lancer Nextevents à l'ouverture de session")
        w.auto_app.setToolTip(
            "Indispensable sur un poste d'affichage : un redémarrage "
            "(mise à jour, coupure) ne doit pas laisser l'écran vide.")
        w.auto_show = QCheckBox(
            "Afficher le diaporama automatiquement au lancement")
        self.lay.addWidget(w.auto_app)
        self.lay.addWidget(w.auto_show)
        self.lay.addStretch(1)

    def preset(self):
        # un poste d'affichage veut les deux : survivre aux reboots
        # et afficher sans intervention
        self.w.auto_app.setChecked(True)
        self.w.auto_show.setChecked(True)


class _OutputPage(_Page):

    def __init__(self, w):
        super().__init__(
            w, "Diapos générées",
            "Formats produits à chaque génération.")
        w.gen_ls = QCheckBox("Paysage 16:9 — écrans, dossier landscape/")
        w.gen_pt = QCheckBox("Portrait — dossier portrait/")
        w.gen_ls.toggled.connect(self.completeChanged)
        w.gen_pt.toggled.connect(self.completeChanged)
        self.lay.addWidget(w.gen_ls)
        row = QHBoxLayout()
        row.addSpacing(28)
        row.addWidget(w.gen_pt)
        w.portrait_fmt = QComboBox()
        w.portrait_fmt.addItem("A4 — impression", "a4")
        w.portrait_fmt.addItem("Écran 9:16 — diffusion", "screen")
        w.portrait_fmt.setEnabled(False)
        w.gen_pt.toggled.connect(w.portrait_fmt.setEnabled)
        row.addWidget(w.portrait_fmt)
        row.addStretch(1)
        self.lay.addLayout(row)
        f = QFormLayout()
        w.res = QComboBox()
        w.res.addItem("UHD 3840×2160", "uhd")
        w.res.addItem("HD 1920×1080", "hd")
        f.addRow("Résolution", w.res)
        self.lay.addLayout(f)
        self.lay.addStretch(1)
        self.lay.addWidget(
            _note("Écran portrait + impression : un seul format "
                  "portrait est produit — la diffusion 9:16 est "
                  "privilégiée, l'A4 se choisit dans l'onglet "
                  "Général si besoin."))

    def preset(self):
        w = self.w
        port_screen = (w.use_screen.isChecked() and
                       w.screen_orient.currentData() == "portrait")
        any_use = any(cb.isChecked() for cb in
                      (w.use_screen, w.use_print, w.use_mirror,
                       w.use_server))
        # aucun usage déclaré → paysage simple (essai) ; sinon le
        # paysage ne sert que si un écran paysage est prévu
        w.gen_ls.setChecked(
            not any_use
            or w.use_screen.isChecked() and not port_screen)
        w.gen_pt.setChecked(w.use_print.isChecked() or port_screen)
        if w.use_screen.isChecked() and port_screen:
            w.portrait_fmt.setCurrentIndex(1)
        elif w.use_print.isChecked():
            w.portrait_fmt.setCurrentIndex(0)

    def isComplete(self):
        return self.w.gen_ls.isChecked() or self.w.gen_pt.isChecked()


class _DestPage(_Page):

    def __init__(self, w):
        super().__init__(
            w, "Sortie et envoi",
            "Où les diapos sont écrites, et où elles sont poussées.")
        box = QGroupBox("Dossier de sortie")
        f = QFormLayout(box)
        w.out_dir = QLineEdit()
        w.out_dir.setPlaceholderText(
            f"(vide = dossier intégré : {OUT_DIR})")
        row = QHBoxLayout()
        row.addWidget(w.out_dir, 1)
        b = QPushButton("…")
        b.setProperty("ghost", True)
        b.setFixedWidth(36)
        b.clicked.connect(self._browse)
        row.addWidget(b)
        f.addRow("Écrire dans", row)
        self.lay.addWidget(box)

        self.mirror_box = QGroupBox("Copie miroir")
        f = QFormLayout(self.mirror_box)
        w.local_dir = QLineEdit()
        w.local_dir.setPlaceholderText(
            "D:\\diaporama ou \\\\serveur\\partage\\dossier")
        row = QHBoxLayout()
        row.addWidget(w.local_dir, 1)
        b = QPushButton("…")
        b.setProperty("ghost", True)
        b.setFixedWidth(36)
        b.clicked.connect(lambda: self._browse_to(w.local_dir))
        row.addWidget(b)
        f.addRow("Vers", row)
        self.lay.addWidget(self.mirror_box)

        self.ftp_box = QGroupBox("Serveur FTP")
        f = QFormLayout(self.ftp_box)
        w.ftp_host = QLineEdit(placeholderText="nas.local")
        w.ftp_path = QLineEdit(placeholderText="/diaporama")
        w.ftp_user = QLineEdit()
        w.ftp_pass = _pw("(optionnel)")
        w.ftp_tls = QCheckBox("FTPS")
        f.addRow("Serveur", w.ftp_host)
        f.addRow("Chemin", w.ftp_path)
        f.addRow("Utilisateur", w.ftp_user)
        f.addRow("Mot de passe", w.ftp_pass)
        f.addRow("", w.ftp_tls)
        self.lay.addWidget(self.ftp_box)

        self.smb_box = QGroupBox("Partage SMB")
        f = QFormLayout(self.smb_box)
        w.smb_host = QLineEdit(placeholderText="192.168.1.20")
        w.smb_share = QLineEdit(placeholderText="diaporama")
        w.smb_path = QLineEdit(placeholderText="(optionnel)")
        w.smb_user = QLineEdit(placeholderText="DOMAINE\\user")
        w.smb_pass = _pw("(optionnel)")
        f.addRow("Hôte", w.smb_host)
        f.addRow("Partage", w.smb_share)
        f.addRow("Sous-dossier", w.smb_path)
        f.addRow("Utilisateur", w.smb_user)
        f.addRow("Mot de passe", w.smb_pass)
        self.lay.addWidget(self.smb_box)
        self.lay.addStretch(1)

    def _browse(self):
        self._browse_to(self.w.out_dir)

    def _browse_to(self, field):
        d = QFileDialog.getExistingDirectory(
            self, "Choisir un dossier", field.text() or str(OUT_DIR))
        if d:
            field.setText(d)

    def initializePage(self):
        super().initializePage()
        w = self.w
        self.mirror_box.setVisible(w.use_mirror.isChecked())
        self.ftp_box.setVisible(w.use_server.isChecked())
        self.smb_box.setVisible(w.use_server.isChecked())


class _FinalPage(_Page):

    def __init__(self, w):
        super().__init__(w, "Prêt")
        self.summary = _note("")
        self.lay.addWidget(self.summary)
        w.gen_now = QCheckBox(
            "Générer mes premières diapos maintenant")
        w.gen_now.setChecked(True)
        self.lay.addWidget(w.gen_now)
        self.lay.addStretch(1)
        self.lay.addWidget(_note(
            "Les envois FTP/SMB peuvent être testés dans l'onglet "
            "Destinations ; le diaporama se règle dans l'onglet "
            "Galerie (intervalle, transition).\n"
            "En cas de doute ensuite : bouton « ? » en haut à droite "
            "ou touche F1 — l'aide s'ouvre sur l'onglet courant."))

    def initializePage(self):
        # pas de garde _seen : le résumé doit refléter les choix,
        # y compris après un aller-retour Précédent/Suivant
        w = self.w
        use = []
        if w.use_screen.isChecked():
            use.append("diffusion sur écran "
                       f"({w.screen_orient.currentText().split(' —')[0]})")
        if w.use_print.isChecked():
            use.append("impression A4")
        if w.use_mirror.isChecked():
            use.append("copie miroir")
        if w.use_server.isChecked():
            use.append("envoi FTP/SMB")
        fmts = []
        if w.gen_ls.isChecked():
            fmts.append("paysage")
        if w.gen_pt.isChecked():
            fmts.append("portrait "
                        f"({w.portrait_fmt.currentText().split(' —')[0]})")
        out = w.out_dir.text().strip() or f"dossier intégré ({OUT_DIR})"
        self.summary.setText(
            f"<b>Usages :</b> {', '.join(use) or 'génération simple'}<br>"
            f"<b>Formats :</b> {' + '.join(fmts)} "
            f"({w.res.currentText()})<br>"
            f"<b>Sortie :</b> {out}")
