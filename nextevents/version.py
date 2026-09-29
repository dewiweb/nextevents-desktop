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
