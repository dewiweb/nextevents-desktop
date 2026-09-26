"""Onglet « Galerie » (diapos paysage/portrait, réglages de lecture,
players plein écran, régénération/suppression unitaire, export zip) —
mixin de MainWindow (aucun __init__ propre : les méthodes sont
appelées sur la fenêtre, qui fournit les signaux et l'état partagé)."""

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QDesktopServices, QKeySequence, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from nextevents.runner import slides, slides_portrait
from nextevents.settings import load_settings, resolve_out_dir, state
from .slideshow import SlideshowWindow


class GalleryTabMixin:

    def _gallery_tab(self):
        """Un sous-onglet par orientation — même organisation que le
        dossier de sortie : landscape/ et portrait/."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)

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
        lay.addLayout(row)

        self.galleries = {}
        inner = QTabWidget()
        inner.setDocumentMode(True)
        # suffixe réglages, sous-dossier, titre d'onglet, taille vignette
        for sfx, sub, label, tw, th in (
                ("", "landscape", "Paysage — landscape/", 280, 160),
                ("_p", "portrait", "Portrait — portrait/", 160, 285)):
            page = QWidget()
            pv = QVBoxLayout(page)
            pv.setContentsMargins(0, 12, 0, 0)
            pv.setSpacing(12)

            play = QGroupBox("Lecture")
            h = QHBoxLayout(play)
            delay = QSpinBox(minimum=2, maximum=3600, suffix=" s")
            delay.setFixedWidth(110)
            trans = QComboBox()
            trans.setFixedWidth(160)
            trans.addItem("Aucune", "none")
            trans.addItem("Fondu", "fade")
            trans.addItem("Glissement", "slide")
            tdur = QSpinBox(minimum=0, maximum=10000, singleStep=100,
                            suffix=" ms")
            tdur.setFixedWidth(110)
            screen = QComboBox()
            screen.setFixedWidth(200)
            screen.addItem("Écran principal", -1)
            # écran de diffusion sur les postes multi-sorties — l'index
            # stocké dans ss_screen* est celui de QApplication.screens()
            from PySide6.QtWidgets import QApplication
            for i, scr in enumerate(QApplication.screens()):
                g = scr.geometry()
                screen.addItem(
                    f"Écran {i + 1} — {g.width()}×{g.height()}", i)
            setattr(self, "ss_delay" + sfx, delay)
            setattr(self, "ss_transition" + sfx, trans)
            setattr(self, "ss_tdur" + sfx, tdur)
            setattr(self, "ss_screen" + sfx, screen)
            h.addWidget(QLabel("Intervalle"))
            h.addWidget(delay)
            h.addWidget(QLabel("Transition"))
            h.addWidget(trans)
            h.addWidget(QLabel("Durée"))
            h.addWidget(tdur)
            h.addWidget(QLabel("Affichage"))
            h.addWidget(screen)
            h.addStretch(1)
            b = QPushButton("Ouvrir le slideshow")
            b.setProperty("ghost", True)
            b.clicked.connect(lambda _=False, p=bool(sfx):
                              self._open_slideshow(p))
            h.addWidget(b)
            pv.addWidget(play)

            gal = QListWidget()
            gal.setSelectionMode(QListWidget.ExtendedSelection)
            gal.setContextMenuPolicy(Qt.CustomContextMenu)
            gal.customContextMenuRequested.connect(
                lambda pos, lst=gal: self._gallery_menu(lst, pos))
            gal.setViewMode(QListWidget.IconMode)
            gal.setResizeMode(QListWidget.Adjust)
            gal.setIconSize(QPixmap(1, 1).scaled(tw, th).size())
            # grille uniforme : les noms de fichier longs ne décalent
            # pas les colonnes — le texte est élidé au centre
            gal.setUniformItemSizes(True)
            gal.setGridSize(QPixmap(1, 1).scaled(tw + 20, th + 45).size())
            gal.setWordWrap(False)
            gal.setTextElideMode(Qt.ElideMiddle)
            gal.setSpacing(8)
            gal.itemDoubleClicked.connect(self._preview_slide)
            QShortcut(QKeySequence.Delete, gal,
                      context=Qt.WidgetWithChildrenShortcut,
                      activated=self._delete_selected)
            pv.addWidget(gal, 1)
            self.galleries[sub] = gal
            inner.addTab(page, label)

        lay.addWidget(inner, 1)
        return w

    # ———————————————————— slideshow ————————————————————

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
        sfx = "_p" if portrait else ""
        scr = int(load_settings().get(f"ss_screen{sfx}") or -1)
        win = SlideshowWindow(portrait=portrait, screen_idx=scr)
        win.setAttribute(Qt.WA_DeleteOnClose)
        self._slideshows.append(win)
        win.destroyed.connect(
            lambda *a, w=win: self._slideshows.remove(w)
            if w in self._slideshows else None)

    # ———————————————————— export ————————————————————

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

    # ———————————————————— galerie ————————————————————

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
        for gal in self.galleries.values():
            gal.clear()
        if not files:
            self._gal_seen = set()   # le suivi incrémental part de zéro
            for gal in self.galleries.values():
                it = QListWidgetItem(
                    "Aucune diapo — lancez une génération (Ctrl+G)")
                it.setFlags(Qt.NoItemFlags)
                it.setTextAlignment(Qt.AlignCenter)
                gal.addItem(it)
            return

        def work():
            from PySide6.QtGui import QImageReader
            items = []
            for p in files:
                r = QImageReader(str(p))
                sz = r.size()
                if sz.isValid():
                    if p.parent.name == "portrait":
                        sz.scale(160, 285, Qt.KeepAspectRatio)
                    else:
                        sz.scale(280, 160, Qt.KeepAspectRatio)
                    r.setScaledSize(sz)
                img = r.read()
                if img.isNull():
                    continue
                rel = str(p.relative_to(d))
                label = p.name.removeprefix("slide-").removesuffix(".png")
                items.append((rel, label, img, str(p)))
            self.thumbs_ready.emit(gen, items)

        threading.Thread(target=work, daemon=True).start()

    def _fill_gallery(self, gen, items):
        if gen != self._gal_gen:
            return  # un rafraîchissement plus récent est en cours
        for gal in self.galleries.values():
            gal.clear()
        self._gal_seen = {rel for rel, _, _, _ in items}
        for rel, label, img, path in items:
            gal = self.galleries.get(Path(rel).parent.name)
            if gal is None:
                continue
            it = QListWidgetItem(label)
            it.setIcon(QPixmap.fromImage(img))
            it.setData(Qt.UserRole, rel)
            it.setToolTip(path)
            gal.addItem(it)
        for sub, gal in self.galleries.items():
            if not gal.count():
                it = QListWidgetItem(
                    "Aucune diapo "
                    f"{'paysage' if sub == 'landscape' else 'portrait'}"
                    " — cochez le layout dans Général puis "
                    "générez (Ctrl+G)")
                it.setFlags(Qt.NoItemFlags)
                it.setTextAlignment(Qt.AlignCenter)
                gal.addItem(it)

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
                    if p.parent.name == "portrait":
                        sz.scale(160, 285, Qt.KeepAspectRatio)
                    else:
                        sz.scale(280, 160, Qt.KeepAspectRatio)
                    r.setScaledSize(sz)
                img = r.read()
                if img.isNull():
                    items.append((rel, None, None, None))
                    continue
                label = p.name.removeprefix("slide-").removesuffix(".png")
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
        for rel, label, img, path in items:
            gal = self.galleries.get(Path(rel).parent.name)
            if gal is None:
                continue
            # retire le placeholder « aucune diapo » s'il est encore là
            if (gal.count() == 1
                    and not gal.item(0).data(Qt.UserRole)):
                gal.clear()
            it = QListWidgetItem(label)
            it.setIcon(QPixmap.fromImage(img))
            it.setData(Qt.UserRole, rel)
            it.setToolTip(path)
            gal.addItem(it)

    # ———————————————————— par diapo ————————————————————

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
        gal = self.galleries.get(Path(rel).parent.name)
        if gal is None:
            return
        for i in range(gal.count()):
            it = gal.item(i)
            if it.data(Qt.UserRole) == rel:
                # même décodage réduit que les vignettes du worker
                from PySide6.QtGui import QImageReader
                r = QImageReader(str(resolve_out_dir() / rel))
                sz = r.size()
                if sz.isValid():
                    sz.scale(160, 285, Qt.KeepAspectRatio) \
                        if rel.startswith("portrait/") else \
                        sz.scale(280, 160, Qt.KeepAspectRatio)
                    r.setScaledSize(sz)
                img = r.read()
                if not img.isNull():
                    it.setIcon(QPixmap.fromImage(img))
                break

    def _gallery_menu(self, gal, pos):
        """Menu contextuel d'une galerie : aperçu / fiche / suppression."""
        from PySide6.QtWidgets import QMenu
        it = gal.itemAt(pos)
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
        if gal.selectedItems():
            m.addAction("Supprimer la sélection…").triggered.connect(
                self._delete_selected)
        if m.actions():
            m.exec(gal.viewport().mapToGlobal(pos))

    def _delete_selected(self):
        """Supprime les diapos sélectionnées : PNG paysage + portrait +
        HTML source (toutes les variantes), puis met manifest.txt à jour
        pour que la prochaine synchro propage la suppression."""
        items = [it for gal in self.galleries.values()
                 for it in gal.selectedItems()
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
