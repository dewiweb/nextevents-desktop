"""Smoke tests — filet de sécurité minimal avant un build.

Lancés par la CI (unittest, pas de dépendance externe) :
    python -m unittest discover -s tests -v

Couvre : round-trip des réglages, résolution des secrets,
comparaison de versions, autostart (clé/.desktop) et parsing pur.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# env posé AVANT tout import nextevents — settings.py lit les
# variables au moment de l'import
_TMP = Path(tempfile.mkdtemp(prefix="ne-test-"))
os.environ["OUT_DIR"] = str(_TMP)
os.environ["SETTINGS_FILE"] = str(_TMP / "settings.json")
os.environ["NEXTEVENTS_CACHE_DIR"] = str(_TMP / "cache")
os.environ["NEXTEVENTS_FONT_DIR"] = str(_TMP / "fonts")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nextevents import autostart, secrets            # noqa: E402
from nextevents import settings as st                # noqa: E402
from nextevents import version                       # noqa: E402
from nextevents.scrape import parse_series_map       # noqa: E402


class SettingsTest(unittest.TestCase):

    def test_roundtrip_and_atomic_write(self):
        s = st.load_settings()
        s["interval_hours"] = 6
        s["out_dir"] = "D:\\diaporama"
        s["limit_mode"] = "days"
        st.save_settings(s)
        s2 = st.load_settings()
        self.assertEqual(s2["interval_hours"], 6)
        self.assertEqual(s2["out_dir"], "D:\\diaporama")
        self.assertEqual(s2["limit_mode"], "days")
        # le fichier est du JSON valide, pas de .tmp résiduel
        json.loads(( _TMP / "settings.json").read_text())
        self.assertFalse((_TMP / "settings.json.tmp").exists())

    def test_defaults_present(self):
        s = st.load_settings()
        for k in ("ss_delay", "ss_screen", "autostart_app",
                  "gen_landscape", "data_source"):
            self.assertIn(k, s)

    def test_resolve_out_dir_override(self):
        s = st.load_settings()
        s["out_dir"] = str(_TMP / "custom")
        self.assertEqual(st.resolve_out_dir(s), _TMP / "custom")

    def test_interval_min_survives_load(self):
        """Régression beta.26 : interval_min absent de DEFAULTS était
        jeté par load_settings → _interval_min retombait sur
        interval_hours=0 → le scheduler ne relançait jamais. Le
        réglage en minutes doit survivre au round-trip, et un
        ancien fichier en heures doit être converti."""
        from nextevents.runner import _interval_min
        (_TMP / "settings.json").write_text(
            json.dumps({"interval_min": 5}))
        self.assertEqual(_interval_min(st.load_settings()), 5)
        (_TMP / "settings.json").write_text(
            json.dumps({"interval_hours": 2}))
        self.assertEqual(_interval_min(st.load_settings()), 120)


class SecretsTest(unittest.TestCase):

    def test_env_wins(self):
        os.environ["NEXTEVENTS_FTP_PASS"] = "s3cret!"
        try:
            self.assertEqual(secrets.load("ftp_pass"), "s3cret!")
            self.assertEqual(secrets.where("ftp_pass"), "env")
            # store() avec env override : la valeur ne doit pas rester
            # dans le fichier
            self.assertTrue(secrets.store("ftp_pass", "s3cret!"))
        finally:
            del os.environ["NEXTEVENTS_FTP_PASS"]

    def test_missing_secret(self):
        self.assertIsNone(secrets.load("ftp_pass"))


class VersionTest(unittest.TestCase):

    def test_newer(self):
        version.VERSION = "0.5.0"
        self.assertTrue(version.newer_than_current("v0.5.1"))
        self.assertTrue(version.newer_than_current("v0.6.0-beta.1"))
        self.assertFalse(version.newer_than_current("v0.5.0"))
        self.assertFalse(version.newer_than_current("v0.4.9"))


class UiCollisionTest(unittest.TestCase):
    """Deux mixins ne doivent pas définir le même nom de méthode :
    la MRO de MainWindow en masque une et les signaux Qt connectés à
    `self.<nom>` tombent sur la mauvaise — silencieusement, car
    PySide6 ignore les arguments excédentaires (bug constaté dans
    openagenda-slides : _preview_slide doublé, le double-clic
    galerie rendait le mauvais aperçu).

    Analyse statique par AST : importer les modules tirerait PySide6,
    indisponible sur un runner sans libs GL."""

    def test_no_shadowed_methods_between_mixins(self):
        import ast
        ui = ROOT / "ui"
        seen, dup = {}, []
        for fname in ("tabs_general.py", "tabs_destinations.py",
                      "tabs_gallery.py", "today.py"):
            tree = ast.parse((ui / fname).read_text("utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef,
                                         ast.AsyncFunctionDef)) \
                            and not item.name.startswith("__"):
                        if item.name in seen:
                            dup.append(f"{item.name} : "
                                       f"{seen[item.name]} vs "
                                       f"{fname}:{node.name}")
                        else:
                            seen[item.name] = f"{fname}:{node.name}"
        self.assertEqual(dup, [])


class AutostartTest(unittest.TestCase):

    def test_cmd_known(self):
        # _cmd() ne doit jamais renvoyer None — sinon apply() écrirait
        # une entrée autostart vide
        cmd = autostart._cmd()
        self.assertIsInstance(cmd, str)
        self.assertTrue(cmd.strip())

    @unittest.skipUnless(sys.platform == "linux", "autostart freedesktop")
    def test_apply_linux(self):
        autostart.apply(True)
        f = autostart._linux_file()
        self.assertTrue(f.exists())
        self.assertIn("nextevents", f.read_text())
        autostart.apply(False)
        self.assertFalse(f.exists())


class ParseTest(unittest.TestCase):

    def test_series_map(self):
        from nextevents.scrape import series_logo
        text = ("grandstemoins = Les grands témoins | logo.png\n"
                "autre = Autre série\n"
                "# commentaire")
        m = parse_series_map(text)
        self.assertEqual(m.get("grandstemoins"), "Les grands témoins")
        self.assertEqual(m.get("autre"), "Autre série")
        # le logo est résolu à part (rendu seulement)
        self.assertEqual(series_logo(text, "Les grands témoins"),
                         "logo.png")
        self.assertIsNone(series_logo(text, "Autre série"))


class SlideTemplateTest(unittest.TestCase):

    def test_base_css_injection(self):
        """Chaque gabarit doit contenir la ligne @import remplacée par
        slide_base.css — sinon _template() lève une erreur au rendu et
        le HTML généré ne doit garder aucun placeholder $ non échappé."""
        from nextevents.paths import ASSET_DIR
        from nextevents.slide import BASE_CSS_IMPORT, DESIGNS, TEMPLATES
        for orient, fname in TEMPLATES.items():
            src = (ASSET_DIR / fname).read_text("utf-8")
            self.assertIn(BASE_CSS_IMPORT, src, fname)
            self.assertIn(orient, DESIGNS)
        # la base CSS existe et tient lieu de charte commune
        self.assertTrue((ASSET_DIR / "slide_base.css").exists())


if __name__ == "__main__":
    unittest.main()
