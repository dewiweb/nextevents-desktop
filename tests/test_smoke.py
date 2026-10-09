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

    def test_pick_newer(self):
        """La liste /releases n'est pas triée par version — la
        sélection doit comparer. Une beta voit les prereleases (flag
        ou tiret dans le tag) ; une stable n'en voit aucune."""
        releases = [
            {"tag_name": "v0.5.0-beta.28", "prerelease": False,
             "html_url": "u28"},            # en tête mais plus vieille
            {"tag_name": "v0.5.0-beta.30", "prerelease": True,
             "html_url": "u30"},
            {"tag_name": "v0.5.0-beta.29", "prerelease": True,
             "html_url": "u29", "draft": True},   # draft : ignorée
        ]
        # beta → le max parmi toutes les releases, beta.30 en 2e position
        self.assertEqual(version.pick_newer(releases, beta=True),
                         ("v0.5.0-beta.30", "u30"))
        # stable → rien d'admissible : le tiret du tag classe beta.28
        # comme préversion même sans le flag prerelease
        self.assertEqual(version.pick_newer(releases, beta=False),
                         ("", ""))
        # avec une stable dans la liste, c'est elle qui sort
        releases.append({"tag_name": "v0.4.0", "prerelease": False,
                         "html_url": "u04"})
        self.assertEqual(version.pick_newer(releases, beta=False),
                         ("v0.4.0", "u04"))
        self.assertEqual(version.pick_newer("pas une liste"), ("", ""))


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


class SeriesFromSoupTest(unittest.TestCase):
    """Attribution de série : seuls les signaux propres à la page
    comptent — les cartes/h2 des sections voisines (« Les autres … »)
    sont exclus."""

    def _soup(self, frag):
        from bs4 import BeautifulSoup
        return BeautifulSoup(
            f"<html><body><main>{frag}</main></body></html>",
            "html.parser")

    TABLE = {"fete-de-la-science": "Fête de la science"}

    def test_neighbor_series_link_ignored(self):
        """Lien vers une série voisine depuis une carte v-event__link
        (sans c-button ni « En savoir plus ») → non capté."""
        from nextevents.scrape import series_from_soup
        soup = self._soup(
            '<div class="v-events__content">'
            '<a class="v-event__link" href="/au-programme/fete-de-la-science">'
            'Dans la même série</a></div>')
        self.assertIsNone(series_from_soup(soup, self.TABLE))

    def test_en_savoir_plus_button(self):
        from nextevents.scrape import series_from_soup
        soup = self._soup(
            '<a class="c-button" href="/au-programme/fete-de-la-science">'
            'En savoir plus</a>')
        self.assertEqual(series_from_soup(soup, self.TABLE),
                         "Fête de la science")

    def test_page_own_slug(self):
        """La page vit elle-même sur la page série (expo) : le slug de
        l'URL suffit."""
        from nextevents.scrape import series_from_soup
        soup = self._soup("<h1>Jardins d'hiver 2027</h1>")
        self.assertEqual(
            series_from_soup(
                soup, {"jardins-d-hiver": "Jardins d'hiver"},
                url="https://www.leschampslibres.fr"
                    "/au-programme/jardins-d-hiver"),
            "Jardins d'hiver")

    def test_richtext_h2(self):
        from nextevents.scrape import series_from_soup
        soup = self._soup(
            '<div class="s-richtext"><h2>Fête de la science</h2></div>')
        self.assertEqual(series_from_soup(soup, self.TABLE),
                         "Fête de la science")

    def test_neighbor_h2_excluded(self):
        """h2 hors .s-richtext (section « Les autres … ») → ignoré."""
        from nextevents.scrape import series_from_soup
        soup = self._soup(
            '<div class="v-events__content">'
            '<h2>Fête de la science</h2></div>')
        self.assertIsNone(series_from_soup(soup, self.TABLE))


class FileUriTest(unittest.TestCase):
    """_file_uri borne les images embarquées aux racines connues —
    pas de fichier arbitraire via « | /chemin » dans series_map."""

    def test_outside_roots_rejected(self):
        import tempfile
        from nextevents import today
        # la suite pose OUT_DIR sous /tmp — on borne les racines à un
        # sous-dossier pour que le temp file soit bien « dehors »
        orig_ro, orig_out = today.resolve_out_dir, today.OUT_DIR
        today.resolve_out_dir = lambda s=None: _TMP / "o" / "x"
        today.OUT_DIR = _TMP / "o"
        try:
            with tempfile.NamedTemporaryFile(suffix=".png") as f:
                self.assertIsNone(today._file_uri(f.name))
            self.assertIsNone(today._file_uri("/etc/passwd"))
        finally:
            today.resolve_out_dir, today.OUT_DIR = orig_ro, orig_out

    def test_asset_allowed(self):
        from nextevents.today import _file_uri
        from nextevents.paths import ASSET_DIR
        uri = _file_uri(str(ASSET_DIR / "check.svg"))
        self.assertTrue(
            uri.startswith("data:image/svg+xml;base64,"), uri)


class PreflightTest(unittest.TestCase):

    def test_defaults_pass(self):
        """Les réglages d'usine ne doivent produire ni blocage ni
        avertissement (sauf la sonde navigateur, qui dépend des
        binaires playwright présents sur la machine)."""
        from nextevents import preflight
        issues = [i for i in preflight.validate_settings(
            dict(st.DEFAULTS)) if "rendu" not in i.msg]
        self.assertEqual(issues, [])

    def test_no_format_blocks(self):
        """Paysage et portrait décochés = génération vide : blocker."""
        from nextevents import preflight
        issues = preflight.validate_settings(
            dict(st.DEFAULTS, gen_landscape=0, gen_portrait=0))
        self.assertTrue(any(i.level == "blocker" for i in issues))

    def test_incomplete_destinations_warn(self):
        """Un hôte sans identifiants/partage : warn, pas blocker —
        les diapos locales sont quand même produites."""
        from nextevents import preflight
        issues = preflight.validate_settings(
            dict(st.DEFAULTS, ftp_host="nas.local", ftp_user="",
                 ftp_pass="", smb_host="192.168.1.2", smb_share="",
                 local_dir="/n/existe/pas"))
        warns = [i for i in issues if i.level == "warn"]
        self.assertEqual(len(warns), 3)
        self.assertFalse(any(i.level == "blocker" for i in issues))

    def test_bad_sched_times_warn(self):
        """Un token d'heure fixe mal formé serait ignoré par
        _times_due en silence — le pré-flight le signale."""
        from nextevents import preflight
        issues = preflight.validate_settings(
            dict(st.DEFAULTS, sched_times="6h00, 18:30"))
        self.assertTrue(any("6h00" in i.msg for i in issues))


class WizardTest(unittest.TestCase):

    def test_presets_and_apply(self):
        """L'assistant pré-coche d'après les usages, saute la page
        Écran quand la diffusion n'est pas cochée, et écrit les mêmes
        clés que les onglets à l'acceptation."""
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtWidgets import QApplication
        except ImportError:
            self.skipTest("PySide6 indisponible")
        QApplication.instance() or QApplication([])
        from ui.wizard import FINAL, OUTPUT, SetupWizard
        w = SetupWizard()
        w.show()
        # usage impression seul : la page Écran (id 1) est sautée,
        # portrait coché en A4
        w.use_print.setChecked(True)
        w.next()
        self.assertEqual(w.currentId(), OUTPUT)
        self.assertTrue(w.gen_pt.isChecked())
        self.assertEqual(w.portrait_fmt.currentData(), "a4")
        self.assertFalse(w.gen_ls.isChecked())
        w.next()  # → Destinations
        w.next()  # → Résumé
        self.assertEqual(w.currentId(), FINAL)
        w.accept()
        s = st.load_settings()
        self.assertEqual(s["gen_portrait"], 1)
        self.assertEqual(s["portrait_format"], "a4")
        self.assertEqual(s["gen_landscape"], 0)
        self.assertTrue(w.generate_now)   # case cochée par défaut
        w.deleteLater()


class HelpDialogTest(unittest.TestCase):

    def test_topics_and_dialog(self):
        """Une rubrique par onglet + raccourcis ; le dialog s'ouvre
        sur la rubrique demandée (contextuel à l'onglet courant)."""
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtWidgets import QApplication
        except ImportError:
            self.skipTest("PySide6 indisponible")
        QApplication.instance() or QApplication([])
        from ui.help import TOPICS, HelpDialog
        self.assertEqual(len(TOPICS), 5)   # 4 onglets + raccourcis
        d = HelpDialog(None, topic=2)      # Diapo du jour
        self.assertEqual(d.picker.currentIndex(), 2)
        self.assertIn("auditorium", d.body.toPlainText())
        d.deleteLater()


class SpecsCheckboxesTest(unittest.TestCase):

    def test_empty_specs_show_checks_all(self):
        """Régression : specs_show="" (= toutes) doit cocher toutes les
        specs au chargement. "".split(",") renvoie [""] — sans filtrage
        des chaînes vides, `not shown` était faux et tout apparaissait
        décoché ; le save suivant n'écrivait que "Date"."""
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtWidgets import QApplication
        except ImportError:
            self.skipTest("PySide6 indisponible")
        st.save_settings(dict(st.DEFAULTS))   # specs_show = ""
        QApplication.instance() or QApplication([])
        from ui.window import MainWindow
        w = MainWindow(tray_ok=False, icon_path="nextevents.ico")
        self.assertTrue(
            all(cb.isChecked() for cb, _o in w._spec_rows.values()))
        w.deleteLater()


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
