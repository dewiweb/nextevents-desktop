"""Source OpenAgenda : alternative au scraping de leschampslibres.fr.

Chaîne de repli :
  1. API v2 officielle (si `oa_api_key` renseignée) — timings filtrés
     côté serveur, schéma de l'agenda pour les libellés catégorie/public
  2. export legacy events.json (sans clé, endpoint déprécié)
  3. à l'appelant de retomber sur le scraping du site si OA est KO

Produit le même format d'événement que scrape.list_events() : title,
url, tag, specs{Date, Séances, Durée, Lieu, Tarif, Public,
Accessibilité}, desc, desc_long, speakers, moderator, note, access,
access_venue, series, image, credit, _dt, _dt_end, pinned.

Différences assumées vs site :
  - pas de `color` (choix éditorial du site) → pastel par défaut
  - `tag` mappé depuis la catégorie OA (Événement → « Temps fort »,
    Atelier 4C → « Rendez-vous 4C »)
"""

import datetime
import re
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .scrape import (
    DEFAULT_CATEGORIES, _extract_access, _extract_note, _extract_people,
)

TZ = ZoneInfo("Europe/Paris")
API = "https://api.openagenda.com/v2"
UA = {"User-Agent": "nextevents/1.0"}

# slug de la page catégorie du site ↔ valeur « categorie » OA
SLUG_TO_OA = {
    "rencontres-aux-champs-libres": "rencontre",
    "concerts-aux-champs-libres": "concert",
    "projections-aux-champs-libres": "projection",
    "spectacles-aux-champs-libres": "spectacle",
    "evenements-aux-champs-libres": "evenement",
    "animations-aux-champs-libres": "animation",
    "ateliers-aux-champs-libres": "atelier",
    "expositions-aux-champs-libres": "exposition",
    "rdv4c-aux-champs-libres": "atelier-4c",
    "visites-aux-champs-libres": "visite",
}
# libellés affichés sur les diapos (la taxonomie OA ≠ wording du site)
OA_TAG_LABEL = {
    "evenement": "Temps fort",
    "atelier-4c": "Rendez-vous 4C",
}

# défaut si le réglage series_map est vide — voir parse_series_map
SERIES_KEYWORDS = {"grandstemoins": "Les grands témoins"}

# mots-clés OA « déficiences » → mention d'accessibilité actionnable
ACCESS_KEYWORDS = {
    "defautidif_lsf": "Interprétation en LSF",
    "defauditif_amp": "Dispositifs d'écoute amplifiée",
    "defvisuel": "Audiodescription",
}

# accessibilité du lieu (codes OA v2 / legacy)
VENUE_ACCESS = {
    "ii": "Handicap intellectuel", "hi": "Handicap auditif",
    "vi": "Handicap visuel", "mi": "Handicap moteur",
    "pi": "Handicap psychique",
}

PUBLIC_LABEL = {"Tous publics": "Tout public"}  # wording du site


# ———————————————————— formatage ————————————————————

def _clean_md(text):
    """OA sert les descriptions en markdown-lite — on enlève les
    marqueurs pour le rendu texte des diapos."""
    if not text:
        return ""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)   # **gras**
    text = re.sub(r"__(.+?)__", r"\1", text)       # __gras__
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)  # *ital*
    text = re.sub(r"\[(.+?)\]\([^)]*\)", r"\1", text)      # [lien](url)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)         # ## titre
    # espaces invisibles OA (zero-width, insécable) → espace normal,
    # sinon « 15h00Où » quand le saut de ligne markdown est réduit
    text = text.replace("​", " ").replace(" ", " ")
    return text.strip()


def _local(dt):
    """ISO → tuple (a, m, j, h, min) en heure de Paris."""
    d = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
    d = d.astimezone(TZ)
    return (d.year, d.month, d.day, d.hour, d.minute)


def _fmt_day(t):
    return f"{t[2]:02d}/{t[1]:02d}/{str(t[0])[2:]}"


def _fmt_time(t):
    return f"{t[3]}h{t[4]:02d}".replace("h00", "h")


def _duration(begin, end):
    """minutes entre deux timings → libellé '1h30' / '45 min' / '1h'."""
    mins = (datetime.datetime(*end) - datetime.datetime(*begin)
            ).total_seconds() // 60
    if mins <= 0 or mins >= 4 * 60:
        # ≥ 4 h = amplitude d'ouverture du lieu, pas durée de séance
        return ""
    h, m = divmod(int(mins), 60)
    return f"{h}h{m:02d}" if m else (f"{h}h" if h else f"{mins} min")


def _date_spec(timings):
    """Construit la spec Date + compteur de séances + durée + bornes.
    timings : liste de tuples locaux (begin, end) triés par début.
    Retourne (date_spec, nb_séances, durée, _dt, _dt_end, pinned)."""
    today = datetime.date.today()
    future = [t for t in timings if t[1][:3] >=
              (today.year, today.month, today.day)]
    if not future:
        future = timings
    first_b, _ = timings[0]
    last_e = timings[-1][1]
    span = (datetime.date(*last_e[:3]) - datetime.date(*first_b[:3])).days

    days = {t[0][:3] for t in timings}
    durs = sorted((datetime.datetime(*e) - datetime.datetime(*b))
                  .total_seconds() // 60 for b, e in timings)
    med = durs[len(durs) // 2]
    # un timing = bloc d'ouverture de journée (≥ 4 h) → vraie expo
    # permanente ; des séances courtes très nombreuses (animations
    # planétarium : 1640 × 60 min sur 2 ans) sont programmées —
    # « Prochaine séance » leur convient mieux
    open_blocks = med >= 4 * 60
    if span > 300 and open_blocks and len(days) >= span * .5:
        # collection/expo sur des années, ouverte quasiment tous les
        # jours → la carte site dit « Exposition permanente » ; le
        # compteur et la durée seraient absurdes. Un rendez-vous
        # récurrent sur l'année (rdv4c : ~14 % des jours) n'en est pas
        # une — il reste dans la branche récurrente ci-dessous.
        return "Exposition permanente", 0, "", None, None, False
    contiguous = (len(days) > 1 and span > 0 and len(days) >= span * .8
                  and (open_blocks or span <= 120))
    if contiguous:
        # événement multi-jours (temps fort, expo temporaire) : même
        # remarque — le « Du … au … » suffit
        date_spec = f"Du {_fmt_day(first_b)} au {_fmt_day(last_e)}"
        t3 = (today.year, today.month, today.day)
        pinned = first_b[:3] <= t3 <= last_e[:3]
        return date_spec, 0, "", first_b, last_e, pinned
    # séance(s) ponctuelle(s) : la prochaine porte la date — préfixée
    # « Prochaine séance : » quand l'événement est récurrent
    nx = next(iter(future))
    date_spec = f"{_fmt_day(nx[0])} à {_fmt_time(nx[0])}"
    if len(future) > 1:
        date_spec = f"Prochaine séance : {date_spec}"
    return (date_spec, len(future),
            _duration(nx[0], nx[1]), nx[0], nx[0], False)


def _timings_pairs(raw):
    """Normalise timings v2 (begin/end) et legacy (start/end)."""
    out = []
    for t in raw or []:
        b = t.get("begin") or t.get("start")
        e = t.get("end")
        if b and e:
            out.append((_local(b), _local(e)))
    out.sort(key=lambda x: x[0])
    return out


# ———————————————————— mapping événement ————————————————————

def _base_map(e, cat_value, cat_label, public_label, kws, cond, timings,
              title, url, desc, desc_long, html_txt, image, credit, lieu,
              access_codes, age=None, series_map=None):
    """Construit le dict événement commun (v2 et legacy convergent ici).
    `e` ne sert que de référence pour l'uid/canonicalUrl éventuels."""
    pairs = _timings_pairs(timings)
    if pairs:
        date_spec, n_sessions, dur, dt, dt_end, pinned = (
            _date_spec(pairs))
    else:
        # aucun créneau : comme « Exposition permanente » du site
        date_spec, n_sessions, dur = "Exposition permanente", 0, ""
        dt = dt_end = None
        pinned = False

    specs = {"Date": date_spec}
    if n_sessions > 1:
        # au-delà de ~30 le décompte n'a plus de sens sur une diapo
        # (animations quotidiennes : « 1640 séances à venir »)
        specs["Séances"] = ("Séances régulières" if n_sessions > 30
                            else f"{n_sessions} séances à venir")
    if dur:
        specs["Durée"] = dur
    if lieu:
        specs["Lieu"] = lieu
    if cond:
        specs["Tarif"] = cond[:1].upper() + cond[1:]
    if public_label:
        pub = PUBLIC_LABEL.get(public_label, public_label)
        if age and age.get("min"):
            pub += f" · dès {age['min']} ans"
        specs["Public"] = pub

    tag = OA_TAG_LABEL.get(cat_value, cat_label or "Événement")
    if tag == "Temps fort":
        specs.pop("Lieu", None)  # multi-sites : le lieu prête à confusion
    desc, desc_long = _clean_md(desc), _clean_md(desc_long)

    # intervenants / animateur / notes : même heuristiques que le site
    # (la description détaillée est du texte libre dans les deux cas)
    intro = BeautifulSoup(html_txt or "", "lxml") if html_txt else None
    speakers, moderator = _extract_people(intro, title, desc_long)
    note = _extract_note(desc_long)

    # accessibilité : mots-clés structurés OA ∪ mentions dans le texte
    access_labels = [lbl for k, lbl in ACCESS_KEYWORDS.items()
                     if k in kws]
    for lbl in (_extract_access(desc_long) or "").split("\n"):
        if lbl and lbl not in access_labels:
            access_labels.append(lbl)
    access = "\n".join(access_labels)
    if access:
        specs["Accessibilité"] = access.replace("\n", " · ")

    series = next((lbl for k, lbl
                   in (series_map or SERIES_KEYWORDS).items()
                   if k in kws), "")

    return {
        "title": title, "url": url, "tag": tag, "color": None,
        "specs": specs, "desc": desc, "desc_long": desc_long,
        "speakers": speakers, "moderator": moderator, "note": note,
        "audience": public_label or "", "access": access,
        "access_venue": [VENUE_ACCESS[c] for c in access_codes
                         if c in VENUE_ACCESS],
        "series": series, "image": image, "card_img": image,
        "credit": credit, "_dt": dt, "_dt_end": dt_end,
        "pinned": pinned, "_source": "oa", "_oa_cat": cat_value,
        # keywords bruts conservés : base d'un éventuel filtre thématique
        # (fetedelascience, vacances…) — pas affichés sur la diapo
        "keywords": kws,
    }


def _map_v2(e, cat_opts, pub_opts, agenda, series_map=None):
    cat_id = e.get("categorie")
    cat_value, cat_label = (cat_opts.get(cat_id) or (None, None))
    pub_ids = e.get("publics") or []
    if isinstance(pub_ids, int):
        pub_ids = [pub_ids]
    pubs = [pub_opts.get(i) for i in pub_ids if i in pub_opts]
    kws = [k for k in (e.get("keywords", {}).get("fr") or []) if k]
    cond = (e.get("conditions") or {}).get("fr")
    acc = e.get("accessibility") or {}
    acc_codes = [k for k, v in acc.items() if v] \
        if isinstance(acc, dict) else list(acc)
    img = e.get("image") or {}
    image = (img.get("base", "") + img["filename"]) \
        if img.get("filename") else None
    for v in img.get("variants") or []:
        if v.get("type") == "full":
            image = img.get("base", "") + v["filename"]
    uid = e.get("uid")
    url = (e.get("canonicalUrl")
           or (f"https://openagenda.com/{agenda}/events/"
               f"{uid}_{e.get('slug', '')}" if uid else ""))
    ev = _base_map(
        e, cat_value, cat_label, " · ".join(pubs), kws, cond,
        e.get("timings"), (e.get("title") or {}).get("fr", ""), url,
        (e.get("description") or {}).get("fr", ""),
        (e.get("longDescription") or {}).get("fr", "")
        or (e.get("description") or {}).get("fr", ""),
        (e.get("html") or {}).get("fr", ""),
        image, e.get("imageCredits") or "",
        (e.get("location") or {}).get("name", ""),
        acc_codes, e.get("age"), series_map)
    if not e.get("timings"):
        # timings indisponibles même sur le détail : le texte
        # « dateRange » éditorial (« 4 septembre 2026 - 2 juillet
        # 2027, certains vendredis ») vaut mieux que « permanente »
        dr = (e.get("dateRange") or {}).get("fr", "")
        dr = re.sub(r"\s*undefined\s*", " ", dr).strip(" ,")
        if dr:
            ev["specs"]["Date"] = dr
            ev["specs"].pop("Séances", None)
    return ev


def _map_legacy(e, series_map=None):
    cat_value = cat_label = None
    pubs = []
    for g in e.get("tagGroups") or []:
        for t in g.get("tags") or []:
            if g.get("slug") == "categorie":
                cat_value, cat_label = t.get("slug"), t.get("label")
            elif g.get("slug") == "publics":
                pubs.append(t.get("label"))
    kws = [k for k in (e.get("keywords", {}).get("fr") or []) if k]
    cond = (e.get("conditions") or {}).get("fr")
    return _base_map(
        e, cat_value, cat_label, " · ".join(p for p in pubs if p), kws,
        cond, e.get("timings"), (e.get("title") or {}).get("fr", ""),
        e.get("canonicalUrl") or "",
        (e.get("description") or {}).get("fr", ""),
        (e.get("longDescription") or {}).get("fr", "")
        or (e.get("description") or {}).get("fr", ""),
        (e.get("html") or {}).get("fr", ""),
        e.get("originalImage") or e.get("image"),
        e.get("imageCredits") or "", e.get("locationName", ""),
        e.get("accessibility") or [], e.get("age"), series_map)


# ———————————————————— fetch ————————————————————

def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=30, **kw)
    r.raise_for_status()
    return r


def _resolve_uid(agenda):
    """Le legacy export veut l'uid numérique ; le réglage accepte le
    slug lisible — on l'extrait de la page publique de l'agenda."""
    if agenda.isdigit():
        return int(agenda)
    html_txt = _get(f"https://openagenda.com/fr/{agenda}").text
    m = re.search(r"agendas/(\d+)", html_txt)
    if not m:
        raise RuntimeError(f"uid de l'agenda « {agenda} » introuvable")
    return int(m.group(1))


def _v2_events(agenda, key, series_map=None):
    """API v2 officielle : schéma (libellés catégorie/public) puis
    événements à venir paginés."""
    a = _get(f"{API}/agendas/{agenda}",
             params={"key": key}).json()
    cat_opts, pub_opts = {}, {}
    for f in a.get("schema", {}).get("fields", []):
        opts = {o["id"]: (o.get("value"),
                         (o.get("label") or {}).get("fr"))
                for o in f.get("options") or []}
        if f["field"] == "categorie":
            cat_opts = opts                     # id → (value, label)
        elif f["field"] == "publics":
            pub_opts = {i: lbl for i, (_, lbl) in opts.items()}

    today = datetime.date.today().isoformat()
    events, offset = [], 0
    while True:
        d = _get(f"{API}/agendas/{agenda}/events",
                 params={"key": key, "size": 100, "offset": offset,
                         "detailed": 1,
                         "timings[gte]": today}).json()
        events += d.get("events", [])
        total = d.get("total", 0)
        offset += len(d.get("events", [])) or 100
        if not d.get("events") or offset >= total:
            break
    # la liste omet `timings` quand il y en a trop (clubs récurrents
    # type rdv4c : ~40/an) — sans eux l'événement serait classé
    # « Exposition permanente » ; on va les chercher sur le détail
    for e in events:
        if not e.get("timings") and e.get("firstTiming"):
            try:
                d = _get(f"{API}/agendas/{agenda}/events/{e['uid']}",
                         params={"key": key}).json()
                full = d.get("event", d)
                if full.get("timings"):
                    e["timings"] = full["timings"]
            except Exception:
                pass  # le texte dateRange servira de spécification
    return [_map_v2(e, cat_opts, pub_opts, agenda, series_map)
            for e in events]


def _legacy_events(agenda, series_map=None):
    """Export public legacy (sans clé, déprécié) : tout l'historique,
    filtré côté client aux événements pas terminés."""
    uid = _resolve_uid(agenda)
    today = datetime.date.today()
    events, offset = [], 0
    while True:
        d = _get(f"https://openagenda.com/agendas/{uid}/events.json",
                 params={"limit": 100, "offset": offset}).json()
        batch = d.get("events", [])
        if not batch:
            break
        events += batch
        offset += len(batch)
        if offset >= d.get("total", 0):
            break
    out = []
    for e in events:
        pairs = _timings_pairs(e.get("timings"))
        if not pairs:
            continue
        last = datetime.date(*pairs[-1][1][:3])
        if last < today:
            continue  # terminé — l'export n'a pas de filtre serveur
        out.append(_map_legacy(e, series_map))
    return out


def oa_list_events(cfg):
    """Événements via OpenAgenda selon les réglages.
    `oa_api_key` présent → v2 ; sinon export legacy public.
    Lève une exception si tout échoue (l'appelant retombe au site)."""
    agenda = (cfg.get("oa_agenda") or "leschampslibres").strip()
    key = (cfg.get("oa_api_key") or "").strip()
    from .scrape import parse_series_map
    series_map = parse_series_map(cfg.get("series_map", "")) or None
    if key:
        print("  source : OpenAgenda API v2")
        return _v2_events(agenda, key, series_map)
    print("  source : export OpenAgenda (sans clé — endpoint déprécié)")
    return _legacy_events(agenda, series_map)


def _norm(s):
    """minuscules, sans accents ni séparateurs — pour croiser un slug
    de page site (« nos-futurs-2027 ») et un keyword OA (« nosfuturs »)."""
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s
                   if not unicodedata.combining(c) and c.isalnum()).lower()


def detect_series(agenda="leschampslibres"):
    """Détecte les séries éditoriales candidates dans les deux sources :
    - keywords OA non techniques (export legacy, pas de clé requise)
    - pages « série » (/au-programme/<slug>) liées depuis les pages
      détail du site — le <h1> fournit le vrai libellé
    Retourne une liste [(identifiant, libellé)] triée ; l'UI propose de
    les ajouter au champ series_map (l'utilisateur trie/retouche)."""
    from collections import Counter
    from .scrape import BASE, get, list_events

    out = {}   # identifiant → libellé

    # — keywords OA — le legacy export est public et complet
    kws = Counter()
    try:
        uid = _resolve_uid(agenda)
        offset = 0
        while True:
            d = _get(f"https://openagenda.com/agendas/{uid}/events.json",
                     params={"limit": 100, "offset": offset}).json()
            for e in d.get("events", []):
                for k in (e.get("keywords") or {}).get("fr") or []:
                    if k and k not in ACCESS_KEYWORDS \
                            and k != "accessibilite":
                        kws[k] += 1
            offset += len(d.get("events", [])) or 100
            if not d.get("events") or offset >= d.get("total", 0):
                break
    except Exception as e:
        print(f"  ! scan keywords OA KO : {e}")

    # — pages série du site : liens éditoriaux dans les pages détail —
    links = Counter()
    try:
        for e in list_events(max_pages=1):      # ~40 cartes, toutes catégories
            try:
                h = get(e["url"]).text
            except Exception:
                continue
            for m in re.findall(r'href="(/au-programme/[^"?#]+)"', h):
                if "/categorie/" in m or re.search(r"/\d+", m):
                    continue  # liste catégorie ou événement, pas une série
                links[m.rsplit("/", 1)[-1]] += 1
    except Exception as e:
        print(f"  ! scan pages série KO : {e}")

    for slug in links:
        # vrai libellé : <h1> de la page série (retombe sur le slug
        # humanisé si la page ne répond pas)
        label = re.sub(r"[-_]+", " ", slug).strip().capitalize()
        try:
            page = get(f"{BASE}/au-programme/{slug}").text
            m = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
            if m:
                label = re.sub(r"<[^>]+>", "", m.group(1)).strip() or label
        except Exception:
            pass
        out[slug] = label
        # le keyword OA correspondant s'il existe (sous-chaîne
        # normalisée) → même série, autre source
        for k in list(kws):
            if _norm(k) in _norm(slug) or _norm(slug) in _norm(k):
                out.setdefault(k, label)
                del kws[k]
                break

    for k in kws:   # keywords sans page série associée sur le site
        out[k] = re.sub(r"[-_]+", " ", k).strip().capitalize()

    return sorted(out.items(), key=lambda kv: kv[1].lower())


def filter_categories(events, categories):
    """Restreint aux slugs de catégories du site (gen_categories).
    Sélection vide = aucune catégorie — même règle que le scraping."""
    wanted = {SLUG_TO_OA[s] for s in categories if s in SLUG_TO_OA}
    return [e for e in events if e.get("_oa_cat") in wanted]
