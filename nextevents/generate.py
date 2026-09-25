"""Orchestration : scraping → images → HTML → PNG → manifeste → synchros."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from .media import download_image, ensure_fonts
from .paths import OUT_DIR
from .scrape import (
    DEFAULT_CATEGORIES, group_sessions, list_events, mark_series,
    parse_detail, parse_series_map,
)
from .oa import oa_list_events
from .slide import (
    render_all, slide_html, slide_name, SIZES, DEFAULT_SIZE,
    portrait_key, portrait_size,
)
from .sync import sync_ftp, sync_local, sync_smb


def _render_set(events, fonts, dest, size, orientation="landscape"):
    """Génère un jeu de diapos (HTML + PNG) dans `dest` et y supprime
    les fichiers obsolètes. Retourne la liste des PNG du jeu."""
    dest.mkdir(parents=True, exist_ok=True)
    html_dir = dest / "html"
    html_dir.mkdir(exist_ok=True)

    # ne re-rendre que les diapos nouvelles ou modifiées ; supprimer
    # celles qui n'existent plus (sobriété : pas de wipe systématique)
    to_render, expected_png, expected_html = [], set(), set()
    used = set()
    for i, ev in enumerate(events, start=1):
        name = slide_name(ev, i)
        while name in used:  # collision date+titre : suffixe
            name += f"-{i}"
        used.add(name)
        expected_png.add(f"{name}.png")
        expected_html.add(f"{name}.html")
        hp, pp = html_dir / f"{name}.html", dest / f"{name}.png"
        content = slide_html(ev, i - 1, fonts, orientation)
        # PNG corrompu/interrompu → on re-rend plutôt que tout échouer
        try:
            same_size = pp.exists() and Image.open(pp).size == size
        except Exception:
            same_size = False
        if (
            same_size
            and hp.exists()
            and hp.read_text("utf-8") == content
        ):
            continue
        hp.write_text(content, encoding="utf-8")
        to_render.append((hp, pp))

    for p in dest.glob("*.png"):
        if p.name not in expected_png:
            p.unlink()
            print(f"  - {p.name} supprimée")
    for p in html_dir.glob("*.html"):
        if p.name not in expected_html:
            p.unlink()

    print(f"  rendu {orientation} — {len(to_render)} à rendre "
          f"({len(expected_png) - len(to_render)} inchangées)…")
    for pp in render_all(to_render, size, orientation):
        print(f"  ✓ {pp.name}")

    pngs = sorted(dest.glob("*.png"))

    # manifeste du jeu attendu — uploadé en dernier par les synchros
    (dest / "manifest.txt").write_text(
        "\n".join(p.name for p in pngs) + "\n", encoding="utf-8"
    )
    return pngs


def _limit_events(events, cfg, max_events):
    """Filtre de fin de liste : par nombre (historique), par horizon
    « dans les N jours » ou « jusqu'au <date> ». Un événement est gardé
    si sa fenêtre [début, fin] intersecte [aujourd'hui, horizon] —
    les multi-jours en cours (épinglés) restent donc visibles."""
    import datetime
    cfg = cfg or {}
    mode = cfg.get("limit_mode", "count")
    if mode == "count":
        return events[:max_events] if max_events else events
    today = datetime.date.today()
    if mode == "days":
        horizon = today + datetime.timedelta(
            days=int(cfg.get("limit_days") or 0))
    elif mode == "date":
        try:
            horizon = datetime.date.fromisoformat(
                str(cfg.get("limit_date") or ""))
        except ValueError:
            return events
    else:
        return events
    out = []
    for ev in events:
        s = ev.get("_dt")
        if not s:
            out.append(ev)  # sans date (expo permanente) : toujours
            continue
        e = ev.get("_dt_end") or s
        sd, ed = datetime.date(*s[:3]), datetime.date(*e[:3])
        if sd <= horizon and ed >= today:
            out.append(ev)
    return out


def generate(out_dir=None, max_events=0, pages=99, cfg=None, size=DEFAULT_SIZE):
    """Génère le diaporama complet. Retourne la liste des PNG produits.
    cfg peut contenir les réglages ftp_* et smb_* pour pousser le
    dossier vers un FTP et/ou un partage SMB après génération."""
    out = Path(out_dir) if out_dir else OUT_DIR

    print("1/5 Récupération des événements…")
    cats = DEFAULT_CATEGORIES
    if cfg and "gen_categories" in cfg:
        cats = [c for c in cfg["gen_categories"].split(",") if c]
    series_map = parse_series_map(
        (cfg or {}).get("series_map", "")) or None
    use_oa = cfg and cfg.get("data_source") == "openagenda"
    if use_oa:
        try:
            from .oa import filter_categories
            events = filter_categories(oa_list_events(cfg), cats)
        except Exception as e:
            # OA injoignable/clé invalide → repli site (seule source
            # de la couleur éditoriale de toute façon)
            print(f"  ! OpenAgenda KO ({e}) — repli scraping du site")
            use_oa = False
    if not use_oa:
        events = list_events(max_pages=pages, categories=cats)
        # une carte par séance sur le site → une diapo par événement
        events = group_sessions(events)
    events = _limit_events(events, cfg, max_events)
    print(f"  {len(events)} événements trouvés")
    if not events:
        raise RuntimeError(
            "Aucun événement trouvé — la page a peut-être changé de structure."
        )

    print("2/5 Pages de détail + images…")
    if use_oa:
        # OA donne déjà desc/speakers/image — pas de page détail à
        # scraper ; on télécharge juste l'image
        with ThreadPoolExecutor(max_workers=6) as ex:
            events = list(ex.map(download_image, events))
    else:
        with ThreadPoolExecutor(max_workers=6) as ex:
            events = list(ex.map(
                lambda e: download_image(parse_detail(e, series_map)),
                events))
        mark_series(events, series_map)

    # métadonnées pour la « diapo du jour » de la webui
    import json
    out.mkdir(parents=True, exist_ok=True)
    (out / "events.json").write_text(
        json.dumps(
            [
                {
                    "title": e["title"], "url": e["url"],
                    "slide": slide_name(e, i),
                    "image": e.get("image") or e.get("card_img"),
                    "tag": e.get("tag"), "color": e.get("color"),
                    "specs": e["specs"],
                    "desc": e.get("desc", ""),
                    "desc_long": e.get("desc_long", ""),
                    "desc_md": e.get("desc_md", ""),
                    "credit": e.get("credit", ""),
                    "speakers": e.get("speakers", []),
                    "moderator": e.get("moderator", ""),
                    "note": e.get("note", ""),
                    "audience": e.get("audience", ""),
                    "access": e.get("access", ""),
                    "access_venue": e.get("access_venue", []),
                    "series": e.get("series", ""),
                }
                for i, e in enumerate(events, start=1)
            ],
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )

    print("3/5 Fontes…")
    fonts = ensure_fonts()

    print(f"4/5 Génération du dossier {out}/…")
    gen_landscape = cfg is None or cfg.get("gen_landscape", 1)
    gen_portrait = cfg and cfg.get("gen_portrait")
    # migration : les diapos paysage vivaient à la racine avant
    # landscape/ — on retire les restes de l'ancienne arborescence
    # (fichiers générés uniquement : slide-*, html/, manifest.txt)
    if gen_landscape:
        for p in out.glob("slide-*.png"):
            p.unlink(missing_ok=True)
        hdir = out / "html"
        if hdir.is_dir():
            for p in hdir.glob("*.html"):
                p.unlink(missing_ok=True)
            try:
                hdir.rmdir()
            except OSError:
                pass
        (out / "manifest.txt").unlink(missing_ok=True)
    pngs = []
    if gen_landscape:
        pngs = _render_set(events, fonts, out / "landscape", size)
    if gen_portrait:
        # portrait A4 (impression, 150-300 dpi) ou écran 9:16 (écran
        # pivoté) selon portrait_format — sous-dossier portrait/,
        # pas poussé par les synchros paysage par défaut
        fmt = (cfg or {}).get("portrait_format") or "a4"
        _render_set(events, fonts, out / "portrait",
                    portrait_size(size, fmt), portrait_key(fmt))

    if cfg:
        if cfg.get("ftp_host"):
            print("6/6 Envoi FTP…")
            sync_ftp(out, cfg)
        if cfg.get("smb_host"):
            print("    Envoi SMB…")
            sync_smb(out, cfg)
        if cfg.get("local_dir"):
            print("    Copie dossier local…")
            sync_local(out, cfg)

    n = len(pngs) + len(list((out / "portrait").glob("*.png")))
    print(f"\nTerminé : {n} diapos dans {out}/")
    return pngs
