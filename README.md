# nextevents-desktop — diaporama Champs Libres en app portable

Réécriture autonome de [nextevents](https://github.com/dewiweb/nextevents)
en application desktop native : même génération de diapos (paysage 16:9 +
portrait A4, diapo du jour, synchros FTP/SMB), packagée en **application
portable** — pas de Docker, pas de serveur, pas de dépendance au dépôt
upstream :

- **Windows** : dossier portable zip (`nextevents.exe`)
- **Linux** : AppImage (`nextevents-linux-*.AppImage`) — un seul
  fichier, `chmod +x`, on lance. Distro-indépendant (libs embarquées)

## Architecture

Tout est local — aucun serveur web, aucun navigateur externe :

- **`nextevents/`** — logique métier portée depuis l'upstream
  (scraping leschampslibres.fr + OpenAgenda, rendu HTML→PNG, synchros
  FTP/SMB/local, planificateur, diapo du jour)
- **`ui/`** — interface native **PySide6/Qt Widgets** : fenêtre à onglets
  (Général, Destinations, Diapo du jour, Diaporama), galerie de vignettes
  avec aperçu intégré — alimentée **au fil de la génération** (décodage
  en worker thread), journal en direct, barre de progression globale,
  raccourcis (`Ctrl+G` générer, `Ctrl+S` enregistrer, `F11` diaporama,
  `F5` galerie), indicateur de réglages modifiés. Garde-fou molette :
  les combos/spin non focalisés ignorent la roulette (elle scrolle la
  page) — `WheelGuard` installé au niveau `QApplication`
- **`ui/slideshow.py`** — player plein écran natif (fondu/glissement,
  pause au clic, rechargement auto des diapos et réglages) — remplace
  l'ancien slideshow HTML/JS
- **Rendu** : Chromium *headless shell* embarqué (appairé au driver
  Playwright) — immunisé aux mises à jour de navigateur sur les postes.
  Pour forcer un navigateur système : `NEXTEVENTS_BROWSER_CHANNEL=msedge`
- **Tray** : `QSystemTrayIcon` natif (Win32 / SNI) — fermer la fenêtre
  réduit en icône, double-clic la réaffiche, menu complet (générer,
  dossier de destination, ouvrir les diapos, quitter)
- **Instance unique** : un second lancement remet la fenêtre existante
  au premier plan au lieu de démarrer un processus concurrent
- Données dans `./data/` à côté de l'exe/AppImage (diapos, réglages,
  cache fontes/images, `app.log`) — portable, copiable tel quel ;
  repli sur `~/.nextevents` si l'emplacement est en lecture seule

Divergence assumée avec l'upstream : `assets/today_template.html`
embarque un auto-fit (`--k`) qui réduit proportionnellement toute la
mise en page quand le contenu déborde (longues qualifications
d'intervenants) — à reverser upstream si souhaité.

## Sources d'événements

Réglage « Source » dans l'onglet Général — deux chemins avec repli
automatique :

1. **OpenAgenda v2** (clé API renseignée) : `timings[gte]` filtré
   côté serveur, schéma de l'agenda pour décoder catégories/publics,
   fetch du détail quand la liste omet les `timings` (événements à
   très nombreuses séances, ex. rdv4c)
2. **Export legacy** `events.json` (sans clé, endpoint déprécié) :
   historique complet, filtrage des terminés côté client
3. **Scraping du site** leschampslibres.fr : repli si OA est KO, et
   seule source de la couleur éditoriale des cartes

Les événements des deux sources convergent vers le même format
interne — le rendu, le filtrage et la diapo du jour sont identiques.

### Catégories et limiteur

- **Catégories** : cases à cocher par catégorie du programme (les 10
  slugs du site) ; la sélection vide = aucun événement. Côté OA, le
  filtrage mappe les catégories OA (`_oa_cat`) sur les slugs site.
- **Limiteur** (réglage « Affichage ») : trois modes —
  `Nombre max` (historique), `Dans les N jours`, `Jusqu'au <date>`.
  Un événement est gardé si sa fenêtre [début, fin] intersecte
  [aujourd'hui, horizon] — les expos en cours restent donc visibles.

## Specs affichées sur les diapos

Ordre fixe `SPEC_ORDER`, chaque ligne absente est omise :

| Spec | Contenu / règles |
|---|---|
| **Date** | `JJ/MM/AA à HHh` (séance unique) · `Du … au …` (multi-jours) · `Prochaine séance : …` (récurrent, > 1 séance à venir) · `Exposition permanente` |
| **Séances** | `N séances à venir` (≤ 30) · `Séances régulières` (> 30 — le décompte n'a plus de sens, ex. animations quotidiennes) |
| **Durée** | `1h30` — masquée si ≥ 4 h (plage d'ouverture, pas une séance) |
| **Lieu** | omis pour les « Temps fort » multi-sites |
| **Tarif** | texte OA `conditions` ou carte site |
| **Public** | `Familles · dès 8 ans` (schéma OA `publics` + `age.min`) |
| **Accessibilité** | keywords OA `def*` ∪ mentions dans le texte |

### Classification date (OA)

La durée **médiane** des timings tranche le type d'événement :

- timings = plages d'ouverture (médiane ≥ 4 h) sur > 300 j et ≥ 50 %
  des jours → **Exposition permanente** (pas de compteur ni durée)
- séances courtes très nombreuses (Merlin : 1640 × 1 h) → récurrent,
  « Prochaine séance » + « Séances régulières »
- jours contigus (≥ 80 % du span, expo temporaire/temps fort) →
  « Du … au … », épinglé en tête tant qu'il est en cours
- sinon → séance unique ou récurrente classique

Le site éclate chaque séance en carte : `group_sessions` les
refusionne par titre — même sémantique « Prochaine séance ».

## Séries éditoriales

Réglage « Séries éditoriales » (Général) — une ligne par série :

```
identifiant = Libellé | chemin/logo-optionnel
```

- L'identifiant matche **aussi bien** un slug de page série du site
  (`les-grands-temoins`) qu'un keyword OA (`grandstemoins`)
- Bouton **« Détecter dans les sources »** : scanne les keywords OA
  (export legacy) + les liens série des pages détail du site, croise
  par normalisation (accents/casse), récupère les vrais libellés dans
  les `<h1>` des pages série — pré-remplit le champ sans écraser
- `| logo.png` optionnel : remplace le badge circulaire générique —
  chemin absolu ou relatif au dossier `data/`
- Les keywords non-série (`vacances`, `fetedelascience`…) sont
  conservés dans `events.json` — base d'un futur filtre thématique
- L'URL du QR de la diapo du jour est résolue en testant les
  identifiants de la série (le premier slug site qui répond gagne)

## Diapo du jour

Onglet dédié : sélection d'un événement, intervenants/animatrice
éditable, notes, accessibilité (événement + lieu), fond (pastels +
image), **accent** (auto = couleur éditoriale de la carte, ou
pastel choisi — pilote badge, filet, tons `color-mix` dérivés).

Série détectée → variante « série » (fond marine, titre majuscules,
badge ou logo custom). Génère `index.*` + `qr.*` dans `today/`,
synchronisé comme le diaporama. Vignettes cliquables (aperçu
agrandi) et suppression directe dans la colonne gauche.

## Secrets

Les identifiants (`ftp_pass`, `smb_pass`, `oa_api_key`) ne restent
pas dans `settings.json` quand un meilleur support existe :

1. **Variable d'environnement** `NEXTEVENTS_FTP_PASS`,
   `NEXTEVENTS_SMB_PASS`, `NEXTEVENTS_OA_API_KEY` — prime toujours,
   idéal pour un poste headless
2. **Trousseau de l'OS** via `keyring` — Credential Manager sous
   Windows, Secret Service (GNOME Keyring / KWallet) sous Linux ;
   le champ de réglage affiche « enregistré dans le trousseau »
3. **`settings.json`** en clair — dernier repli (Linux sans session
   D-Bus) ; le placeholder signale alors « enregistré en clair »

Les valeurs en clair d'une ancienne installation migrent vers le
trousseau au premier enregistrement des réglages.

## Usage (utilisateur final)

Lancer `nextevents.exe` / l'AppImage → fenêtre principale :

- **Général** — réglages (intervalle, nb d'événements, résolution,
  layouts), journal de génération. Le layout
  portrait propose deux formats : **A4** (impression, 150-300 dpi)
  ou **écran 9:16** (écran 16:9 monté en vertical / totem)
- **Destinations** — dossier de sortie, copie miroir locale
  (disque / lecteur réseau), FTP/FTPS et SMB avec test de connexion.
  Chaque destination choisit les layouts envoyés. Les
  synchros sont **miroir** avec la même arborescence (`landscape/`,
  `portrait/`, `today/`) : elles suppriment à distance les fichiers
  générés (`slide-*`, `index`/`qr`) absents en local — utilisez un
  dossier de destination dédié ; préférez FTPS à FTP (identifiants
  chiffrés)
- **Diapo du jour** — choix d'un événement, intervenants, fond,
  notes, génération + envoi, aperçu
- **Galerie** — un sous-onglet par orientation, calqué sur le dossier
  de sortie : « Paysage — landscape/ » et « Portrait — portrait/ ».
  Chacun a ses réglages de lecture (intervalle, transition, durée,
  lancement du player) ; barre d'actions commune (actualiser, ouvrir
  le dossier, export `.zip`, suppression multi-sélection via Suppr /
  clic droit — propage aux synchros)

Fermer la fenêtre réduit l'app dans la zone de notification ; double-
clic sur l'icône la réaffiche. Clic droit : Afficher / Générer
maintenant / Dossier de destination… / Ouvrir les diapos / Quitter.

L'infobulle de l'icône affiche le nombre de diapos et l'état. Journal
applicatif : `data/app.log`. Diagnostic du rendu : `--diag` →
`data/diag.log`.

## Build Windows (Python ≥ 3.11)

```bat
git clone https://github.com/dewiweb/nextevents-desktop
cd nextevents-desktop
build.bat
```

Produit `dist\nextevents\` — dossier portable à livrer en .zip.

## Build Linux (Python ≥ 3.11)

```bash
git clone https://github.com/dewiweb/nextevents-desktop
cd nextevents-desktop
pip install -r requirements-desktop.txt
PLAYWRIGHT_BROWSERS_PATH=0 playwright install chromium --only-shell
playwright install-deps chromium   # libs système (sudo) pour l'AppImage
pyinstaller --clean --noconfirm app.spec
appimage/build-appimage.sh
```

Produit `dist/nextevents-linux.AppImage` — fichier portable unique.
Exécution nécessitant FUSE : `apt install libfuse2` sur Ubuntu ≥ 22.04
(ou `--appimage-extract-and-run`).

## Notes techniques

- PyInstaller onedir (démarrage rapide, fiable) ; journal dans
  `data/app.log` — utile au diagnostic
- Qt **Widgets** seulement : QtWebEngine/QtQml/Qt3D exclus du bundle
  (`app.spec`) — le headless shell Playwright (~260 Mo) reste le seul
  Chromium embarqué
- Variables d'environnement posées par `desktop.py` :
  `OUT_DIR`/`SETTINGS_FILE` → `./data`, `NEXTEVENTS_ASSET_DIR` → assets
  du bundle, `NEXTEVENTS_FONT_DIR`/`NEXTEVENTS_CACHE_DIR` → `./data`
  (fontes amorcées depuis `assets/fonts` — rendu correct hors-ligne),
  `NEXTEVENTS_BROWSER_CHANNEL` optionnel
- Réglages écrits de façon atomique (`settings.json.tmp` + rename) —
  un crash ne peut pas tronquer le fichier
- Proxy d'entreprise : honorer `HTTP_PROXY`/`HTTPS_PROXY` si besoin ;
  `truststore` fait confiance au magasin de certificats système
  (interception TLS des pare-feux d'entreprise)

## Antivirus / réputation (Symantec, SmartScreen…)

Les exes PyInstaller **non signés** déclenchent fréquemment des alertes
de réputation (Symantec WS.Reputation/SONAR, SmartScreen) : faux
positif classique pour un binaire neuf et peu téléchargé. Ce n'est pas
un signal de compromission — le build est reproductible depuis le tag
GitHub via la CI publique, et le SHA256 du zip est vérifiable.

Mitigations mises en place :

- Métadonnées de version embarquées (`version.txt` : éditeur, produit,
  description) — un exe identifié est moins suspect qu'un exe anonyme
- Icône applicative (`nextevents.ico`)
- Build onedir (pas de self-extract dans `%TEMP%`, moins suspect)

Recommandations de déploiement, par ordre d'efficacité :

1. **Whitelisting par le SI** — procédure normale pour un outil
   interne ; l'alerte ne bloque généralement que le premier lancement.
   Fournir le SHA256 du zip + le lien vers le tag/build GitHub comme
   garantie de provenance.
2. **Signalement de faux positif** — formulaire « report false
   positive » de l'éditeur AV (ex. Broadcom/Symantec) ; gratuit,
   efficace en quelques jours.
3. **Signature de code** — fix durable : certificat OV (~200-400 €/an)
   ou Azure Trusted Signing (~10 €/mois). La réputation se construit
   alors release après release au lieu de repartir de zéro à chaque
   binaire.
