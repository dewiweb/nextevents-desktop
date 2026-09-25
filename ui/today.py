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
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from nextevents.settings import load_settings, resolve_out_dir
from nextevents.scrape import series_brand
from nextevents.slide import SIZES, DEFAULT_SIZE

BG_CHOICES = [
    ("#141414", "Encre"), ("#302f2e", "Anthracite"),
    ("#363129", "Jaune nuit"), ("#2b2e2c", "Vert nuit"),
    ("#312a28", "Terre nuit"), ("#313134", "Bleu nuit"),
    ("#3d1813", "Rouge nuit"), ("#16203f", "Marine (séries)"),
]

# accent = pastel de la pastille/règle/badge série ; None = couleur
# éditoriale de la carte de l'événement (site — OA n'en a pas)
ACCENT_CHOICES = [
    (None, "Auto (couleur de la carte)"),
    ("#efeae6", "Gris pâle"), ("#f6e3bb", "Jaune pâle"),
    ("#c6d2c9", "Vert pâle"), ("#e3c2b7", "Rouge pâle"),
    ("#e2dff0", "Bleu pâle"),
]


class _Thumb(QLabel):
    """Vignette cliquable — même idée que la galerie (clic = aperçu)."""
    clicked = Signal()

    def __init__(self, tooltip):
        super().__init__("—")
        self.setFixedSize(300, 170)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setStyleSheet(
            "border:1px solid #3a3836;border-radius:8px;color:#8f8c8a")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


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
        if self.value is None:
            # pastille « auto » : cercle pointillé + A
            from PySide6.QtGui import QPen
            p.setPen(QPen(QColor("#8f8c8a"), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(8, 8, 24, 24)
            p.drawText(self.rect(), Qt.AlignCenter, "A")
        else:
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
        self.accent = None  # auto = couleur éditoriale de la carte
        self.gen_done.connect(self._on_gen_done)

        # scroll si la fenêtre est trop courte (comme l'onglet Général)
        outer_wrap = QVBoxLayout(self)
        outer_wrap.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(widgetResizable=True)
        from PySide6.QtWidgets import QFrame
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer_wrap.addWidget(scroll)

        outer = QVBoxLayout(inner)
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

        row = QHBoxLayout()
        row.addWidget(QLabel("Accent"))
        self._accents = []
        for v, name in ACCENT_CHOICES:
            b = _Swatch(v, name, self._pick_accent, lambda: self.accent)
            self._accents.append(b)
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
        form.addStretch(1)

        # vignettes de la diapo générée (comme la galerie : clic =
        # aperçu, supprimable) — épinglées en bas de la colonne
        prow = QHBoxLayout()
        self.thumb = _Thumb("Diapo du jour — cliquer pour agrandir")
        self.thumb.clicked.connect(lambda: self._preview("index.png"))
        prow.addWidget(self.thumb)
        self.qr_thumb = _Thumb("Slide QR de la série — idem")
        self.qr_thumb.clicked.connect(lambda: self._preview("qr.png"))
        prow.addWidget(self.qr_thumb)
        rm = QPushButton("Supprimer")
        rm.setProperty("danger", True)
        rm.setToolTip("Supprime les fichiers générés (index + QR) "
                      "du dossier today/")
        rm.clicked.connect(self._delete_today)
        prow.addWidget(rm, alignment=Qt.AlignBottom)
        prow.addStretch(1)
        form.addLayout(prow)
        cols.addLayout(form, 3)

        right = QVBoxLayout()
        right.addWidget(QLabel(
            "Description détaillée (référence pour corriger les champs)"))
        self.desc = QPlainTextEdit(readOnly=True)
        self.desc.setPlaceholderText(
            "Sélectionnez un événement pour voir sa description.")
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
        self._refresh_thumbs()
        if not self._spk_box.count():
            self._add_speaker("", "")

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

    def _pick_accent(self, v):
        self.accent = v
        for b in self._accents:
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
        smap = (load_settings() or {}).get("series_map", "")
        label, _ = series_brand(smap, e.get("series") or "")
        series = label or e.get("series") or ""
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
        smap = (load_settings() or {}).get("series_map", "")
        label, logo = series_brand(smap, e.get("series") or "")
        series = label or e.get("series") or ""
        # série : le bleu pâle de la palette reprend le rond bleu du
        # modèle com (accent auto = couleur de carte sinon)
        accent = self.accent or ("#e2dff0" if series else None)
        return {
            "title": self.title.text().strip(),
            "tag": e.get("tag") or "",
            "color": e.get("color") or None,
            "accent": accent,
            "bg": self.bg,
            "speakers": self._speakers(),
            "moderator": self.moderator.text().strip(),
            "note": self.note.toPlainText().strip(),
            "access": self.access.toPlainText().strip(),
            "series": series,
            "series_logo": logo,
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
        self._refresh_thumbs()

    def _refresh_thumbs(self):
        """Recharge les vignettes today/ (index + QR) ou le tiret si
        rien n'est généré — appelé après génération et suppression."""
        d = resolve_out_dir() / "today"
        for w, name in ((self.thumb, "index.png"),
                        (self.qr_thumb, "qr.png")):
            p = d / name
            pix = QPixmap(str(p)) if p.exists() else QPixmap()
            w.setPixmap(pix.scaled(w.width() - 4, w.height() - 4,
                                   Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
                        if not pix.isNull() else QPixmap())
            w.setText("" if not pix.isNull() else "—")

    def _delete_today(self):
        """Supprime les fichiers générés de today/ (HTML + PNG, index et
        QR) — les destinations déjà poussées ne sont pas touchées."""
        d = resolve_out_dir() / "today"
        files = [d / f for f in ("index.html", "index.png",
                                 "qr.html", "qr.png") if (d / f).exists()]
        if not files:
            self.gen_lbl.setText("rien à supprimer")
            return
        r = QMessageBox.question(
            self, "Supprimer la diapo du jour",
            f"Supprimer {len(files)} fichier(s) généré(s) ?")
        if r != QMessageBox.Yes:
            return
        for f in files:
            f.unlink(missing_ok=True)
        self._refresh_thumbs()
        self.gen_lbl.setText("diapo du jour supprimée")

    def _preview(self, name="index.png"):
        p = resolve_out_dir() / "today" / name
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
