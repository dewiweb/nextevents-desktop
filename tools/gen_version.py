"""Injecte la version du tag de release dans le build.

Usage : python tools/gen_version.py v0.5.0-beta.12
  → nextevents/version.py : repli embarqué = "0.5.0-beta.12" — le
    fichier est *patché* en place (VERSION = _git_version() or "dev"
    → « or "0.5.0-beta.12" ») : le module versionné garde toutes ses
    fonctions, aucune version dupliquée à maintenir ici
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


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "dev"
    v = tag.lstrip("v")
    nums = re.findall(r"\d+", v)
    nums = (nums + ["0"] * 4)[:4]
    dotted = ".".join(nums)

    vp = ROOT / "nextevents" / "version.py"
    src = vp.read_text(encoding="utf-8")
    # repli embarqué : `or "dev"` → `or "<tag>"` (une seule occurrence)
    patched, n = re.subn(r'or "dev"', f'or "{v}"', src, count=1)
    if n != 1:
        sys.exit('version.py : marqueur \'or "dev"\' introuvable')
    vp.write_text(patched, encoding="utf-8")

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
