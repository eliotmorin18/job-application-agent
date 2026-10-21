"""
Tests des zones cliquables du PDF (marqueurs invisibles \\cvanchor et cv/layout.py).
CV fictifs dans des dossiers temporaires ; aucun appel à Claude. Les tests de compilation
sont ignorés si latexmk n'est pas installé.

Lancement :  python -m unittest discover tests
"""

import copy
import json
import os
import re
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from pypdf import PdfReader

from cv import build_cv
from cv.build_cv import TEMPLATE_DIR, compile_cv, write_cv
from cv.document import build_document
from cv.layout import LayoutError, read_layout, region_at, write_layout
from cv.render import render_sections
from cv_fixtures import example_profile, fake_draft


HAS_LATEX = shutil.which("latexmk") is not None
SP = 65536   # points -> unités pdfTeX


def positions_file(folder: Path, anchors: list, page_height=845.0) -> Path:
    """Fichier .cvpos fictif : page A4 (597.5 x 845 pt), texte de 43 à 553 pt, du haut 43 à 801 pt."""
    lines = [f"page,597.5pt,{page_height}pt,43.0pt,510.0pt,43.0pt,758.0pt"]
    lines += [f"{key},{page},{int(43 * SP)},{int((page_height - top) * SP)},{ascent}pt"
              for key, page, top, ascent in anchors]
    path = folder / "cv.cvpos"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class ReadLayoutTest(unittest.TestCase):
    """Calcul des zones à partir des positions (sans LaTeX)."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)

    def layout(self, anchors, **kwargs):
        return read_layout(positions_file(self.folder, anchors), **kwargs)

    def keys(self, layout):
        return [(r["key"], r["page"]) for r in layout["regions"]]

    def test_sections_and_items_follow_each_other(self):
        layout = self.layout([
            ("profile", 1, 60, 20), ("experiences", 1, 120, 10), ("experiences/0", 1, 140, 8),
            ("experiences/1", 1, 200, 8), ("skills", 1, 260, 10), ("end", 1, 300, 0)])
        self.assertEqual(self.keys(layout), [("profile", 1), ("experiences", 1), ("experiences/0", 1),
                                             ("experiences/1", 1), ("skills", 1)])
        regions = {r["key"]: r for r in layout["regions"]}
        # La section s'arrête au début de la suivante ; le dernier élément à la fin de sa section
        self.assertEqual(regions["experiences"]["bottom"], regions["skills"]["top"])
        self.assertEqual(regions["experiences/0"]["bottom"], regions["experiences/1"]["top"])
        self.assertEqual(regions["experiences/1"]["bottom"], regions["experiences"]["bottom"])
        self.assertEqual(regions["skills"]["bottom"], round(300 / 845, 4))
        # Haut de la ligne = ligne de base - hauteur de la ligne
        self.assertEqual(regions["experiences"]["top"], round((120 - 10) / 845, 4))
        self.assertEqual(regions["experiences/0"]["json"], ["experiences", 0])
        self.assertEqual(regions["skills"]["json"], ["skills", "languages"])
        self.assertEqual(regions["profile"]["json"], ["header"])
        for region in layout["regions"]:
            self.assertTrue(0 <= region["left"] < region["right"] <= 1)
            self.assertTrue(0 <= region["top"] < region["bottom"] <= 1)

    def test_absent_sections_have_no_region(self):
        layout = self.layout([("profile", 1, 60, 20), ("education", 1, 120, 10), ("end", 1, 200, 0)])
        self.assertEqual(self.keys(layout), [("profile", 1), ("education", 1)])

    def test_sections_and_items_cut_by_a_page_break(self):
        layout = self.layout([
            ("profile", 1, 60, 20), ("experiences", 1, 600, 10), ("experiences/0", 1, 620, 8),
            ("experiences/1", 1, 780, 8), ("skills", 2, 200, 10), ("end", 2, 260, 0)], pages=2)
        self.assertEqual(layout["pages"], 2)
        self.assertEqual(self.keys(layout), [
            ("profile", 1), ("experiences", 1), ("experiences", 2), ("experiences/0", 1),
            ("experiences/1", 1), ("experiences/1", 2), ("skills", 2)])
        second = [r for r in layout["regions"] if r["page"] == 2 and r["key"] == "experiences/1"][0]
        self.assertEqual(second["top"], round(43 / 845, 4))              # haut de la zone de texte
        self.assertEqual(second["bottom"], round((200 - 10) / 845, 4))   # jusqu'au titre suivant
        first = [r for r in layout["regions"] if r["page"] == 1 and r["key"] == "experiences/1"][0]
        self.assertEqual(first["bottom"], round(801 / 845, 4))           # bas de la zone de texte

    def test_item_priority_and_clicks_outside(self):
        layout = self.layout([("profile", 1, 60, 20), ("experiences", 1, 120, 10), ("experiences/0", 1, 140, 8),
                              ("end", 1, 300, 0)])
        self.assertEqual(region_at(layout, 1, 0.5, 150 / 845)["key"], "experiences/0")   # élément d'abord
        self.assertEqual(region_at(layout, 1, 0.5, 115 / 845)["key"], "experiences")     # titre de section
        self.assertIsNone(region_at(layout, 1, 0.02, 150 / 845))                        # marge gauche
        self.assertIsNone(region_at(layout, 1, 0.5, 0.9))                               # sous le contenu
        self.assertIsNone(region_at(layout, 2, 0.5, 150 / 845))                         # autre page

    def test_invalid_positions(self):
        with self.assertRaises(LayoutError):
            self.layout([("profile", 1, 60, 20)])                                       # pas de marqueur de fin
        (self.folder / "bad.cvpos").write_text("n'importe quoi\n", encoding="utf-8")
        with self.assertRaises(LayoutError):
            read_layout(self.folder / "bad.cvpos")
        layout = self.layout([("profile", 1, 60, 20), ("autre", 1, 90, 10), ("end", 1, 200, 0)])
        self.assertEqual(self.keys(layout), [("profile", 1)])                           # clé inconnue ignorée

    def test_layout_is_written_only_from_this_compilation(self):
        pdf = self.folder / "cv.pdf"
        pdf.write_bytes(b"%PDF")
        self.assertIsNone(write_layout(self.folder, pdf, 1))                            # pas de marqueurs
        positions_file(self.folder, [("profile", 1, 60, 20), ("end", 1, 200, 0)])
        old = time.time() - 3600
        os.utime(self.folder / "cv.cvpos", (old, old))
        self.assertIsNone(write_layout(self.folder, pdf, 1))                            # positions anciennes
        os.utime(self.folder / "cv.cvpos")
        path = write_layout(self.folder, pdf, 1)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["pdf"], "cv.pdf")


def without_anchors(folder: Path) -> None:
    """Le même CV sans aucun marqueur : .tex principal d'origine et sections sans \\cvanchor."""
    main = next(folder.glob("*.tex"))
    text = main.read_text(encoding="utf-8")
    text = re.sub(r"%-------------------------\n% Marqueurs invisibles.*?\\makeatother\n\n", "", text, flags=re.S)
    main.write_text(text.replace("\\cvanchor{end}\n", ""), encoding="utf-8")
    for section in (folder / "sections").glob("*.tex"):
        content = section.read_text(encoding="utf-8")
        content = re.sub(r"\\cvanchor\{[^}]*\}", "", content).replace("\\providecommand{\\cvanchor}[1]{}\n", "")
        section.write_text(content, encoding="utf-8")


def text_items(pdf: Path) -> list:
    """(page, texte, x, y) normalisés (origine en haut à gauche) de chaque morceau de texte du PDF."""
    items = []
    for number, page in enumerate(PdfReader(pdf).pages, start=1):
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        page.extract_text(visitor_text=lambda text, cm, tm, font, size: text.strip() and items.append(
            (number, text.strip(), round((tm[4] * cm[0] + cm[4]) / width, 4),
             round(1 - (tm[5] * cm[3] + cm[5]) / height, 4))))
    return items


@unittest.skipUnless(HAS_LATEX, "latexmk n'est pas installé")
class CompiledLayoutTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        original = build_cv.APPLICATIONS_DIR
        build_cv.APPLICATIONS_DIR = self.folder
        self.addCleanup(setattr, build_cv, "APPLICATIONS_DIR", original)
        self.doc = build_document(fake_draft(), example_profile())

    def compile_doc(self, doc):
        main_tex = write_cv(doc, {})
        pdf, pages = compile_cv(main_tex)
        layout = json.loads((pdf.parent / "layout.json").read_text(encoding="utf-8"))
        return main_tex, pdf, pages, layout

    def test_markers_do_not_change_the_appearance(self):
        for name, doc in (("one-page", self.doc), ("two-pages", self.long_doc())):
            with self.subTest(name):
                main_tex, pdf, pages, _ = self.compile_doc(doc)
                plain = self.folder / f"plain-{name}"
                shutil.copytree(main_tex.parent, plain, ignore=shutil.ignore_patterns("build"))
                without_anchors(plain)
                self.assertNotIn("cvanchor", "".join(p.read_text(encoding="utf-8") for p in plain.rglob("*.tex")))
                plain_pdf, plain_pages = compile_cv(plain / main_tex.name)
                self.assertEqual(plain_pages, pages)
                self.assertEqual(text_items(plain_pdf), text_items(pdf))
                self.assertFalse((plain_pdf.parent / "layout.json").exists())          # sans marqueurs : pas de zones

    def test_texts_fall_in_their_regions(self):
        _, pdf, pages, layout = self.compile_doc(self.doc)
        self.assertEqual((pages, layout["pages"], layout["pdf"]), (1, 1, pdf.name))
        items = text_items(pdf)

        def region_of(prefix):
            page, text, x, y = next(item for item in items if item[1].startswith(prefix))
            return (region_at(layout, page, x, y) or {}).get("key")

        expected = {"John Doe": "profile", "john.doe@example.com": "profile", "Profil": "profile",
                    "Exp": "experiences", "Stagiaire Vision": "experiences/0", "Stagiaire D": "experiences/1",
                    "– Assistant adopt": "experiences/1", "Formation": "education", "Example Eng": "education/0",
                    "Example Univ": "education/1", "Projets": "projects", "Syst": "projects/0",
                    "Pipeline": "projects/1", "Programmation": "skills", "Langues": "skills", "Tennis": "interests"}
        for prefix, key in expected.items():
            self.assertEqual(region_of(prefix), key, prefix)

        sections = [r["key"] for r in layout["regions"] if r["level"] == "section"]
        self.assertEqual(sections, ["profile", "experiences", "education", "projects", "skills", "interests"])
        for item in (r for r in layout["regions"] if r["level"] == "item"):
            section = next(r for r in layout["regions"] if r["key"] == item["key"].split("/")[0])
            self.assertTrue(section["top"] <= item["top"] < item["bottom"] <= section["bottom"], item["key"])

    def test_empty_sections_have_no_region(self):
        doc = copy.deepcopy(self.doc)
        doc["projects"], doc["interests"], doc["skills"], doc["languages"] = [], [], [], []
        _, _, _, layout = self.compile_doc(doc)
        self.assertEqual([r["key"] for r in layout["regions"] if r["level"] == "section"],
                         ["profile", "experiences", "education"])

    def long_doc(self):
        """Deux pages, le saut de page tombant au milieu de la première expérience."""
        doc = copy.deepcopy(self.doc)
        doc["experiences"][0]["bullets"] = doc["experiences"][0]["bullets"] * 34
        return doc

    def test_cv_on_two_pages(self):
        _, pdf, pages, layout = self.compile_doc(self.long_doc())
        self.assertEqual((pages, layout["pages"]), (2, 2))
        self.assertTrue(all(r["page"] in (1, 2) for r in layout["regions"]))
        items = text_items(pdf)
        split = [(r["page"], r["level"]) for r in layout["regions"] if r["key"] == "experiences/0"]
        self.assertEqual(split, [(1, "item"), (2, "item")])                 # élément coupé : une zone par page
        for prefix, key in {"Formation": "education", "Programmation": "skills", "Tennis": "interests"}.items():
            page, text, x, y = next(item for item in items if item[1].startswith(prefix))
            self.assertEqual(page, 2)
            self.assertEqual(region_at(layout, page, x, y)["key"], key)
        # Le texte en haut de la page 2 appartient encore à l'expérience commencée en page 1
        page, text, x, y = next(item for item in items if item[0] == 2)
        hit = region_at(layout, 2, x, y)
        self.assertEqual(hit["level"], "item")
        self.assertTrue(hit["key"].startswith("experiences/"))
        self.assertIn(hit["key"], [r["key"] for r in layout["regions"] if r["page"] == 1])
        # Tout le texte des deux pages est dans une zone
        self.assertEqual([item for item in items if region_at(layout, *item[0:1], *item[2:]) is None], [])

    def test_failed_compilation_leaves_no_layout(self):
        main_tex, pdf, _, _ = self.compile_doc(self.doc)
        layout = pdf.parent / "layout.json"
        self.assertTrue(layout.exists())
        experience = main_tex.parent / "sections" / "experience.tex"
        experience.write_text(experience.read_text(encoding="utf-8") + "\n\\commandeinconnue\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            compile_cv(main_tex)
        self.assertFalse(layout.exists())

    def test_cv_folders_created_before_the_markers_still_compile(self):
        # Ancien main.tex (sans \cvanchor) + nouvelles sections : les marqueurs sont ignorés, pas de zones
        folder = self.folder / "ancien"
        shutil.copytree(TEMPLATE_DIR, folder)
        without_anchors(folder)
        for name, content in render_sections(self.doc).items():
            (folder / "sections" / f"{name}.tex").write_text(content, encoding="utf-8")
        pdf, pages = compile_cv(folder / "main.tex")
        self.assertEqual(pages, 1)
        self.assertFalse((pdf.parent / "layout.json").exists())


if __name__ == "__main__":
    unittest.main()
