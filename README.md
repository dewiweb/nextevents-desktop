# nextevents-desktop — diaporama Champs Libres en app Windows portable

Version desktop de [nextevents](https://github.com/dewiweb/nextevents) :
même webui, même génération de diapos (paysage 16:9 + portrait A4,
diapo du jour, synchros FTP/SMB), packagée en **application portable
Windows** — pas de Docker, pas de serveur.

Le code métier vit dans le dépôt principal, inclus ici en **submodule
`upstream/`**. Ce dépôt n'ajoute que le lanceur desktop et le packaging.

## Principe

- `desktop.py` lance le serveur Flask sur `127.0.0.1:8095` et ouvre le
  navigateur par défaut
- Le rendu HTML→PNG pilote **Microsoft Edge** (présent sur tout
  Windows 10/11) via le canal `msedge` de Playwright — **aucun
  téléchargement de navigateur**
- Données dans `./data/` à côté de l'exe (diapos, réglages, cache
  fontes/images) — le dossier est copiable/déplaçable tel quel

## Build (sur une machine Windows + Python ≥ 3.11)

```bat
git clone --recurse-submodules https://github.com/dewiweb/nextevents-desktop
cd nextevents-desktop
build.bat
```

Produit `dist\nextevents\` — dossier portable. Le livrer en .zip ;
l'utilisateur lance `nextevents.exe`.

## Usage

- Double-clic sur `nextevents.exe` → console + ouverture de
  http://127.0.0.1:8095 (la webui habituelle)
- Scraping → besoin d'Internet (leschampslibres.fr, openagenda.com)
- Synchros FTP/SMB identiques au serveur
- Fermer la console ou Ctrl+C pour quitter

## Mise à jour du code métier

```bat
git submodule update --remote upstream
build.bat
```

## Notes techniques

- PyInstaller onedir (démarrage rapide, fiable) ; la console affiche le
  journal — utile au diagnostic
- Variables d'environnement posées par `desktop.py` :
  `OUT_DIR`/`SETTINGS_FILE` → `./data`, `NEXTEVENTS_ASSET_DIR` → assets
  du bundle, `NEXTEVENTS_FONT_DIR`/`NEXTEVENTS_CACHE_DIR` → `./data`,
  `NEXTEVENTS_BROWSER_CHANNEL=msedge`
- Proxy d'entreprise : honorer `HTTP_PROXY`/`HTTPS_PROXY` si besoin ;
  `truststore` fait déjà confiance au magasin de certificats Windows
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
