"""Rendu des diapos : template HTML (assets/slide_template.html) puis
capture Playwright/Chromium (repli firefox --headless)."""

import html
import io
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from string import Template

from PIL import Image

from .browser import launch_browser
from .paths import ASSET_DIR
from .scrape import CARD_COLORS, SPEC_ICONS, SPEC_ORDER

SIZES = {"hd": (1920, 1080), "uhd": (3840, 2160)}
DEFAULT_SIZE = SIZES["uhd"]

INK = "#141414"

ICONS = {
    "calendar": "M8 5.75c-.41 0-.75-.34-.75-.75V2c0-.41.34-.75.75-.75s.75.34.75.75v3c0 .41-.34.75-.75.75Zm8 0c-.41 0-.75-.34-.75-.75V2c0-.41.34-.75.75-.75s.75.34.75.75v3c0 .41-.34.75-.75.75Zm4.5 4.09h-17c-.41 0-.75-.34-.75-.75s.34-.75.75-.75h17c.41 0 .75.34.75.75s-.34.75-.75.75ZM16 22.75H8c-3.65 0-5.75-2.1-5.75-5.75V8.5c0-3.65 2.1-5.75 5.75-5.75h8c3.65 0 5.75 2.1 5.75 5.75V17c0 3.65-2.1 5.75-5.75 5.75ZM8 4.25c-2.86 0-4.25 1.39-4.25 4.25V17c0 2.86 1.39 4.25 4.25 4.25h8c2.86 0 4.25-1.39 4.25-4.25V8.5c0-2.86-1.39-4.25-4.25-4.25H8Z",
    "pin": "M12 14.17c-2.13 0-3.87-1.73-3.87-3.87S9.87 6.44 12 6.44s3.87 1.73 3.87 3.87-1.74 3.86-3.87 3.86Zm0-6.23c-1.3 0-2.37 1.06-2.37 2.37s1.06 2.37 2.37 2.37 2.37-1.06 2.37-2.37S13.3 7.94 12 7.94ZM12 22.76a5.97 5.97 0 0 1-4.13-1.67c-2.95-2.84-6.21-7.37-4.98-12.76C4 3.44 8.27 1.25 12 1.25h.01c3.73 0 8 2.19 9.11 7.09 1.22 5.39-2.04 9.91-4.99 12.75A5.97 5.97 0 0 1 12 22.76Zm0-20.01c-2.91 0-6.65 1.55-7.64 5.91C3.28 13.37 6.24 17.43 8.92 20a4.426 4.426 0 0 0 6.17 0c2.67-2.57 5.63-6.63 4.57-11.34-1-4.36-4.75-5.91-7.66-5.91Z",
    "ticket": "M17 20.75H7c-4.41 0-5.75-1.34-5.75-5.75v-.5c0-.41.34-.75.75-.75.96 0 1.75-.79 1.75-1.75S2.96 10.25 2 10.25c-.41 0-.75-.34-.75-.75V9c0-4.41 1.34-5.75 5.75-5.75h10c4.41 0 5.75 1.34 5.75 5.75v1c0 .41-.34.75-.75.75-.96 0-1.75.79-1.75 1.75s.79 1.75 1.75 1.75c.41 0 .75.34.75.75 0 4.41-1.34 5.75-5.75 5.75ZM2.75 15.16c.02 3.44.73 4.09 4.25 4.09h10c3.34 0 4.15-.59 4.24-3.59a3.25 3.25 0 0 1-2.49-3.16c0-1.53 1.07-2.82 2.5-3.16V9c0-3.57-.67-4.25-4.25-4.25H7c-3.52 0-4.23.65-4.25 4.09 1.43.34 2.5 1.63 2.5 3.16 0 1.53-1.07 2.82-2.5 3.16ZM10 7.25c-.41 0-.75-.34-.75-.75V4c0-.41.34-.75.75-.75s.75.34.75.75v2.5c0 .41-.34.75-.75.75Zm0 7.33c-.41 0-.75-.34-.75-.75v-3.67c0-.41.34-.75.75-.75s.75.34.75.75v3.67c0 .42-.34.75-.75.75Zm0 6.17c-.41 0-.75-.34-.75-.75v-2.5c0-.41.34-.75.75-.75s.75.34.75.75V20c0 .41-.34.75-.75.75Z",
    # sprite-timer du site (« Durée : … » sur les fiches événement)
    "timer": "M12 22.75c-5.24 0-9.5-4.26-9.5-9.5s4.26-9.5 9.5-9.5 9.5 4.26 9.5 9.5-4.26 9.5-9.5 9.5Zm0-17.5c-4.41 0-8 3.59-8 8s3.59 8 8 8 8-3.59 8-8-3.59-8-8-8ZM12 13.75c-.41 0-.75-.34-.75-.75V8c0-.41.34-.75.75-.75s.75.34.75.75v5c0 .41-.34.75-.75.75Zm3-11H9c-.41 0-.75-.34-.75-.75s.34-.75.75-.75h6c.41 0 .75.34.75.75s-.34.75-.75.75Z",
    # sprite-group du site (public visé)
    "group": "M16.5 7.25h-.119c-1.732-.054-3.025-1.392-3.025-3.042a3.057 3.057 0 0 1 3.053-3.053 3.063 3.063 0 0 1 3.052 3.053A3.05 3.05 0 0 1 16.51 7.26c0-.01 0-.01-.01-.01Zm-.091-4.73a1.678 1.678 0 0 0-.064 3.356c.009-.01.082-.01.165 0a1.68 1.68 0 0 0-.101-3.355Zm.1 11.487a6.05 6.05 0 0 1-1.072-.092.687.687 0 1 1 .238-1.357c1.128.193 2.32-.018 3.117-.55.431-.284.66-.641.66-.999 0-.357-.238-.706-.66-.99-.797-.531-2.007-.742-3.144-.54a.68.68 0 0 1-.798-.56.688.688 0 0 1 .56-.797c1.494-.266 3.043.018 4.143.751.807.541 1.274 1.311 1.274 2.136 0 .816-.458 1.595-1.274 2.145-.834.55-1.916.853-3.043.853ZM5.474 7.25h-.018a3.047 3.047 0 0 1-2.952-3.043 3.065 3.065 0 0 1 3.052-3.062 3.063 3.063 0 0 1 3.053 3.052 3.035 3.035 0 0 1-2.943 3.053l-.192-.688.064.688h-.064Zm.092-1.375c.055 0 .1 0 .155.009.816-.037 1.531-.77 1.531-1.677a1.678 1.678 0 1 0-1.769 1.677c.01-.01.046-.01.083-.01Zm-.102 8.13c-1.127 0-2.209-.302-3.043-.852-.807-.54-1.274-1.32-1.274-2.145 0-.816.467-1.595 1.274-2.136 1.1-.733 2.65-1.017 4.143-.751a.688.688 0 0 1 .56.797.68.68 0 0 1-.798.56c-1.137-.202-2.337.009-3.144.54-.431.284-.66.633-.66.99 0 .358.238.715.66 1 .797.531 1.989.742 3.117.55a.688.688 0 1 1 .238 1.357 6.05 6.05 0 0 1-1.073.09Zm5.537.092h-.119c-1.732-.055-3.025-1.393-3.025-3.043a3.057 3.057 0 0 1 3.053-3.053 3.063 3.063 0 0 1 3.052 3.053 3.05 3.05 0 0 1-2.952 3.053c0-.01 0-.01-.009-.01Zm-.091-4.73a1.678 1.678 0 0 0-.065 3.355c.01-.009.083-.009.166 0a1.68 1.68 0 0 0 1.585-1.677c0-.917-.751-1.678-1.686-1.678Zm.09 11.495c-1.1 0-2.2-.284-3.052-.861-.807-.541-1.274-1.311-1.274-2.136 0-.816.458-1.604 1.274-2.145 1.714-1.137 4.4-1.137 6.105 0 .807.54 1.274 1.31 1.274 2.136 0 .816-.458 1.604-1.274 2.145-.853.568-1.953.861-3.053.861Zm-2.291-3.987c-.431.284-.66.641-.66.999 0 .357.238.706.66.99 1.237.834 3.336.834 4.574 0 .43-.284.66-.642.66-1 0-.357-.238-.705-.66-.99-1.228-.833-3.328-.824-4.574 0Z",
    # sprite-accessibility du site (pictogramme accessibilité)
    "accessibility": "M8.786 11.192v3.724l-3.981 4.485a2.49 2.49 0 0 0 3.726 3.307L12 18.799l3.47 3.909a2.49 2.49 0 0 0 3.725-3.307l-3.98-4.485v-3.724h3.995a2.29 2.29 0 0 0 0-4.58H4.79a2.29 2.29 0 1 0 0 4.58h3.996Zm1.5 3.914v-4.414a1 1 0 0 0-1-1H4.79a.79.79 0 0 1 0-1.58h14.42a.79.79 0 0 1 0 1.58h-4.496a1 1 0 0 0-1 1v4.414a1 1 0 0 0 .252.664l4.107 4.627a.99.99 0 1 1-1.482 1.315l-3.843-4.33a1 1 0 0 0-1.496 0l-3.843 4.33a.99.99 0 1 1-1.482-1.315l4.107-4.627a1 1 0 0 0 .252-.664ZM12 4.833A1.167 1.167 0 1 0 12 2.5a1.167 1.167 0 0 0 0 2.333Zm0 1.5A2.667 2.667 0 1 0 12 1a2.667 2.667 0 0 0 0 5.333Z",
}
ICON_VIEWBOX = {"group": "0 0 22 22"}
ICON_PATH_ATTRS = {"accessibility": ' fill-rule="evenodd" clip-rule="evenodd"'}

# gabarit de conception par orientation : le HTML est dessiné pour ces
# dimensions, le PNG final est mis à l'échelle via device_scale_factor.
# Deux déclinaisons portrait : A4 (1:√2, pensée pour l'impression) et
# écran (9:16, pour un écran 16:9 monté en vertical).
DESIGNS = {
    "landscape": (1920, 1080),
    "portrait": (1240, 1754),
    "portrait-screen": (1080, 1920),
}
TEMPLATES = {
    "landscape": "slide_template.html",
    "portrait": "slide_template_portrait.html",
    "portrait-screen": "slide_template_portrait_screen.html",
}
_TEMPLATES = {}
_BASE_CSS = None


# Les gabarits assets/slide_template*.html partagent leur charte via
# assets/slide_base.css : la ligne `@import "slide_base.css";` du gabarit
# est remplacée par le contenu du fichier au chargement (le HTML produit
# reste autonome — tout est en ligne pour le navigateur de rendu).
BASE_CSS_IMPORT = '@import "slide_base.css";'


def _base_css():
    global _BASE_CSS
    if _BASE_CSS is None:
        _BASE_CSS = (ASSET_DIR / "slide_base.css").read_text("utf-8")
    return _BASE_CSS


def portrait_size(size, fmt="a4"):
    """Dimensions de sortie portrait pour une taille paysage `size` :
    « a4 » suit le ratio 1:√2 à la même densité que le paysage
    (HD → 1240×1754 ≈ 150 dpi, UHD → 2480×3508 ≈ 300 dpi) ;
    « screen » est l'écran pivoté (HD → 1080×1920, UHD → 2160×3840)."""
    if fmt == "screen":
        return (size[1], size[0])
    scale = size[0] / DESIGNS["landscape"][0]
    return tuple(round(d * scale) for d in DESIGNS["portrait"])


def portrait_key(fmt="a4"):
    """Clé d'orientation (DESIGNS/TEMPLATES) pour un format portrait."""
    return "portrait-screen" if fmt == "screen" else "portrait"


def _template(orientation="landscape"):
    if orientation not in _TEMPLATES:
        src = (ASSET_DIR / TEMPLATES[orientation]).read_text(encoding="utf-8")
        if BASE_CSS_IMPORT not in src:
            raise RuntimeError(
                f"{TEMPLATES[orientation]} : ligne {BASE_CSS_IMPORT!r} "
                "introuvable — la charte commune n'est pas injectée")
        _TEMPLATES[orientation] = Template(
            src.replace(BASE_CSS_IMPORT, _base_css()))
    return _TEMPLATES[orientation]


def icon_svg(name):
    path = ICONS.get(name, ICONS["calendar"])
    vb = ICON_VIEWBOX.get(name, "0 0 24 24")
    attrs = ICON_PATH_ATTRS.get(name, "")
    return (
        f'<svg viewBox="{vb}" width="42" height="42" '
        f'aria-hidden="true"><path{attrs} d="{path}" '
        f'fill="currentColor"/></svg>'
    )


def _md_inline(text):
    """Markdown-lite → HTML inline pour le rendu : échappé d'abord,
    puis **gras** → <b>, *italique* → <em>, [lien](url) → libellé
    souligné, «## titre» → <b>. Tronquer AVANT (jamais au milieu
    d'une balise)."""
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__(.+?)__", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<em>\1</em>", t)
    t = re.sub(r"\[(.+?)\]\([^)]*\)", r"<u>\1</u>", t)
    t = re.sub(r"^#+\s*(.+?)$", r"<b>\1</b>", t, flags=re.M)
    return t.replace("\n", "<br>")


# fins de phrase acceptées pour les coupures — le site joint les
# paragraphes de desc_long par « \n » : sans les variantes \n la
# plupart des fins de phrase réelles seraient ratées (coupe au mot)
_SENT_END = (". ", "! ", "? ", "… ", ".\n", "!\n", "?\n", "…\n", "\n")


def truncate(text, limit=400):
    """Coupe à la dernière fin de phrase présente dans la fenêtre,
    sinon au dernier mot complet + « … » — jamais au milieu d'un
    mot, et pas au milieu d'une phrase si une fin de phrase existe
    avant la borne (repli mot = première phrase plus longue que la
    limite, cas sans alternative)."""
    if len(text) <= limit:
        return text
    w = text[:limit]
    # max sur les séparateurs = la fin de phrase la plus tardive,
    # quelle que soit la ponctuation — pas de seuil : une phrase
    # terminée tôt dans la fenêtre vaut mieux qu'une coupe en plein
    # milieu (surtout aux petites limites)
    i = max(w.rfind(s) for s in _SENT_END)
    if i > 0:
        return w[:i].rstrip(".,;:!?\n") + "…"
    cut = w.rsplit(maxsplit=1)
    return (cut[0] if len(cut) > 1 else w).rstrip(".,;:!?") + "…"


def asset_svg(name):
    p = ASSET_DIR / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


# métriques de la colonne texte par gabarit — dérivées des :root et
# règles de assets/slide_template*.html, mesurées au rendu (chromium) :
# hauteur/largeur utiles de la colonne, hauteurs de ligne titre/
# description, hauteur d'une ligne de specs (normale/compacte).
# Elles servent à borner la description à ce qui tient réellement :
# sinon c'est -webkit-line-clamp qui tranche, en plein mot, ou le
# flex qui rogne une ligne en hauteur.
_LAYOUT = {
    "landscape": dict(col_h=892, title_w=942, h1_max=4,
                      desc_lh=34 * 1.38, desc_mt=36, desc_max=6,
                      desc_cpl=46, spec_row=50, spec_row_t=47,
                      spec_gap=26, spec_gap_t=16, spec_pad=0),
    "portrait": dict(col_h=842, title_w=1114, h1_max=5,
                     desc_lh=32 * 1.4, desc_mt=28, desc_max=7,
                     desc_cpl=63, spec_row=47, spec_row_t=45,
                     spec_gap=20, spec_gap_t=15, spec_pad=64),
    "portrait-screen": dict(col_h=922, title_w=972, h1_max=6,
                            desc_lh=32 * 1.45, desc_mt=30, desc_max=9,
                            desc_cpl=55, spec_row=45, spec_row_t=42,
                            spec_gap=18, spec_gap_t=14, spec_pad=64),
}
# largeur moyenne d'un glyphe de titre / description, en fraction de
# la taille de fonte — mesurée (~0,5 em) puis majorée : surestimer
# les lignes du titre protège la description, jamais l'inverse
_TITLE_CHAR_W = 0.55


def _desc_lines(orientation, n_title, h1_size, n_specs):
    """Nombre de lignes de description réellement disponibles sur la
    diapo : hauteur de la colonne moins le titre estimé (borné par
    son clamp) et le bloc specs. ≥ 1 — le flex CSS garde le dernier
    mot en cas d'estimation trop optimiste."""
    lay = _LAYOUT[orientation]
    t_lines = min(
        lay["h1_max"],
        max(1, math.ceil(n_title * h1_size * _TITLE_CHAR_W
                         / lay["title_w"])))
    tight = n_specs >= 4
    specs_h = (n_specs * (lay["spec_row_t"] if tight else lay["spec_row"])
               + max(0, n_specs - 1)
               * (lay["spec_gap_t"] if tight else lay["spec_gap"])
               + (lay["spec_pad"] if n_specs else 0))
    avail = (lay["col_h"] - t_lines * h1_size * 1.06
             - lay["desc_mt"] - specs_h - 8)
    return max(1, min(lay["desc_max"], int(avail // lay["desc_lh"])))


def _desc_html(ev, mode, limit, orientation="landscape",
               max_lines=None):
    """Texte de la description selon le réglage desc_mode : « chapeau »
    (texte court), « long » (description détaillée — le clamp CSS
    borne l'affichage), « auto » (markdown/long si présent, chapeau
    sinon — comportement historique). `max_lines` borne aussi au
    nombre de lignes calculé pour la diapo (_desc_lines)."""
    if mode == "chapeau":
        src = ev.get("desc") or ""
    elif mode == "long":
        # desc_long d'abord : desc_md est le *chapeau* markdown OA,
        # pas la description détaillée — il masquerait desc_long
        src = (ev.get("desc_long") or ev.get("desc_md")
               or ev.get("desc") or "")
    else:
        src = ev.get("desc_md") or ev.get("desc") or ""
    # toujours tronquer côté texte, plafonné à la capacité du gabarit :
    # sinon le clamp CSS prend le relais et coupe au milieu d'un mot —
    # 400 car. ≈ ce que la zone affiche quand la limite est à 0
    lay = _LAYOUT.get(orientation)
    cap = limit or 400
    if lay:
        cpl = lay["desc_cpl"]
        cap = min(cap, cpl * (max_lines or lay["desc_max"]))
    if mode != "chapeau" and len(src) > cap:
        # première phrase plus longue que la borne : la troncature
        # tomberait en plein milieu — retomber sur le chapeau, pensé
        # pour tenir dans la zone
        end = max(src.find(s) for s in _SENT_END)
        if end < 0 or end + 2 > cap:
            src = ev.get("desc") or src
    txt = truncate(src, cap)
    if lay and max_lines and "\n" in txt:
        # un « \n » rendu en <br> consomme aussi une ligne du clamp
        # sans que la borne en caractères le sache — resserrer tant
        # que le texte ne rentre pas dans les lignes prévues
        def used(t):
            return sum(max(1, math.ceil(len(s) / cpl))
                       for s in t.split("\n"))
        while used(txt) > max_lines and len(txt) > 40:
            txt = truncate(src, int(len(txt) * 0.85))
    return _md_inline(txt)


def slide_html(ev, idx, fonts, orientation="landscape",
               desc_mode="auto", desc_max=400):
    portrait = orientation.startswith("portrait")
    bg, dark = CARD_COLORS.get(ev.get("color"), CARD_COLORS[None])
    tag = ev.get("tag") or ev["specs"].get("Catégorie") or "Événement"
    # les temps forts se déroulent à plusieurs endroits du bâtiment :
    # leur « lieu » (Hall) est trompeur — on ne l'affiche pas
    keys = [k for k in SPEC_ORDER if k in ev["specs"]
            and not (k == "Lieu" and tag == "Temps fort")]
    specs_html = "".join(
        f'<div class="spec">{icon_svg(SPEC_ICONS[k])}'
        f'<span>{html.escape(ev["specs"][k])}</span></div>'
        for k in keys
    )
    n_title = len(ev["title"])
    if portrait:
        if orientation == "portrait-screen":
            h1_size = 70 if n_title < 50 else 57 if n_title < 80 else 46
        else:
            h1_size = 76 if n_title < 50 else 62 if n_title < 80 else 50
    else:
        h1_size = 80 if n_title < 50 else 64 if n_title < 80 else 52
    specs_cls = "specs specs--tight" if len(keys) >= 4 else "specs"

    # lignes de description réellement disponibles : la colonne est
    # partagée entre titre, description et specs — la borne texte
    # (caractères) et le clamp CSS (lignes) restent alignés, sinon
    # l'un coupe en plein mot là où l'autre a déjà posé « … »
    d_lines = _desc_lines(orientation, n_title, h1_size, len(keys))

    credit = html.escape(ev.get("credit", ""))
    if ev.get("img_data"):
        media = (
            f'<img class="photo" src="{ev["img_data"]}" alt="">'
            + (f'<div class="credit">{credit}</div>' if credit else "")
        )
    else:
        # impression A4 : inversion du bloc foncé (encre) — fond blanc,
        # cercles clairs ; les autres formats gardent le bloc foncé
        # à cercles blancs
        if orientation == "portrait":
            ph_bg, ph_c1, ph_c2, ph_o1, ph_o2 = "#fff", bg, dark, ".6", ".3"
        else:
            ph_bg, ph_c1, ph_c2, ph_o1, ph_o2 = dark, "#fff", dark, ".42", ".55"
        media = f"""<div class="photo photo--empty" style="background:{ph_bg}">
<svg viewBox="0 0 780 970" preserveAspectRatio="xMidYMid slice">
 <g fill="none" stroke="{ph_c1}" stroke-width="86" opacity="{ph_o1}">
  <circle cx="-60" cy="1030" r="340"/><circle cx="-60" cy="1030" r="560"/>
  <circle cx="-60" cy="1030" r="780"/>
 </g>
 <g fill="none" stroke="{ph_c2}" stroke-width="60" opacity="{ph_o2}">
  <circle cx="850" cy="-40" r="260"/><circle cx="850" cy="-40" r="440"/>
 </g>
</svg>
<div class="ph-logo">{asset_svg('logo-full.svg')}</div></div>"""

    return _template(orientation).substitute(
        font_regular=fonts["regular"],
        font_medium=fonts["medium"],
        ink=INK,
        bg=bg,
        dark=dark,
        media=media,
        tag=html.escape(tag),
        h1_size=h1_size,
        title=html.escape(ev["title"]),
        # desc_md : markdown interprété (gras/italique) ; desc plat en
        # repli (chemin site — pas de markdown de toute façon)
        desc=_desc_html(ev, desc_mode, desc_max, orientation, d_lines),
        desc_lines=d_lines,
        specs_cls=specs_cls,
        specs_html=specs_html,
        logo_mark=asset_svg("logo-mark.svg"),
    )


def slugify(text, maxlen=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower())
    s = re.sub(r"['’]", "", s).strip("-")
    return s[:maxlen].strip("-") or "event"


def slide_name(ev, idx):
    """Nom stable dérivé de la date + titre : l'ordre alphabétique suit la
    chronologie et un événement garde son nom entre deux générations."""
    dt = ev.get("_dt")
    if dt:
        # _dt (a, m, j, h, min) : fiable quel que soit le format
        # d'affichage de la spec Date (date_format ≠ compact retire
        # le motif JJ/MM/AA du libellé — le nommage ne doit pas en
        # dépendre)
        prefix = f"{dt[0]:04d}-{dt[1]:02d}-{dt[2]:02d}"
        if dt[3] or dt[4]:
            prefix += f"-{dt[3]:02d}h{dt[4]:02d}"
    else:
        d = ev["specs"].get("Date", "")
        m = re.search(r"(\d{2})/(\d{2})/(\d{2})", d)
        t = re.search(r"(\d{1,2})h(\d{2})?", d)
        prefix = (f"20{m.group(3)}-{m.group(2)}-{m.group(1)}"
                  if m else f"zz{idx:02d}")
        if t:
            prefix += f"-{int(t.group(1)):02d}h{t.group(2) or '00'}"
    if ev.get("pinned"):
        # événement multi-jours en cours : nom de fichier trié en tête
        # ('slide-00-' précède 'slide-20…' alphabétiquement)
        prefix = "00-" + prefix
    return f"slide-{prefix}-{slugify(ev['title'])}"


def render_png_firefox(html_path, png_path, size=DEFAULT_SIZE,
                       orientation="landscape"):
    """Repli : firefox --screenshot avec zoom + fenêtre aux dimensions
    voulues (le HTML est dessiné pour les dimensions DESIGNS du
    gabarit — zoom adapté au ratio réel)."""
    w, h = size
    dw, _ = DESIGNS[orientation]
    html_path = Path(html_path).resolve()
    png_path = Path(png_path)
    zoomed = html_path.with_suffix(".zoom.html")
    # body{background:#000} : --screenshot ne gère pas l'alpha —
    # sans ça les coins arrondis sortiraient blancs
    zoomed.write_text(
        html_path.read_text("utf-8").replace(
            "</head>",
            f"<style>html{{zoom:{w / dw}}}"
            "body{background:#000 !important}</style></head>",
        ),
        encoding="utf-8",
    )
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_out = Path(tmp.name)
    tmp_out.unlink()
    cmd = [
        "firefox", "--headless", f"--window-size={w},{h}",
        "--screenshot", str(tmp_out), zoomed.as_uri(),
    ]
    for _ in range(2):
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if tmp_out.exists() and tmp_out.stat().st_size > 0:
            break
    else:
        raise RuntimeError(f"firefox screenshot KO : {r.stderr.decode()[:400]}")
    img = Image.open(tmp_out).convert("RGB")
    img = img.resize(size) if img.size != size else img
    _save_atomic(img, png_path)
    tmp_out.unlink()
    zoomed.unlink()


def _save_atomic(img, path):
    """PNG écrit via fichier temporaire + rename : le diaporama ou la
    galerie ne peuvent pas lire un fichier à moitié écrit."""
    tmp = path.with_name(path.name + ".tmp")
    img.save(tmp, "PNG")
    os.replace(tmp, path)


def render_all(slides, size=DEFAULT_SIZE, orientation="landscape"):
    """Rend les diapos via Playwright/Chromium (viewport aux dimensions
    de conception + device_scale_factor → texte vectoriel ultra net).
    Repli Firefox si Playwright est absent."""
    w, h = size
    dw, dh = DESIGNS[orientation]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        for hp, pp in slides:
            try:
                render_png_firefox(hp, pp, size, orientation)
                yield pp
            except Exception as e:
                print(f"  ✗ {pp.name} : {e}")
        return

    with sync_playwright() as p:
        # retries partagés avec la sonde pré-flight (browser.launch_browser)
        browser = launch_browser(p)
        if browser is None:
            raise RuntimeError("impossible de lancer le navigateur de rendu")
        page = browser.new_page(
            viewport={"width": dw, "height": dh},
            device_scale_factor=w / dw,
        )
        for hp, pp in slides:
            try:
                page.goto(Path(hp).resolve().as_uri())
                page.wait_for_function("document.fonts.status === 'loaded'")
                # omit_background : le fond <body> transparent reste
                # transparent dans le PNG (coins arrondis de la carte)
                shot = page.screenshot(omit_background=True)
                img = Image.open(io.BytesIO(shot))
                if img.size != size:
                    img = img.resize(size, Image.LANCZOS)
                _save_atomic(img, pp)
                yield pp
            except Exception as e:
                print(f"  ✗ {pp.name} : {e}")
        browser.close()
