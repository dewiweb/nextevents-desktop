"""Génère les fichiers de version depuis le tag de release.

Usage : python tools/gen_version.py v0.5.0-beta.12
  → nextevents/version.py : VERSION embarquée = "0.5.0-beta.12"
  → version.txt : métadonnées exe Windows (filevers/FileVersion…)

Appelé par la CI avant le build PyInstaller — version.txt n'est plus
figé à la main. En dev (checkout git), version.py résout la version
courante via `git describe` — la valeur embarquée n'est le repli que
pour les builds figés (pas de .git dans le bundle).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VERSION_PY = '''"""Version de l'app — régénérée par la CI au moment du build
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


VERSION = _git_version() or "{embedded}"


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
'''


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "dev"
    v = tag.lstrip("v")
    nums = re.findall(r"\d+", v)
    nums = (nums + ["0"] * 4)[:4]
    dotted = ".".join(nums)

    (ROOT / "nextevents" / "version.py").write_text(
        VERSION_PY.replace("{embedded}", v), encoding="utf-8")

    tpl = (ROOT / "version.txt").read_text(encoding="utf-8")
    tpl = re.sub(r"filevers=\([\d, ]+\)",
                 f"filevers=({', '.join(nums)})", tpl)
    tpl = re.sub(r"prodvers=\([\d, ]+\)",
                 f"prodvers=({', '.join(nums)})", tpl)
    tpl = re.sub(r"(FileVersion', ')[\d.]+'", rf"\g<1>{dotted}'", tpl)
    tpl = re.sub(r"(ProductVersion', ')[\d.]+'", rf"\g<1>{dotted}'", tpl)
    (ROOT / "version.txt").write_text(tpl, encoding="utf-8")
    print(f"version {v} -> nextevents/version.py + version.txt ({dotted})")


if __name__ == "__main__":
    main()
