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
  avec aperçu intégré, journal en direct, barre de progression globale,
  raccourcis (`Ctrl+G` générer, `Ctrl+S` enregistrer, `F11` diaporama,
  `F5` galerie), indicateur de réglages modifiés
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

## Usage (utilisateur final)

Lancer `nextevents.exe` / l'AppImage → fenêtre principale :

- **Général** — réglages (intervalle, nb d'événements, résolution,
  layouts), dossiers locaux, journal de génération
- **Destinations** — FTP/FTPS et SMB avec test de connexion
- **Diapo du jour** — choix d'un événement, intervenants, fond,
  notes, génération + envoi, aperçu
- **Diaporama** — réglages de lecture par orientation, lancement du
  player plein écran, galerie (aperçu au double-clic, suppression
  multi-sélection via Suppr / clic droit — propage aux synchros),
  export `.zip`

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
