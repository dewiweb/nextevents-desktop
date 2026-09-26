"""Onglet « Destinations » (FTP / SMB / dossier local) — mixin de
MainWindow (aucun __init__ propre : les méthodes sont appelées sur la
fenêtre, qui fournit les signaux, _save et les widgets partagés).
Contient aussi les helpers réseau : test de connexion et sélecteur
de dossier."""

import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from nextevents.settings import OUT_DIR, load_settings
from .style import _pw


class DestinationsTabMixin:

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

    def _browse(self, field):
        d = QFileDialog.getExistingDirectory(
            self, "Choisir un dossier", field.text() or str(OUT_DIR))
        if d:
            field.setText(d)
