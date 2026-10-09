"""Aide contextuelle — bouton « ? » de l'en-tête et touche F1.

Un dialog par rubrique (une par onglet + raccourcis) : les tooltips
expliquent un champ, ici c'est la démarche — « à quoi sert cet
onglet, comment m'y prendre ». Contenu HTML dans TOPICS, l'index de
rubrique suit l'ordre des onglets de la fenêtre.
"""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QTextBrowser,
    QVBoxLayout,
)

TOPICS = [
    ("Général — produire les diapos", """
<p>Le bouton <b>Générer</b> (Ctrl+G) relève les événements à venir
des Champs Libres et produit les diapos dans le dossier de sortie —
une par événement, actualisées à chaque passage.</p>

<p><b>Planification</b> — « Rafraîchissement auto » régénère toutes
les N minutes ; « … et/ou à heures fixes » cale la génération sur
des horaires précis (ex. <i>06:00, 18:30</i>).</p>

<p><b>Diapos générées</b> — quels événements inclure : les N
premiers, tout ce qui a lieu dans les N jours, ou jusqu'à une
date. Un événement en cours (expo permanente…) reste affiché.</p>

<p><b>Layouts</b> — « Paysage » pour les TV et écrans ; « Portrait »
pour l'impression A4 ou un écran pivoté 9:16.</p>

<p><b>Source des événements</b> — le site web suffit dans la plupart
des cas ; OpenAgenda apporte des données plus riches si vous avez
une clé API (repli automatique sur le site si injoignable).</p>

<p><b>Informations affichées</b> — les specs visibles sur les diapos
(durée, lieu, tarif…) peuvent être masquées, forcées ou expurgées de
valeurs précises.</p>

<p>Le <b>journal</b> en bas d'onglet trace chaque génération — c'est
le premier endroit à regarder si un résultat surprend.</p>
"""),

    ("Destinations — où vont les diapos", """
<p>Chaque génération écrit les diapos dans le <b>dossier de
sortie</b>, puis les pousse vers les destinations remplies.</p>

<p><b>Dossier de sortie</b> — vide = dossier intégré de l'app
(<i>data/diaporama</i>). Utile pour écrire directement sur un
lecteur réseau monté.</p>

<p><b>Copie miroir</b> — clone la sortie vers un autre dossier
(partage, clé USB…) sans serveur.</p>

<p><b>FTP / SMB</b> — envoi vers un serveur ou un partage Windows ;
renseignez hôte, identifiants, chemin puis « Tester la connexion »
avant la première génération.</p>

<p><b>Attention, miroir</b> : les synchros suppriment à distance les
fichiers générés absents en local — utilisez des dossiers de
destination dédiés.</p>
"""),

    ("Diapo du jour — l'annonce auditorium", """
<p>Une diapo à part, générée à la main pour l'événement du jour
(hall, auditorium) — indépendante du diaporama, écrite dans
<i>today/</i> et poussée comme le reste vers les destinations.</p>

<p><b>Événement</b> — la liste vient de la dernière génération ; le
choix pré-remplit titre, intervenants, animateur, notes et
accessibilité. Tout se retouche avant génération.</p>

<p><b>Fond et accent</b> — palette de couleurs ; une série
éditoriale applique automatiquement son modèle (fond marine).</p>

<p>« <b>Générer la diapo du jour</b> » produit <i>index.png</i>
(+ <i>qr.png</i> pour les séries, renvoyant vers la billetterie) ;
l'aperçu ouvre le rendu en grand.</p>
"""),

    ("Galerie — voir, diffuser, imprimer", """
<p>Un sous-onglet par orientation, calqué sur le dossier de sortie
(<i>landscape/</i>, <i>portrait/</i>) : ce qu'on voit ici est ce que
les écrans diffusent.</p>

<p><b>Lecture</b> — réglages du diaporama plein écran : intervalle
entre diapos, transition, écran de diffusion (relu en continu : un
écran rebranché est pris en compte sans relancer).</p>

<p><b>Par diapo</b> — double-clic pour l'aperçu ; clic droit pour
régénérer une seule diapo, lancer le diaporama depuis elle, ou la
supprimer. La sélection multiple (Suppr) propage aux synchros.</p>

<p><b>Actions</b> — « Exporter en .zip » pour transmettre les
visuels à un partenaire ; « Imprimer… » pour la sélection ou toute
l'orientation (dialogue d'impression → PDF possible).</p>
"""),

    ("Raccourcis & astuces", """
<p><b>Clavier</b> — Ctrl+G générer · Ctrl+S enregistrer les
réglages · F11 diaporama paysage · F5 recharger la galerie · F1
cette aide · Échap quitter le diaporama · Suppr retirer la
sélection.</p>

<p><b>Zone de notification</b> — fermer la fenêtre réduit l'app en
icône (le planificateur continue). Clic droit sur l'icône :
générer, ouvrir le dossier, lancer un diaporama.</p>

<p><b>« Réglages modifiés * »</b> dans le titre = des changements ne
sont pas enregistrés — Ctrl+S avant de générer pour qu'ils soient
pris en compte.</p>

<p><b>En cas de souci</b> — journal de génération en bas de Général,
journal applicatif <i>data/app.log</i>, diagnostic du rendu via
<i>nextevents --diag</i> (écrit <i>data/diag.log</i>).</p>
"""),
]


class HelpDialog(QDialog):
    """Sélecteur de rubrique + texte. `topic` = index dans TOPICS
    (aligné sur les onglets de la fenêtre, Raccourcis en dernier)."""

    def __init__(self, parent, topic=0):
        super().__init__(parent)
        self.setWindowTitle("Aide")
        self.resize(560, 520)
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
        _t, html = TOPICS[i]
        self.body.setHtml(html)
