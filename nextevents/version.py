"""Version de l'app — régénérée par la CI au moment du build
(tools/gen_version.py). En dev, "dev"."""

VERSION = "0.5.0-beta.12"


def newer_than_current(tag):
    """True si `tag` (ex. « v0.5.0-beta.12 ») est une version plus
    récente que celle embarquée. Comparaison lexicale tolérante :
    on découpe sur les séparateurs, numérique quand possible."""
    def key(v):
        v = v.lstrip("v")
        out = []
        for part in v.replace("-", ".").split("."):
            out.append(int(part) if part.isdigit() else part)
        return out
    try:
        return key(tag) > key(VERSION)
    except Exception:
        return tag.lstrip("v") != VERSION
