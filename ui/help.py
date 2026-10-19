"""Aide contextuelle — bouton « ? » de l'en-tête et touche F1.

Un dialog par rubrique (une par onglet + raccourcis) : les tooltips
expliquent un champ, ici c'est la démarche — « à quoi sert cet
onglet, comment m'y prendre ». Contenu HTML dans assets/help/, un
fichier par rubrique — l'index suit l'ordre des onglets de la
fenêtre.
"""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QTextBrowser,
    QVBoxLayout,
)

from nextevents.paths import ASSET_DIR

# (titre affiché dans le sélecteur, fichier dans assets/help/)
TOPICS = [
    ("Général — produire les diapos", "general.html"),
    ("Destinations — où vont les diapos", "destinations.html"),
    ("Diapo du jour — l'annonce auditorium", "today.html"),
    ("Galerie — voir, diffuser, imprimer", "galerie.html"),
    ("Raccourcis & astuces", "raccourcis.html"),
]


def _topic_url(filename):
    """URL file:// de la rubrique — QTextBrowser la charge et résout
    les ressources relatives (<img src="img/…">) depuis assets/help/.
    None si le fichier manque (bundle incomplet ?)."""
    from PySide6.QtCore import QUrl
    p = ASSET_DIR / "help" / filename
    return QUrl.fromLocalFile(str(p)) if p.exists() else None


class HelpDialog(QDialog):
    """Sélecteur de rubrique + texte. `topic` = index dans TOPICS
    (aligné sur les onglets de la fenêtre, Raccourcis en dernier)."""

    def __init__(self, parent, topic=0):
        super().__init__(parent)
        self.setWindowTitle("Aide")
        # assez grand pour que les captures de groupes (~970 px) soient
        # lisibles à ~85 % de leur taille native dans le corps
        self.resize(920, 680)
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Rubrique :"))
        self.picker = QComboBox()
        for title, _ in TOPICS:
            self.picker.addItem(title.split(" — ")[0])
        self.picker.currentIndexChanged.connect(self._show_topic)
        row.addWidget(self.picker, 1)
        lay.addLayout(row)

        self.body = QTextBrowser()
        self.body.setOpenLinks(False)
        self.body.setStyleSheet(
            "QTextBrowser { font-size:14px; line-height:1.4 }")
        lay.addWidget(self.body, 1)

        self.picker.setCurrentIndex(
            topic if 0 <= topic < len(TOPICS) else 0)
        # index déjà à 0 → pas de signal émis, remplir quand même
        self._show_topic(self.picker.currentIndex())

    def _show_topic(self, i):
        _t, filename = TOPICS[i]
        url = _topic_url(filename)
        if url:
            self.body.setSource(url)
        else:
            self.body.setHtml(
                f"<p><i>Rubrique indisponible ({filename} absent de "
                f"assets/help/ — bundle incomplet ?)</i></p>")
