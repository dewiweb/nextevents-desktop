"""Application desktop : fenêtre Qt + icône de zone de notification
(QSystemTrayIcon — Win32 natif / SNI sous Linux) + planificateur."""

import subprocess
import sys
import threading

from nextevents.runner import run_generation, scheduler
from nextevents.settings import (
    load_settings, resolve_out_dir, save_settings, state,
)


def run(icon_path):
    """Lance l'UI Qt. Bloquant jusqu'à la fermeture de l'app."""
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import (QApplication, QFileDialog, QMenu,
                                   QMessageBox, QSystemTrayIcon)
    from .window import MainWindow, STYLE, WheelGuard

    app = QApplication(sys.argv)
    app.setApplicationName("Nextevents")
    app.setStyleSheet(STYLE)
    # la molette ne doit pas modifier les combos/spins lors du scroll
    app._wheel_guard = WheelGuard(app)
    app.installEventFilter(app._wheel_guard)
    icon = QIcon(str(icon_path))
    app.setWindowIcon(icon)

    # instance unique : deux processus partageraient settings.json et
    # le dossier de sortie → générations/écritures concurrentes
    INSTANCE = "nextevents-desktop"
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE)
    if probe.waitForConnected(300):
        return  # déjà lancée — l'instance existante se met au 1er plan
    server = QLocalServer(app)
    if not server.listen(INSTANCE):
        # socket orphelin après un crash (Linux) → on le reprend
        QLocalServer.removeServer(INSTANCE)
        server.listen(INSTANCE)

    tray_ok = QSystemTrayIcon.isSystemTrayAvailable()
    # avec tray : fermer la fenêtre réduit en icône ; sans : quitter
    app.setQuitOnLastWindowClosed(not tray_ok)

    win = MainWindow(tray_ok=tray_ok, icon_path=icon_path)

    def _show():
        win.show()
        win.raise_()
        win.activateWindow()

    server.newConnection.connect(
        lambda: (server.nextPendingConnection().deleteLater(), _show()))

    def _pick_dir():
        d = QFileDialog.getExistingDirectory(
            win, "Dossier de destination des diapos")
        if d:
            s = load_settings()
            s["out_dir"] = d
            save_settings(s)
            tray.showMessage("Nextevents", f"Dossier de sortie : {d}")

    def _open_dir():
        try:
            p = resolve_out_dir()
            p.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                import os
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except OSError:
            pass

    def _gen():
        if not state["running"]:
            threading.Thread(target=run_generation, daemon=True).start()

    def _quit():
        if state["running"]:
            r = QMessageBox.question(
                None, "Quitter Nextevents",
                "Une génération est en cours — quitter quand même ?",
                QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        if win._dirty and not win.confirm_quit():
            return
        app.quit()

    tray = QSystemTrayIcon(icon, app)
    menu = QMenu()
    menu.addAction("Afficher").triggered.connect(_show)
    menu.addSeparator()
    menu.addAction("Générer maintenant").triggered.connect(_gen)
    menu.addAction("Dossier de destination…").triggered.connect(_pick_dir)
    menu.addAction("Ouvrir les diapos").triggered.connect(_open_dir)
    menu.addSeparator()
    menu.addAction("Quitter").triggered.connect(_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda r: _show() if r == QSystemTrayIcon.DoubleClick else None)
    if tray_ok:
        tray.show()

    def _check_tray():
        """isSystemTrayAvailable() peut mentir (GNOME sans extension
        SNI) : si l'icône n'est jamais apparue, fermer la fenêtre doit
        quitter l'app au lieu de la laisser invisible en tâche de fond."""
        if tray_ok and not tray.isVisible():
            win._tray_ok = False
            app.setQuitOnLastWindowClosed(True)

    QTimer.singleShot(2000, _check_tray)

    # infobulle + notification de fin de génération
    st = {"was_running": False}

    def _poll():
        try:
            n = win._n_slides  # compteur déjà à jour, pas de glob ici
            running = state["running"]
            tray.setToolTip(
                f"Nextevents — {n} diapos"
                + (" · génération…" if running else ""))
            if st["was_running"] and not running:
                if state["last_error"]:
                    tray.showMessage(
                        "Nextevents — génération",
                        f"Échec : {state['last_error'][:200]}")
                else:
                    tray.showMessage(
                        "Nextevents — génération terminée",
                        f"{n} diapos générées")
            st["was_running"] = running
        except Exception:
            pass

    timer = QTimer(app)
    timer.timeout.connect(_poll)
    timer.start(5000)

    threading.Thread(target=scheduler, daemon=True).start()

    prefs = load_settings()
    mode = prefs.get("autostart_slideshow", "none")
    if mode in ("landscape", "portrait"):
        QTimer.singleShot(
            500, lambda: win._open_slideshow(mode == "portrait"))
    if tray_ok and prefs.get("start_minimized", 0):
        win.hide()      # démarre dans le tray, sans fenêtre
    else:
        _show()
    app.exec()
