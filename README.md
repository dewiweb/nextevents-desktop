# nextevents-desktop — diaporama Champs Libres en app Windows portable

Version desktop de [nextevents](https://github.com/dewiweb/nextevents) :
même webui, même génération de diapos (paysage 16:9 + portrait A4,
diapo du jour, synchros FTP/SMB), packagée en **application portable
Windows** — pas de Docker, pas de serveur.

Le code métier vit dans le dépôt principal, inclus ici en **submodule
`upstream/`**. Ce dépôt n'ajoute que le lanceur desktop et le packaging.

## Principe

- `desktop.py` lance le serveur Flask sur `127.0.0.1:8095` et ouvre la
  webui dans une fenêtre dédiée `--no-proxy-server`
- Rendu HTML→PNG et fenêtre webui via le **Chromium embarqué** dans le
  bundle — hors GPO/proxy du navigateur géré par l'entreprise (repli :
  Edge du poste en canal `msedge`, puis navigateur par défaut)
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
  `PLAYWRIGHT_BROWSERS_PATH` → `ms-playwright` du bundle (sinon
  `NEXTEVENTS_BROWSER_CHANNEL=msedge`)
- Réseau d'entreprise : TLS intercepté → magasin de certs Windows
  (`truststore`) ; proxy PAC/WPAD résolu via `pypac` (+ auth
  Negotiate/NTLM du compte via `requests_negotiate_sspi`) ; forçage
  manuel possible via `NEXTEVENTS_PROXY=http://proxy:3128`. La webui
  s'ouvre dans une fenêtre Edge dédiée `--no-proxy-server` (le PAC peut
  envoyer 127.0.0.1 au proxy) — profil `data/edge-ui`
- `nextevents.exe --diag` écrit `data/diag.log` — diagnostic complet
  poste pro : port libre, proxy (env, registre IE, PAC résolu par URL
  dont 127.0.0.1), stratégies navigateur GPO, AppLocker, TCP direct vs
  proxy, GET réels + scrape p1, lancement Edge/Playwright, et test
  décisif de joignabilité 127.0.0.1 avec/sans `--no-proxy-server`
- Antivirus : PyInstaller onedir est parfois flaggé à tort —
  prévoir une exception si nécessaire
