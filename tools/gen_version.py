"""Génère les fichiers de version depuis le tag de release.

Usage : python tools/gen_version.py v0.5.0-beta.12
  → nextevents/version.py : VERSION = "0.5.0-beta.12"
  → version.txt : métadonnées exe Windows (filevers/FileVersion…)

Appelé par la CI avant le build PyInstaller — version.txt n'est plus
figé à la main.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "dev"
    v = tag.lstrip("v")
    nums = re.findall(r"\d+", v)
    nums = (nums + ["0"] * 4)[:4]
    dotted = ".".join(nums)

    (ROOT / "nextevents" / "version.py").write_text(
        '"""Version de l\'app — régénérée par la CI au moment du build\n'
        "(tools/gen_version.py). En dev, \"dev\".\"\"\"\n\n"
        f'VERSION = "{v}"\n\n\n'
        "def newer_than_current(tag):\n"
        '    """True si `tag` (ex. « v0.5.0-beta.12 ») est une version plus\n'
        "    récente que celle embarquée. Comparaison lexicale tolérante :\n"
        "    on découpe sur les séparateurs, numérique quand possible.\"\"\"\n"
        "    def key(v):\n"
        '        v = v.lstrip("v")\n'
        "        out = []\n"
        '        for part in v.replace("-", ".").split("."):\n'
        "            out.append(int(part) if part.isdigit() else part)\n"
        "        return out\n"
        "    try:\n"
        "        return key(tag) > key(VERSION)\n"
        "    except Exception:\n"
        '        return tag.lstrip("v") != VERSION\n',
        encoding="utf-8")

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
