"""Version de l'app — régénérée par la CI au moment du build
(tools/gen_version.py). En dev (checkout git), la version courante
est résolue par `git describe` ; la valeur embarquée ne sert que de
repli pour les builds figés."""


def _git_version():
    """Version réelle en dev : git describe sur le checkout. None si
    pas de .git (bundle PyInstaller) ou git indisponible."""
    try:
        import subprocess
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        if not (root / ".git").exists():
            return None
        out = subprocess.run(
            ["git", "describe", "--tags", "--always"], cwd=root,
            capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip().lstrip("v")
    except Exception:
        pass
    return None


VERSION = _git_version() or "dev"


def _key(v):
    """Clé de comparaison de version : découpe sur les séparateurs,
    numérique quand possible (v0.5.0-beta.30 → [0, 5, 0, 'beta', 30])."""
    out = []
    for part in v.lstrip("v").replace("-", ".").split("."):
        out.append(int(part) if part.isdigit() else part)
    return out


def newer_than_current(tag):
    """True si `tag` (ex. « v0.5.0-beta.12 ») est une version plus
    récente que celle embarquée. Comparaison lexicale tolérante."""
    try:
        return _key(tag) > _key(VERSION)
    except Exception:
        return tag.lstrip("v") != VERSION


def pick_newer(releases, beta=None):
    """Choisit la version la plus récente admissible dans une liste de
    releases GitHub (dicts de l'API). L'API ne les renvoie PAS triées
    par version — il faut comparer, pas prendre la première.

    `beta` : l'app courante est une préversion → elle voit les
    prereleases ; une stable ne voit que les stables. Une release est
    préversion si le flag `prerelease` est posé OU si son tag contient
    un tiret (vieilles betas publiées avant le flag CI).

    Renvoie (tag, url) — ("", "") si rien d'admissible."""
    if beta is None:
        beta = "-" in VERSION
    tag = url = ""
    best = None
    for r in (releases if isinstance(releases, list) else []):
        t = r.get("tag_name") or ""
        if not t or r.get("draft"):
            continue
        if ("-" in t or r.get("prerelease")) and not beta:
            continue
        try:
            k = _key(t)
            if best is None or k > best:
                best, tag, url = k, t, r.get("html_url") or ""
        except Exception:
            continue
    return tag, url
