"""
Tests de la conversion du CV structuré en LaTeX (cv/render.py) et de la compilation du PDF.
Données fictives uniquement ; aucun appel à Claude. Les tests de compilation sont ignorés si
latexmk n'est pas installé.

Lancement :  python -m unittest discover tests
"""

import copy
import shutil
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from cv import build_cv
from cv.build_cv import TEMPLATE_DIR, compile_cv
from cv.document import build_document
from cv.render import (display_url, escape_latex, format_dates, latex_url, render_sections, short_location)
from cv_fixtures import example_profile, fake_draft


HAS_LATEX = shutil.which("latexmk") is not None


def small_doc(language="fr") -> dict:
    return {
        "schema_version": 1, "language": language, "company": "Acme", "role": "Stage",
        "header": {"name": "Jane Doe",
                   "contacts": [{"type": "email", "value": "jane@example.com"},
                                {"type": "github", "value": "https://github.com/jane/"}],
                   "summary": "Ingénieure **IA**."},
        "experiences": [{"source_id": "acme", "title": "Stagiaire IA", "organization": "Acme", "context": "R&D",
                         "location": "Paris", "dates": "2024–2025", "bullets": ["Mission A.", "Mission B."]}],
        "education": [{"source_id": "school", "institution": "École X", "location": "Paris", "dates": "2023",
                       "bullets": ["**Cours :** ML."]}],
        "projects": [{"source_id": "p", "name": "Projet P", "link": {"url": "https://github.com/jane/p", "label": "GitHub"},
                      "bullets": ["Fait P."]}],
        "skills": [{"label": "Programmation", "items": ["Python", "C++"]}],
        "languages": [{"name": "Français", "level": "natif"}, {"name": "Anglais", "level": ""}],
        "interests": ["Tennis", "Échecs"],
        "gaps": [],
    }


class EscapeTest(unittest.TestCase):

    def test_latex_special_characters(self):
        cases = {
            "R&D": r"R\&D", "100 %": r"100 \%", "$5": r"\$5", "#1": r"\#1", "a_b": r"a\_b",
            "{x}": r"\{x\}", "~": r"\textasciitilde{}", "x^2": r"x\textasciicircum{}2",
            "a\\b": r"a\textbackslash{}b", "<10 ms>": r"\textless{}10 ms\textgreater{}", "a|b": r"a\textbar{}b",
            "« oui »": "`` oui ''", "50 €": "50 EUR", "20 °C": r"20 \textdegree{}C",
        }
        for text, expected in cases.items():
            self.assertEqual(escape_latex(text), expected, text)

    def test_backslash_is_never_a_latex_command(self):
        self.assertEqual(escape_latex(r"\textbf{x} \input{secret}"),
                         r"\textbackslash{}textbf\{x\} \textbackslash{}input\{secret\}")

    def test_bold(self):
        self.assertEqual(escape_latex("Utilisation de **PyTorch** et **C++**"),
                         r"Utilisation de \textbf{PyTorch} et \textbf{C++}")
        self.assertEqual(escape_latex("**R&D :** 100 %"), r"\textbf{R\&D :} 100 \%")   # contenu du gras échappé
        self.assertEqual(escape_latex("5 ** 2 et ** seul"), "5 ** 2 et ** seul")      # sans fermeture : tel quel

    def test_whitespace_and_accents(self):
        self.assertEqual(escape_latex("  Développement\n  d'un   modèle  "), "Développement d'un modèle")
        self.assertEqual(escape_latex("Profil\u00a0:"), "Profil~:")
        self.assertEqual(escape_latex(None), "")

    def test_urls(self):
        self.assertEqual(latex_url("https://example.com/a%20b#top"), r"https://example.com/a\%20b\#top")
        self.assertEqual(display_url("https://www.linkedin.com/in/jane-doe-/"), "linkedin.com/in/jane-doe-")
        self.assertEqual(display_url("https://github.com/jane"), "github.com/jane")

    def test_dates_and_places(self):
        self.assertEqual(format_dates("2024-06", "2025-02"), "2024–2025")
        self.assertEqual(format_dates("2026-02", "2026-08"), "2026")
        self.assertEqual(format_dates("2026", None), "2026")
        self.assertEqual(format_dates(None, "2025"), "2025")
        self.assertEqual(format_dates(None, None), "")
        self.assertEqual(short_location("Paris, France"), "Paris")
        self.assertEqual(short_location("Europe"), "Europe")
        self.assertEqual(short_location(None), "")


class RenderTest(unittest.TestCase):
    """Le LaTeX produit reprend exactement les macros et la mise en page du template."""

    def test_heading(self):
        self.assertEqual(render_sections(small_doc())["heading"], (
            "%----------HEADING-----------------\n"
            "\\providecommand{\\cvanchor}[1]{}\n"
            "\\begin{center}\n"
            "    \\textbf{\\Huge \\scshape \\cvanchor{profile}Jane Doe} \\\\ \\vspace{2pt}\n"
            "    \\small \\faEnvelope\\ \\href{mailto:jane@example.com}{jane@example.com}\\ $|$\\\n"
            "    \\faGithub\\ \\href{https://github.com/jane/}{github.com/jane}\n"
            "\\end{center}\n"
            "\n\\vspace{4pt}\n"
            "\\textbf{Profil :} Ingénieure \\textbf{IA}.\n"
            "\n\\vspace{2pt}\n"))

    def test_experience(self):
        self.assertEqual(render_sections(small_doc())["experience"], (
            "%===========================\n%     EXPERIENCE\n%===========================\n"
            "\\section*{\\cvanchor{experiences}Expérience}\n\n"
            "\\begin{tabular*}{\\textwidth}{l@{\\extracolsep{\\fill}}r}\n"
            "    \\textbf{\\cvanchor{experiences/0}Stagiaire IA — Acme} \\textnormal{(R\\&D)} & \\textbf{Paris, 2024–2025} \\\\\n"
            "\\end{tabular*}\n\n"
            "\\resumeItemListStart\n"
            "    \\resumeItemPlain{Mission A.}\n"
            "    \\resumeItemPlain{Mission B.}\n"
            "\\resumeItemListEnd\n"))

    def test_education_projects_skills_interests(self):
        sections = render_sections(small_doc())
        self.assertIn("\\section*{\\cvanchor{education}Formation}", sections["education"])
        self.assertIn("    \\textbf{\\cvanchor{education/0}École X} & \\textbf{Paris, 2023} \\\\\n", sections["education"])
        self.assertIn("    \\resumeItemPlain{\\textbf{Cours :} ML.}\n", sections["education"])
        self.assertIn("    \\textbf{\\cvanchor{projects/0}Projet P} & \\footnotesize\\href{https://github.com/jane/p}{GitHub} \\\\\n",
                      sections["projects"])
        self.assertEqual(sections["technical-skills"].split("\\section*{\\cvanchor{skills}Compétences Techniques}\n\n")[1], (
            "\\begin{tabularx}{\\textwidth}{@{}l@{\\hspace{6pt}}X@{}}\n"
            "    \\textbf{Programmation :} & Python, C++ \\\\\n"
            "    \\textbf{Langues :} & Français (natif), Anglais \\\\\n"
            "\\end{tabularx}\n"))
        self.assertTrue(sections["interests"].endswith(
            "\\section*{\\cvanchor{interests}Centres d'intérêt}\n\nTennis \\textbullet\\ Échecs\n"))

    def test_skills_keep_the_order_chosen_in_the_editor(self):
        doc = small_doc()
        doc["skills"] = [{"label": "Programmation", "items": ["C++", "Rust", "Python"]},
                         {"label": "Outils", "items": ["Git", "Docker"]}]
        skills = render_sections(doc)["technical-skills"]
        self.assertIn("    \\textbf{Programmation :} & C++, Rust, Python \\\\\n", skills)
        self.assertIn("    \\textbf{Outils :} & Git, Docker \\\\\n", skills)
        self.assertLess(skills.index("Programmation"), skills.index("Outils"))

    def test_interests_keep_the_order_chosen_in_the_editor(self):
        doc = small_doc()
        doc["interests"] = ["Échecs", "Tennis", "Escalade"]
        self.assertTrue(render_sections(doc)["interests"].endswith(
            "Échecs \\textbullet\\ Tennis \\textbullet\\ Escalade\n"))

    def test_english_labels(self):
        sections = render_sections(small_doc("en"))
        self.assertIn("\\textbf{Profile:}", sections["heading"])
        self.assertIn("\\section*{\\cvanchor{experiences}Experience}", sections["experience"])
        self.assertIn("\\textbf{Languages:}", sections["technical-skills"])
        self.assertIn("\\section*{\\cvanchor{skills}Technical Skills}", sections["technical-skills"])

    def test_optional_parts_are_left_out(self):
        doc = small_doc()
        doc["header"]["contacts"], doc["header"]["summary"] = [], ""
        doc["experiences"][0].update(context=None, organization="", location="", dates="", bullets=[])
        doc["projects"][0]["link"] = None
        sections = render_sections(doc)
        self.assertNotIn("\\\\ \\vspace{2pt}", sections["heading"])
        self.assertNotIn("Profil", sections["heading"])
        self.assertIn("    \\textbf{\\cvanchor{experiences/0}Stagiaire IA} &  \\\\\n", sections["experience"])
        self.assertNotIn("resumeItemListStart", sections["experience"])       # pas de liste vide
        self.assertIn("    \\textbf{\\cvanchor{projects/0}Projet P} &  \\\\\n", sections["projects"])

    def test_empty_sections_are_hidden(self):
        doc = small_doc()
        for key in ("experiences", "education", "projects", "skills", "languages", "interests"):
            doc[key] = []
        for name, content in render_sections(doc).items():
            if name != "heading":
                self.assertNotIn("\\section*", content, name)
                self.assertNotIn("tabular", content, name)

    def test_six_section_files_in_the_template_order(self):
        self.assertEqual(list(render_sections(small_doc())),
                         ["heading", "experience", "education", "projects", "technical-skills", "interests"])
        main = (TEMPLATE_DIR / "main.tex").read_text(encoding="utf-8")
        for name in render_sections(small_doc()):
            self.assertIn(f"\\input{{sections/{name}}}", main)


def text_positions(pdf: Path) -> list:
    """(texte, x, y) de chaque morceau de texte du PDF, pour comparer deux mises en page."""
    items = []
    PdfReader(pdf).pages[0].extract_text(
        visitor_text=lambda text, cm, tm, font, size: text.strip() and items.append(
            (text.strip(), round(tm[4] * cm[0] + cm[4], 1), round(tm[5] * cm[3] + cm[5], 1))))
    return items


@unittest.skipUnless(HAS_LATEX, "latexmk n'est pas installé")
class CompileTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self._applications = build_cv.APPLICATIONS_DIR
        build_cv.APPLICATIONS_DIR = self.folder / "applications"
        self.addCleanup(setattr, build_cv, "APPLICATIONS_DIR", self._applications)

    def compile_doc(self, doc):
        return compile_cv(build_cv.write_cv(doc, {"job_title": "Stage"}))

    def compile_sections(self, sections: dict, name: str) -> Path:
        folder = self.folder / name
        shutil.copytree(TEMPLATE_DIR, folder)
        for section, content in sections.items():
            (folder / "sections" / f"{section}.tex").write_text(content, encoding="utf-8")
        return compile_cv(folder / "main.tex")[0]

    def test_realistic_fictional_cv_fits_on_one_page(self):
        pdf, pages = self.compile_doc(build_document(fake_draft(), example_profile()))
        self.assertTrue(pdf.exists())
        self.assertEqual(pages, 1)
        text = PdfReader(pdf).pages[0].extract_text()
        for expected in ("John Doe", "Example Research Company", "Langues", "Tennis", "github.com/johndoe"):
            self.assertIn(expected, text)

    def test_special_characters_compile(self):
        doc = small_doc()
        doc["experiences"][0]["bullets"] = [
            "R&D à 100 % pour $5, #1, a_b, {x}, ~, x^2, <10 ms>, a|b, back\\slash, « oui », 50 €, 20 °C, – — ’ …",
            "**Gras** et ** seul",
        ]
        doc["skills"][0]["items"] = ["C++", "C#", "F#", "Node.js"]
        pdf, pages = self.compile_doc(doc)
        self.assertEqual(pages, 1)
        text = PdfReader(pdf).pages[0].extract_text()
        for expected in ("R&D", "100 %", "#1", "{x}", "<10 ms>", "a|b", "50 EUR", "C++", "C#"):
            self.assertIn(expected, text)

    def test_empty_sections_compile(self):
        doc = small_doc()
        for key in ("experiences", "education", "projects", "skills", "languages", "interests"):
            doc[key] = []
        self.assertEqual(self.compile_doc(doc)[1], 1)

    def test_same_layout_as_the_former_latex_written_by_claude(self):
        """Même contenu écrit à la main comme le faisait Claude (ancien système) : même PDF au point près."""
        doc = small_doc()
        legacy = render_sections(copy.deepcopy(doc))
        legacy["heading"] = (
            "%----------HEADING-----------------\n\\begin{center}\n"
            "    \\textbf{\\Huge \\scshape Jane Doe} \\\\ \\vspace{2pt}\n"
            "    \\small \\faEnvelope\\ \\href{mailto:jane@example.com}{jane@example.com}\\ $|$\\\n"
            "    \\faGithub\\ \\href{https://github.com/jane/}{github.com/jane}\n\\end{center}\n\n"
            "\\vspace{4pt}\n\\textbf{Profil :} Ingénieure \\textbf{IA}.\n\n\\vspace{2pt}\n")
        legacy["experience"] = (
            "%===========================\n%     EXPERIENCE\n%===========================\n"
            "\\section*{Expérience}\n\n% Acme\n"
            "\\begin{tabular*}{\\textwidth}{l@{\\extracolsep{\\fill}}r}\n"
            "    \\textbf{Stagiaire IA — Acme} \\textnormal{(R\\&D)} & \\textbf{Paris, 2024–2025} \\\\\n"
            "\\end{tabular*}\n\n\\resumeItemListStart\n"
            "    \\resumeItemPlain{Mission A.}\n    \\resumeItemPlain{Mission B.}\n\\resumeItemListEnd\n")
        legacy["technical-skills"] = (
            "%===========================\n%     TECHNICAL SKILLS\n%===========================\n"
            "\\section*{Compétences Techniques}\n\n"
            "\\begin{tabularx}{\\textwidth}{@{}l@{\\hspace{6pt}}X@{}}\n"
            "    \\textbf{Programmation :} & Python, C++ \\\\\n"
            "    \\textbf{Langues :} & Français (natif), Anglais \\\\\n\\end{tabularx}\n")
        old = self.compile_sections(legacy, "legacy")
        new = self.compile_sections(render_sections(doc), "new")
        self.assertEqual(text_positions(new), text_positions(old))
        self.assertGreater(len(text_positions(new)), 10)


if __name__ == "__main__":
    unittest.main()
