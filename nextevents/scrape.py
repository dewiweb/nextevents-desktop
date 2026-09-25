"""Scraping de leschampslibres.fr : listes catégories et pages de détail."""

import datetime
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.leschampslibres.fr"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 nextevents/1.0"

# (libellé de secours, slug de la page catégorie)
CATEGORIES = [
    ("Rencontre", "rencontres-aux-champs-libres"),
    ("Concert", "concerts-aux-champs-libres"),
    ("Projection", "projections-aux-champs-libres"),
    ("Spectacle", "spectacles-aux-champs-libres"),
    ("Temps fort", "evenements-aux-champs-libres"),
    ("Animation", "animations-aux-champs-libres"),
    ("Atelier", "ateliers-aux-champs-libres"),
    ("Exposition", "expositions-aux-champs-libres"),
    ("RDV4C", "rdv4c-aux-champs-libres"),
    ("Visite", "visites-aux-champs-libres"),
]
# les 5 catégories « vitrine » historiques : défaut du réglage
# gen_categories (le reste — ateliers, visites, rdv4c… — produit un
# volume très supérieur de séances récurrentes)
DEFAULT_CATEGORIES = [
    slug for _, slug in CATEGORIES[:5]]

# Couleurs de card du site : nom du modifieur CSS -> (fond, variante foncée).
# Reflète les classes .v-event--{couleur} / .v-banner--{couleur} du site
# (cf. app-shop-entry.*.css : --color-pale-*). None = fond neutre par défaut.
CARD_COLORS = {
    None:      ("#efeae6", "#bfbbb8"),  # pale-grey / grey-600 (défaut)
    "yellow":  ("#f6e3bb", "#d5bb85"),  # pale-yellow / pale-yellow-600
    "beige":   ("#f6e3bb", "#d5bb85"),  # pale-beige (= pale-yellow)
    "green":   ("#c6d2c9", "#9daa9f"),  # pale-green / pale-green-600
    "red":     ("#e3c2b7", "#c99483"),  # pale-red / pale-red-600
    "blue":    ("#e2dff0", "#beb7e1"),  # pale-blue / pale-blue-600
}

# Séries éditoriales du site : slug de la page série -> libellé.
# La page série (/au-programme/<slug>) liste les événements membres ;
# les pages détail portent parfois un bloc « En savoir plus » vers la
# série — double canal, la page série est la source exhaustive.
SERIES = {"les-grands-temoins": "Les grands témoins"}

# format du réglage series_map : une ligne « identifiant = Libellé »
# (slug de page série du site ou keyword OpenAgenda — c'est le même
# tableau des deux côtés : les clés diffèrent selon la source)


def parse_series(text):
    """« cle = Libellé » ou « cle = Libellé | chemin/logo.png » par
    ligne → liste de (cle, libellé, logo). Lignes vides/# ignorées."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, rest = line.split("=", 1)
        label, _, logo = rest.partition("|")
        k, label, logo = k.strip(), label.strip(), logo.strip()
        if k and label:
            out.append((k, label, logo or None))
    return out


def parse_series_map(text):
    """cle → libellé (matching site/OA — le logo ne sert qu'au rendu)."""
    return {k: l for k, l, _ in parse_series(text)}


def series_logo(text, label):
    """Chemin du logo associé au libellé de série, ou None."""
    return next((g for _, l, g in parse_series(text)
                 if l == label and g), None)

SPEC_ICONS = {"Date": "calendar", "Séances": "calendar", "Durée": "timer",
              "Lieu": "pin", "Tarif": "ticket", "Public": "group",
              "Accessibilité": "accessibility"}
SPRITE_LABELS = {v: k for k, v in SPEC_ICONS.items()}
SPEC_ORDER = ["Date", "Séances", "Durée", "Lieu", "Tarif", "Public",
              "Accessibilité"]

session = requests.Session()
session.headers["User-Agent"] = UA


def get(url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r


def _color_from_classes(classes, prefix):
    """Extrait 'yellow' de classes comme 'v-event--yellow'."""
    for c in classes or []:
        if c.startswith(prefix + "--"):
            name = c.split("--", 1)[1]
            if name in CARD_COLORS:
                return name
    return None


def parse_card(card):
    """Extrait les infos d'une carte .v-event de la liste."""
    link = card.select_one("a.v-event__link")
    if not link:
        return None
    img = card.select_one("img.v-event__picture")
    tag = card.select_one(".c-tag__label")
    specs = {}
    for spec in card.select("p.v-event__spec"):
        icon = spec.select_one("svg[aria-label]")
        text = spec.select_one(".v-event__text")
        if icon and text:
            specs[icon["aria-label"]] = " ".join(text.get_text().split())
    return {
        "title": " ".join(link.get_text().split()),
        "url": urljoin(BASE, link["href"]),
        "card_img": urljoin(BASE, img["src"]) if img else None,
        "tag": " ".join(tag.get_text().split()) if tag else None,
        "color": _color_from_classes(card.get("class"), "v-event"),
        "specs": specs,
    }


def event_dates(ev):
    """Extrait (début, fin) du spec Date :
    'Du JJ/MM/AA au JJ/MM/AA' (événement multi-jours, ex. temps fort)
    ou 'JJ/MM/AA à HHhMM'. Renvoie des tuples (a, m, j, h, min)."""
    d = ev["specs"].get("Date", "")
    m = re.search(r"(\d{2})/(\d{2})/(\d{2})\s*au\s*(\d{2})/(\d{2})/(\d{2})", d)
    if m:
        return ((2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)), 0, 0),
                (2000 + int(m.group(6)), int(m.group(5)), int(m.group(4)), 23, 59))
    m = re.search(r"(\d{2})/(\d{2})/(\d{2})\D*(\d{1,2})h(\d{2})?", d)
    if m:
        t = (2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)),
             int(m.group(4)), int(m.group(5) or 0))
        return t, t
    return None, None


def group_sessions(events):
    """Fusionne les séances multiples d'un même événement : le site
    éclate chaque date en carte séparée (animations, ateliers, visites
    et rdv4c récurrents → des dizaines de cartes par événement). Une
    diapo = un événement : on garde la prochaine séance et on signale
    le nombre total de séances à venir via la spec « Séances »."""
    groups = {}
    for ev in events:
        key = re.sub(r"[^a-z0-9à-ÿ]+", "", (ev.get("title") or "")
                     .lower())
        groups.setdefault(key, []).append(ev)
    out = []
    for g in groups.values():
        # la carte de la prochaine séance porte image/tag/couleur ;
        # son « Date » est la prochaine occurrence — c'est elle qui
        # compte pour l'affichage et le tri
        g.sort(key=lambda e: e.get("_dt") or (9999, 12, 31, 23, 59))
        ev = g[0]
        if len(g) > 1:
            ev["n_sessions"] = len(g)
            ev["specs"]["Séances"] = f"{len(g)} séances à venir"
            d = ev["specs"].get("Date", "")
            if d and not d.startswith("Prochaine séance"):
                ev["specs"]["Date"] = f"Prochaine séance : {d}"
        out.append(ev)
    out.sort(key=lambda e: (
        0 if e.get("pinned") else 1, e.get("_dt") or (9999, 12, 31, 23, 59)))
    return out


def list_events(max_pages=99, categories=None):
    """Itère les pages de chaque catégorie et retourne les événements
    dédupliqués, triés chronologiquement. `categories` restreint aux
    slugs donnés ; None = les 5 catégories vitrine historiques."""
    wanted = (set(categories) if categories is not None
              else set(DEFAULT_CATEGORIES))
    events, seen = [], set()
    for cat_label, slug in CATEGORIES:
        if slug not in wanted:
            continue
        list_url = f"{BASE}/au-programme/categorie/{slug}"
        page = 1
        while page <= max_pages:
            url = list_url if page == 1 else f"{list_url}?page={page}"
            soup = BeautifulSoup(get(url).text, "lxml")
            cards = soup.select("div.v-event")
            if not cards:
                break
            new = 0
            for card in cards:
                ev = parse_card(card)
                if ev and ev["url"] not in seen:
                    seen.add(ev["url"])
                    if not ev.get("tag"):
                        ev["tag"] = cat_label
                    events.append(ev)
                    new += 1
            if new == 0:
                break
            print(f"  {cat_label} p{page} : {new} événements")
            page += 1
    today = datetime.date.today()
    today = (today.year, today.month, today.day)
    for ev in events:
        start, end = event_dates(ev)
        ev["_dt"] = start
        ev["_dt_end"] = end or start
        # événement multi-jours en cours (début passé ou aujourd'hui) :
        # épinglé en tête du diaporama jusqu'à sa date de fin
        ev["pinned"] = bool(
            start and end and start[:3] != end[:3]
            and start[:3] <= today <= end[:3]
        )
    events.sort(key=lambda e: (
        0 if e["pinned"] else 1, e["_dt"] or (9999, 12, 31, 23, 59)))
    return events


def parse_detail(ev, series_map=None):
    """Complète un événement avec sa page détail : description, image HD,
    crédit, durée, couleur de bannière."""
    try:
        soup = BeautifulSoup(get(ev["url"]).text, "lxml")
    except Exception as e:
        print(f"  ! détail KO {ev['url']} : {e}")
        return ev

    # vraie image de l'événement : bannière, sinon og:image / carte
    # UNIQUEMENT si elles pointent vers /media/ (le site renvoie sinon son
    # logo générique /build/.../share.png)
    img = soup.select_one("img.v-banner__picture")
    og = soup.select_one('meta[property="og:image"]')
    if img and img.get("src"):
        ev["image"] = urljoin(BASE, img["src"])
    elif og and "/media/" in og.get("content", ""):
        ev["image"] = og["content"]
    elif ev.get("card_img") and "/media/" in ev["card_img"]:
        ev["image"] = ev["card_img"]
    else:
        ev["image"] = None

    # la couleur de bannière l'emporte sur celle de la card si définie
    banner = soup.select_one(".v-banner")
    color = _color_from_classes(banner.get("class") if banner else [], "v-banner")
    if color:
        ev["color"] = color

    cap = soup.select_one(".v-banner__caption")
    ev["credit"] = " ".join(cap.get_text().split()) if cap else ""

    intro = soup.select_one(".s-introduction:not(.s-introduction--long)") or soup.select_one(".s-introduction")
    if intro:
        for junk in intro.select("nav, .c-breadcrumb"):
            junk.decompose()
        ev["desc"] = " ".join(intro.get_text(" ").split())

    # description détaillée : intervenants (noms en <strong>) et animateur
    intro_long = soup.select_one(".s-introduction--long")
    if intro_long:
        for junk in intro_long.select("nav, .c-breadcrumb"):
            junk.decompose()
        ev["desc_long"] = "\n".join(
            ln for ln in (
                " ".join(p.get_text(" ").split())
                for p in intro_long.select("p")
            ) if ln
        ) or " ".join(intro_long.get_text(" ").split())
        ev["speakers"], ev["moderator"] = _extract_people(
            intro_long, ev["title"], ev["desc_long"])
        ev["note"] = _extract_note(ev["desc_long"])
    else:
        ev["desc_long"] = ev.get("desc", "")
        ev["speakers"], ev["moderator"] = _extract_people(
            intro_long, ev["title"], ev["desc_long"])
        ev["note"] = _extract_note(ev["desc_long"])

    for spec in soup.select("p.v-banner__spec"):
        use = spec.select_one("use[href]")
        text = spec.select_one(".v-banner__text")
        if use and text:
            m = re.search(r"sprite-([a-z-]+)", use["href"])
            label = SPRITE_LABELS.get(m.group(1)) if m else None
            if label and label not in ev["specs"]:
                ev["specs"][label] = " ".join(text.get_text().split())

    # appartenance à une série : bloc richtext « En savoir plus » vers
    # /au-programme/<slug> ou <h2> au nom de la série (présent sur une
    # partie seulement des pages — mark_series complète via la page série)
    for slug, label in (series_map or SERIES).items():
        if soup.find("a", href=re.compile(rf"/{slug}\b")) or soup.find(
                lambda t: t.name == "h2"
                and label.lower() in t.get_text().lower()):
            ev["series"] = label
            break

    # bloc « Destiné à … / Accessibilité » : le site reflète les champs
    # OpenAgenda (publics / accessibility) — extraction directe, sans
    # requête supplémentaire
    aud = soup.select_one(".v-audience__intending .v-audience__tag")
    ev["audience"] = " ".join(aud.get_text(" ").split()) if aud else ""
    if ev["audience"]:
        ev["specs"]["Public"] = ev["audience"]
    ev["access_venue"] = [
        " ".join(li.get_text(" ").split())
        for li in soup.select(".v-audience__accessibility .v-audience__item")
        if li.get_text(strip=True)
    ]
    # mentions « actionnables » (LSF, audiodescription…) dans la
    # description : seules celles-ci montent en spec sur la diapo — le
    # reste reste éditable dans la webui
    ev["access"] = _extract_access(ev.get("desc_long") or "")
    if ev["access"]:
        ev["specs"]["Accessibilité"] = ev["access"].replace("\n", " · ")
    return ev


# mentions d'accessibilité « actionnables » repérables dans la
# description (pas de champ dédié côté OpenAgenda : texte libre des
# programmateurs). Chaque motif produit un libellé normalisé affichable
# sur une diapo ; les handicaps pris en compte sur place restent dans
# access_venue (référence webui, pas de spec diapo).
_ACCESS_PATTERNS = [
    (re.compile(r"interpr[ée]t\w*\s+en\s+LSF|langue des signes", re.I),
     "Interprétation en LSF"),
    (re.compile(r"audiodescri\w*|audio-description", re.I),
     "Audiodescription"),
    (re.compile(r"surtitr", re.I), "Surtitrage"),
    (re.compile(r"boucle magn[ée]tique|collier magn[ée]tique"
               r"|casque d'amplification", re.I),
     "Dispositifs d'écoute amplifiée"),
]


def _extract_access(text):
    """Mentions d'accessibilité trouvées dans la description détaillée,
    une par ligne, dédupliquées."""
    out = []
    for pat, label in _ACCESS_PATTERNS:
        if pat.search(text) and label not in out:
            out.append(label)
    return "\n".join(out)


def mark_series(events, series_map=None):
    """Marque ev['series'] d'après les pages séries du site — source
    exhaustive (toutes les pages détail ne portent pas le bloc série)."""
    for slug, label in (series_map or SERIES).items():
        try:
            html_text = get(f"{BASE}/au-programme/{slug}").text
        except Exception:
            # normal : les clés peuvent être des keywords OpenAgenda
            # sans page correspondante sur le site
            continue
        ids = set(re.findall(r"/au-programme/[^\"'<>]+/(\d+)", html_text))
        for ev in events:
            m = re.search(r"/(\d+)/?$", ev.get("url") or "")
            if m and m.group(1) in ids:
                ev["series"] = label


# ——— extraction best-effort des intervenants / animateurs ———
# Les rédacteurs ont une certaine liberté ; les noms sont *souvent* en
# <strong> suivis de leur qualité, l'animateur signalé par « animé par ».
# Des replis existent (« X est qualité » dans le texte, « avec X » dans le
# titre). La webui permet de corriger avant génération de la diapo du jour.

_NAME = r"[A-ZÀ-Ý][\wÀ-ÿ'’\-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’\-]+){1,4}"

# coupe une qualité aux frontières narratives / mentions annexes
_QUALITY_CUT = re.compile(
    r"(?:\.(?=\s|$)"
    r"|\s+et\s+anim[ée]e?|\s+anim[ée]e?\s+par|\s+En lien|\s+En partenariat"
    r"|\s+Rencontre|\s+Suivie|\s+Dans le cadre|\s+Production\b"
    r"|\s+Auteurs?\b|\s+mise en scène|\s+dont\b"
    r"|,\s+(?:racontent|retrace|revient|explique|présente|analyse|interroge"
    r"|détaille|propose|débat|explore|explorent|décrypte|décryptent|imprime"
    r"|impriment|emmène|plonge|interprète|nous|ils|il)\b).*", re.S)

# la qualité commence directement par un verbe narratif → pas une qualité
_LEADING_VERB = re.compile(
    r"^(?:imprime|impriment|explore|explorent|retrace|retracent|décrypte"
    r"|décryptent|revient|reviennent|ensemble|nous|ils|il)\b")


def _clean_quality(t):
    t = " ".join(t.split())
    t = re.sub(r"^(?:est\s+|,\s*|:\s*)", "", t)
    t = _QUALITY_CUT.sub("", t)
    t = t.strip(" ,.;:")
    t = re.sub(r"\s+et$", "", t).strip()
    return "" if _LEADING_VERB.match(t) else t


def _is_name(s):
    return (
        3 <= len(s) <= 60 and ":" not in s and s[0].isupper()
        and len(s.split()) >= 2
    )


def _extract_people(intro_long, title, text):
    speakers, seen = [], set()

    def add(name, quality=""):
        name = name.strip(" ,.;:")
        if _is_name(name) and name not in seen:
            seen.add(name)
            speakers.append({"name": name, "quality": quality[:220]})

    # noms en <strong>/<b> : la qualité est le texte jusqu'au suivant
    strongs = []
    for st in (intro_long.select("strong, b") if intro_long else []):
        name = " ".join(st.get_text().split())
        bits = []
        for sib in st.next_siblings:
            if getattr(sib, "name", None) in ("strong", "b", "br", "p"):
                break
            bits.append(sib.get_text() if hasattr(sib, "get_text") else str(sib))
        strongs.append((name, "".join(bits)))
    quals = [_clean_quality(q) for _, q in strongs]
    for i, q in enumerate(quals):
        if q in ("et", "&") and i + 1 < len(quals):
            quals[i] = quals[i + 1]  # « A et B, qualité commune »
        elif q.startswith("et "):
            # « A et l'historien B » : la qualité est partagée par la paire
            shared = re.sub(
                r"^(?:l['’]|le |la |les |un |une |des )", "",
                q[3:].strip())
            quals[i] = shared
            if i + 1 < len(quals):
                quals[i + 1] = shared
    for (name, _), q in zip(strongs, quals):
        add(name, q)

    # repli : « X est qualité » directement dans le texte
    if not speakers:
        for m in re.finditer(rf"({_NAME})\s+est\s+([^.;\n]{{4,180}})", text):
            add(m.group(1), _clean_quality(m.group(2)))

    # repli : « … avec X » dans le titre
    if not speakers:
        m = re.search(r"avec\s+(.{3,50})$", title, re.I)
        if m:
            for nm in re.split(r"\s+et\s+|,", m.group(1)):
                add(nm)

    moderator = ""
    for pat in (r"anim[ée]e?\s+par\s+(" + _NAME + ")",
                r"présentée?\s+par\s+(" + _NAME + ")"):
        m = re.search(pat, text)
        if m:
            moderator = m.group(1)
            break
    # l'animateur n'est pas un intervenant
    if moderator:
        speakers = [s for s in speakers if s["name"] != moderator]
    return speakers, moderator


# phrases de la description détaillée qui relèvent d'une mention de pied
# de diapo (partenaires, dédicace…) — elles doivent *commencer* le
# segment pour éviter les faux positifs du récit (« suivi », « cadre »
# sont fréquents en pleine phrase). Proposition préremplie du champ
# « notes » de la diapo du jour.
_NOTE_RE = re.compile(
    r"^(?:en partenariat|en lien avec|dans le cadre|suivi[ée]e?\b"
    r"|rencontre suivie|entrée libre|sur réservation|séance de dédicace"
    r"|une séance de dédicace|gratuit\b)", re.I)


def _extract_note(text):
    notes = []
    for ln in (text or "").split("\n"):
        ln = " ".join(ln.split()).strip(" ​")
        if not ln:
            continue
        # retire le bout « animée par … » déjà affiché à part
        ln = re.sub(r"^.*?anim[ée]e?\s+par\s+" + _NAME, "", ln)
        for seg in re.split(r"(?<=[.!?])\s+", ln):
            seg = re.sub(r"^et\s+", "", seg.strip(" ,.;:"))
            if seg and _NOTE_RE.match(seg) and seg not in notes:
                notes.append(seg[0].upper() + seg[1:])
    return "\n".join(notes)
