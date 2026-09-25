"""Player de diaporama plein écran — remplace assets/slideshow.html.

Affiche les PNG générés (paysage : out_dir/*.png ; portrait :
out_dir/portrait/*.png), fondu/glissement/instantané, intervalle et
durée depuis les réglages ss_*. La liste des diapos et les réglages
sont re-lus en continu (toutes les 15 s) — une régénération se reflète
seule, comme le player web.

Contrôles : clic ou Espace = pause/reprise (badge ⏸ bas-droite,
visible à la pause et au moindre mouvement de souris ~2 s), flèches
←/→ = navigation, F11 = plein écran, Échap = quitter.
"""

import threading

from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup,
                            QPoint, QPropertyAnimation, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QLabel,
                               QMainWindow, QWidget)

from nextevents.settings import load_settings, resolve_out_dir


class _Slide(QWidget):
    """Diapo : PNG centré et mis à l'échelle (fit) sur fond noir.
    Enfant direct de la fenêtre — géométrie manuelle pour permettre
    l'animation de position (un layout la réécrirait)."""

    def __init__(self, parent):
        super().__init__(parent)
        self._pix = QPixmap()
        self._scaled = None  # cache : éviter de re-lisser à chaque frame

    def set_slide(self, path, img=None):
        # img : QImage pré-décodée en worker — évite de décoder un PNG
        # UHD (~100-200 ms) sur le thread GUI au moment de la transition
        self._pix = (QPixmap.fromImage(img)
                     if img is not None and not img.isNull()
                     else QPixmap(str(path)))
        self._scaled = None
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._scaled = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        if self._pix.isNull():
            return
        if self._scaled is None:
            self._scaled = self._pix.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawPixmap((self.width() - self._scaled.width()) // 2,
                     (self.height() - self._scaled.height()) // 2,
                     self._scaled)


class SlideshowWindow(QMainWindow):
    img_ready = Signal(str, object)  # chemin, QImage décodée en worker

    def __init__(self, portrait=False):
        super().__init__()
        self.portrait = portrait
        self.setWindowTitle("Nextevents — slideshow"
                            + (" portrait" if portrait else ""))
        self.setStyleSheet("background:#000")
        self.setCursor(Qt.BlankCursor)
        self.setMouseTracking(True)

        self._names, self._paths, self._idx = [], [], -1
        self._fp = []
        self._paused = False
        self._anim = None
        # pré-décodage de la diapo suivante (QImage borné à 2 entrées)
        self._img_cache = {}
        self._img_busy = set()
        self.img_ready.connect(self._on_img_ready)

        self._cur = _Slide(self)
        self._next = _Slide(self)
        self._cur.raise_()

        # état vide : aucune diapo générée
        from PySide6.QtWidgets import QLabel as _L
        self._empty = _L("Aucune diapo — en attente d'une génération",
                         self)
        self._empty.setStyleSheet(
            "color:#8f8c8a;font-size:28px;background:transparent")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.hide()

        # badge pause façon lecteur vidéo
        self._badge = QLabel("⏸", self)
        self._badge.setStyleSheet(
            "color:rgba(239,234,230,.5);font-size:18px;"
            "background:rgba(0,0,0,.35);padding:6px 12px;"
            "border-radius:14px")
        self._badge.adjustSize()
        self._badge.hide()
        self._badge_timer = QTimer(self, singleShot=True, interval=1800,
                                   timeout=self._badge.hide)

        self._timer = QTimer(self, singleShot=True,
                             timeout=self._advance)
        self._reloader = QTimer(self, interval=15000,
                                timeout=self._reload)
        self._reloader.start()
        self.showFullScreen()
        # différé : le premier _show doit voir la géométrie plein écran
        # (sinon la transition "glissement" part d'une largeur fausse)
        QTimer.singleShot(0, self._reload)

    # ——— liste et réglages ———

    def _dir(self):
        d = resolve_out_dir()
        return d / ("portrait" if self.portrait else "landscape")

    def _files(self):
        d = self._dir()
        return sorted(d.glob("*.png")) if d.exists() else []

    def _reload(self):
        s = load_settings()
        sfx = "_p" if self.portrait else ""
        self._delay = s.get(f"ss_delay{sfx}") or 8
        self._trans = s.get(f"ss_transition{sfx}") or "fade"
        self._tdur = s.get(f"ss_tdur{sfx}") or 1500
        files = self._files()
        names = [p.name for p in files]
        # nom + mtime : une régénération réécrivant le même fichier
        # doit quand même rafraîchir l'image affichée
        fp = [(p.name, p.stat().st_mtime_ns) for p in files]
        self._empty.setVisible(not names)
        self._empty.raise_()
        if fp == self._fp:
            return
        self._img_cache.clear()  # liste ou contenus changés
        cur = self._names[self._idx] if 0 <= self._idx < len(
            self._names) else None
        same_names = names == self._names
        self._fp = fp
        self._names, self._paths = names, files
        # diapo courante supprimée → repartir proprement, sinon
        # retrouver son nouvel index
        self._idx = (self._names.index(cur) if cur in self._names
                     else -1)
        if self._idx < 0 and self._names:
            self._show(0)
            self._arm()
        elif same_names and 0 <= self._idx < len(self._paths):
            p = self._paths[self._idx]
            self._cur.set_slide(p, self._img_cache.pop(str(p), None))

    def _arm(self):
        self._timer.stop()
        if not self._paused:
            self._timer.start(max(2, self._delay) * 1000)

    # ——— transitions ———

    def _show(self, i):
        if not self._names:
            return
        self._idx = i % len(self._names)
        path = self._paths[self._idx]
        dur, trans = self._tdur, self._trans
        if self._anim:
            self._anim.stop()
            self._swap()
        incoming, outgoing = self._next, self._cur
        incoming.set_slide(path, self._img_cache.pop(str(path), None))
        self._prefetch_next()
        if trans == "none" or dur <= 0:
            incoming.move(0, 0)
            incoming.raise_()
            self._cur, self._next = incoming, outgoing
            return
        if trans == "slide":
            w = self.width()
            incoming.raise_()
            incoming.move(w, 0)
            anim_in = QPropertyAnimation(incoming, b"pos")
            anim_in.setDuration(dur)
            anim_in.setStartValue(QPoint(w, 0))
            anim_in.setEndValue(QPoint(0, 0))
            anim_out = QPropertyAnimation(outgoing, b"pos")
            anim_out.setDuration(dur)
            anim_out.setStartValue(QPoint(0, 0))
            anim_out.setEndValue(QPoint(-w, 0))
            self._anim = QParallelAnimationGroup(self)
            self._anim.addAnimation(anim_in)
            self._anim.addAnimation(anim_out)
        else:  # fade
            incoming.raise_()
            eff = QGraphicsOpacityEffect(incoming)
            incoming.setGraphicsEffect(eff)
            self._anim = QPropertyAnimation(eff, b"opacity", self)
            self._anim.setDuration(dur)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
        for a in ([self._anim] if not isinstance(
                self._anim, QParallelAnimationGroup)
                else [self._anim.animationAt(0),
                      self._anim.animationAt(1)]):
            a.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim.finished.connect(self._swap)
        self._anim.start()

    def _swap(self):
        if self._anim:
            self._anim.deleteLater()
            self._anim = None
        self._cur, self._next = self._next, self._cur
        self._cur.setGraphicsEffect(None)
        self._cur.move(0, 0)
        self._cur.raise_()

    def _prefetch_next(self):
        """Décode la diapo suivante dans un worker — le changement de
        diapo ne paye alors que la conversion QPixmap, pas la lecture
        PNG UHD."""
        if len(self._paths) < 2:
            return
        p = str(self._paths[(self._idx + 1) % len(self._paths)])
        if p in self._img_cache or p in self._img_busy:
            return
        self._img_busy.add(p)

        def work():
            self.img_ready.emit(p, QImage(p))

        threading.Thread(target=work, daemon=True).start()

    def _on_img_ready(self, path, img):
        self._img_busy.discard(path)
        if img.isNull():
            return
        self._img_cache = {path: img}  # une seule suivante suffit

    def _advance(self):
        if self._names:
            self._show(self._idx + 1)
        self._arm()

    # ——— interactions ———

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._timer.stop()
            self._show_badge()
        else:
            self._badge_timer.stop()
            self._badge.hide()
            self._arm()

    def _show_badge(self):
        if not self._paused:
            return
        self._badge.move(self.width() - self._badge.width() - 18,
                         self.height() - self._badge.height() - 14)
        self._badge.raise_()
        self._badge.show()
        self._badge_timer.start()

    def mousePressEvent(self, e):
        self._toggle_pause()

    def mouseMoveEvent(self, e):
        self._show_badge()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Space:
            self._toggle_pause()
        elif k in (Qt.Key_Right, Qt.Key_Down):
            self._advance()
        elif k in (Qt.Key_Left, Qt.Key_Up) and self._names:
            self._show(self._idx - 1)
            self._arm()
        elif k == Qt.Key_F11:
            self.showNormal() if self.isFullScreen() \
                else self.showFullScreen()
        elif k == Qt.Key_Escape:
            self.close()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        for w in (self._cur, self._next, self._empty):
            w.resize(self.size())
        self._badge.move(self.width() - self._badge.width() - 18,
                         self.height() - self._badge.height() - 14)
