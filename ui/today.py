"""Diapo du jour (auditorium) — éditeur + génération.

Reprend la section correspondante de la webui : choix d'un événement
issu de events.json (écrit à la génération), préremplissage titre /
intervenants / animateur / notes / accessibilité, palette de fonds,
génération du HTML+PNG et envoi vers les partages configurés.
"""

import json
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from nextevents.settings import load_settings, resolve_out_dir
from nextevents.slide import SIZES, DEFAULT_SIZE

BG_CHOICES = [
    ("#141414", "Encre"), ("#302f2e", "Anthracite"),
    ("#363129", "Jaune nuit"), ("#2b2e2c", "Vert nuit"),
    ("#312a28", "Terre nuit"), ("#313134", "Bleu nuit"),
    ("#3d1813", "Rouge nuit"), ("#16203f", "Marine (séries)"),
]


class _Swatch(QPushButton):
    """Pastille ronde de choix de fond (palette BG_CHOICES)."""

    def __init__(self, value, name, pick, current):
        super().__init__()
        self.value = value
        self._current = current
        self.setToolTip(name)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(lambda: pick(value))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._current() == self.value:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#f6e3bb"))
            p.drawEllipse(1, 1, 38, 38)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.value))
        p.drawEllipse(6, 6, 28, 28)


class TodayTab(QWidget):
    gen_done = Signal(str)

    def __init__(self, main):
        super().__init__()
        self._main = main
        self._events = []
        self._busy = False
        self.bg = BG_CHOICES[0][0]
        self.gen_done.connect(self._on_gen_done)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)

        row = QHBoxLayout()
        row.addWidget(QLabel("Événement"))
        self.ev = QComboBox()
        self.ev.setMinimumWidth(420)
        self.ev.currentIndexChanged.connect(self._prefill)
        row.addWidget(self.ev, 1)
        self.series_lbl = QLabel("")
        self.series_lbl.setStyleSheet("color:#a8bce0")
        row.addWidget(self.series_lbl)
        outer.addLayout(row)

        cols = QHBoxLayout()
        form = QVBoxLayout()
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignRight)
        self.title = QLineEdit()
        f.addRow("Titre", self.title)
        form.addLayout(f)

        self._spk_box = QVBoxLayout()
        form.addLayout(self._spk_box)
        row = QHBoxLayout()
        add = QPushButton("+ intervenant")
        add.setProperty("ghost", True)
        add.clicked.connect(lambda: self._add_speaker("", ""))
        row.addWidget(add)
        row.addWidget(QLabel("Animé par"))
        self.moderator = QLineEdit()
        self.moderator.setFixedWidth(230)
        row.addWidget(self.moderator)
        row.addStretch(1)
        form.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Fond"))
        self._swatches = []
        for v, name in BG_CHOICES:
            b = _Swatch(v, name, self._pick_bg, lambda: self.bg)
            self._swatches.append(b)
            row.addWidget(b)
        row.addStretch(1)
        form.addLayout(row)

        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignRight)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText(
            "En partenariat avec …\n"
            "Rencontre suivie d'une séance de dédicace")
        self.note.setFixedHeight(60)
        f.addRow("Notes — pied de page\n(une ligne par mention)",
                 self.note)
        self.access = QPlainTextEdit()
        self.access.setPlaceholderText("Interprétation en LSF")
        self.access.setFixedHeight(60)
        f.addRow("Accessibilité\n(une ligne par mention)", self.access)
        form.addLayout(f)
        self.access_hint = QLabel("")
        self.access_hint.setWordWrap(True)
        form.addWidget(self.access_hint)
        cols.addLayout(form, 3)

        right = QVBoxLayout()
        right.addWidget(QLabel(
            "Description détaillée (référence pour corriger les champs)"))
        self.desc = QPlainTextEdit(readOnly=True)
        self.desc.setStyleSheet("font-size:12.5px;color:#bfbbb8")
        right.addWidget(self.desc, 1)
        cols.addLayout(right, 2)
        outer.addLayout(cols, 1)

        row = QHBoxLayout()
        g = QPushButton("Générer la diapo du jour")
        g.setProperty("accent", True)
        self._gen_btn = g
        g.clicked.connect(self._generate)
        row.addWidget(g)
        pv = QPushButton("Aperçu")
        pv.setProperty("ghost", True)
        pv.clicked.connect(self._preview)
        row.addWidget(pv)
        self.gen_lbl = QLabel("")
        row.addWidget(self.gen_lbl)
        row.addStretch(1)
        outer.addLayout(row)

        self.load_events()

    # ——— données ———

    def load_events(self):
        p = resolve_out_dir() / "events.json"
        try:
            self._events = json.loads(p.read_text("utf-8"))
        except Exception:
            self._events = []
        cur = self.ev.currentData()
        self.ev.blockSignals(True)
        self.ev.clear()
        self.ev.addItem("— choisir un événement —", -1)
        for i, e in enumerate(self._events):
            d = e.get("specs", {}).get("Date", "")
            self.ev.addItem(
                f"{d} · {e.get('tag') or ''} · "
                f"{e.get('title') or '(sans titre)'}", i)
        if cur is not None and cur >= 0:
            self.ev.setCurrentIndex(
                self.ev.findData(cur))
        self.ev.blockSignals(False)
        self._prefill()

    def _pick_bg(self, v):
        self.bg = v
        for b in self._swatches:
            b.update()

    def _add_speaker(self, name, qual):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        n = QLineEdit(name, placeholderText="Nom Prénom")
        n.setFixedWidth(230)
        q = QLineEdit(qual,
                      placeholderText="Qualité (fonction, affiliation…)")
        x = QPushButton("×")
        x.setProperty("ghost", True)
        x.setFixedWidth(32)
        x.clicked.connect(
            lambda: (self._spk_box.removeWidget(row),
                     row.deleteLater()))
        h.addWidget(n)
        h.addWidget(q, 1)
        h.addWidget(x)
        self._spk_box.addWidget(row)

    def _speakers(self):
        out = []
        for i in range(self._spk_box.count()):
            row = self._spk_box.itemAt(i).widget()
            if not row:
                continue
            fields = row.findChildren(QLineEdit)
            if fields and fields[0].text().strip():
                out.append({"name": fields[0].text().strip(),
                            "quality": fields[1].text().strip()})
        return out

    def _prefill(self):
        i = self.ev.currentData()
        if i is None or i < 0 or i >= len(self._events):
            return
        e = self._events[i]
        series = e.get("series") or ""
        self.series_lbl.setText(
            f"Série : {series} — modèle com appliqué" if series else "")
        if series:
            self._pick_bg("#16203f")
        self.title.setText(e.get("title") or "")
        self.moderator.setText(e.get("moderator") or "")
        self.note.setPlainText(e.get("note") or "")
        self.access.setPlainText(e.get("access") or "")
        av = e.get("access_venue") or []
        self.access_hint.setText(
            "Sur place : " + " · ".join(av) if av else "")
        while self._spk_box.count():
            w = self._spk_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        for s in e.get("speakers") or []:
            self._add_speaker(s.get("name", ""), s.get("quality", ""))
        if not self._spk_box.count():
            self._add_speaker("", "")
        self.desc.setPlainText(e.get("desc_long") or e.get("desc") or "—")

    # ——— génération ———

    def _data(self):
        i = self.ev.currentData()
        e = self._events[i] if i is not None and 0 <= i < len(
            self._events) else {}
        return {
            "title": self.title.text().strip(),
            "tag": e.get("tag") or "",
            "color": e.get("color") or None,
            "bg": self.bg,
            "speakers": self._speakers(),
            "moderator": self.moderator.text().strip(),
            "note": self.note.toPlainText().strip(),
            "access": self.access.toPlainText().strip(),
            "series": e.get("series") or "",
        }

    def _generate(self):
        data = self._data()
        if not data["title"]:
            self.gen_lbl.setText("titre vide")
            return
        self.gen_lbl.setText("génération…")
        self._gen_btn.setEnabled(False)
        self._busy = True
        # même barre de progression globale que la génération principale
        self._main.progress.show()

        def work():
            from nextevents.today import (push_today, render_today_png,
                                          write_today)
            cfg = load_settings()
            out = resolve_out_dir(cfg)
            errors = []
            try:
                write_today(data, out)
                render_today_png(
                    SIZES.get(cfg.get("resolution"), DEFAULT_SIZE), out)
            except Exception as e:
                errors.append(str(e))
            errors += push_today(cfg, out)
            msg = ("générée ✓ envoyée sur le partage" if not errors
                   else "générée — " + " ; ".join(errors))
            # Signal → livré dans le thread GUI (queued connection)
            self.gen_done.emit(msg)

        threading.Thread(target=work, daemon=True).start()

    def _on_gen_done(self, msg):
        self._busy = False
        self.gen_lbl.setText(msg)
        self._gen_btn.setEnabled(True)
        self._main.progress.hide()
        self._main.statusBar().showMessage(
            "Diapo du jour : " + msg, 6000)

    def _preview(self):
        p = resolve_out_dir() / "today" / "index.png"
        if not p.exists():
            self.gen_lbl.setText("pas encore générée")
            return
        from PySide6.QtWidgets import QDialog
        d = QDialog(self)
        d.setAttribute(Qt.WA_DeleteOnClose)
        d.setWindowTitle("Diapo du jour — aperçu")
        v = QVBoxLayout(d)
        lbl = QLabel()
        pix = QPixmap(str(p))
        lbl.setPixmap(pix.scaled(1100, 620, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation))
        v.addWidget(lbl)
        d.exec()
