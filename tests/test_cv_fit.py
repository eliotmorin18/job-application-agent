"""
Tests de la règle « une page au maximum » (cv/build_cv.fit_one_page, cv/pipeline.py, api/cvs.py).
Profil et CV fictifs, dossiers temporaires, compilation simulée (un test réel si latexmk est installé),
aucun appel à Claude.

Lancement :  python -m unittest discover tests
"""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from candidate.profile import EXAMPLE_PATH, load_profile
from cv import pipeline
from cv.build_cv import MAX_FIT_COMPILES, CvTooLongError, fit_one_page, pdf_pages, write_cv
from cv.document import build_document, load_document
from cv_fixtures import fake_draft
from test_analysis import OFFER, fake_answer


class FakeCompiler:
    """Compilation simulée : le nombre de pages dépend du nombre de puces de cv.json."""

    def __init__(self, max_bullets: int | None):
        self.max_bullets = max_bullets
        self.calls = 0

    def __call__(self, main_tex: Path):
        self.calls += 1
        doc = json.loads((main_tex.parent / "cv.json").read_text(encoding="utf-8"))
        bullets = sum(len(e["bullets"]) for section in ("experiences", "education", "projects") for e in doc[section])
        pdf = main_tex.parent / "build" / f"{main_tex.stem}.pdf"
        pdf.parent.mkdir(exist_ok=True)
        pdf.write_bytes(b"%PDF " + str(bullets).encode())
        return pdf, 1 if self.max_bullets is not None and bullets <= self.max_bullets else 2


def bullets(doc: dict) -> list[str]:
    return [b for section in ("experiences", "education", "projects") for e in doc[section] for b in e["bullets"]]


class FitOnePageTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.profile = load_profile(EXAMPLE_PATH)
        self.doc = build_document(fake_draft(), self.profile)
        self.doc["experiences"][0]["bullets"] += ["Puce longue fictive A.", "Puce longue fictive B."]
        self.doc["interests"] += ["Échecs"]
        self.main_tex = write_cv(self.doc, OFFER, applications_dir=self.folder)

    def test_a_one_page_cv_is_left_untouched(self):
        compiler = FakeCompiler(max_bullets=100)
        result = fit_one_page(self.main_tex, self.doc, compiler)
        self.assertEqual((result.pages, result.adjustments, compiler.calls), (1, [], 1))
        self.assertEqual(load_document(self.main_tex.parent), self.doc)

    def test_a_too_long_cv_is_brought_back_to_one_page_by_removing_secondary_content(self):
        compiler = FakeCompiler(max_bullets=len(bullets(self.doc)) - 3)
        result = fit_one_page(self.main_tex, self.doc, compiler)
        self.assertEqual(result.pages, 1)
        self.assertTrue(result.adjustments)
        self.assertLessEqual(compiler.calls, 1 + MAX_FIT_COMPILES)
        # cv.json décrit le PDF obtenu ; rien n'est ajouté ni réécrit, seulement retiré en fin de liste
        saved = load_document(self.main_tex.parent)
        self.assertEqual(saved, result.document)
        self.assertTrue(set(bullets(saved)) <= set(bullets(self.doc)))
        self.assertEqual(saved["experiences"][0]["bullets"][:3], self.doc["experiences"][0]["bullets"][:3])
        self.assertEqual(saved["header"], self.doc["header"])
        selection = json.loads((self.main_tex.parent / "selection.json").read_text(encoding="utf-8"))
        self.assertEqual(selection["page_adjustments"], result.adjustments)
        self.assertEqual(selection["selected_project_ids"], [p["source_id"] for p in saved["projects"]])

    def test_least_relevant_items_go_first(self):
        compiler = FakeCompiler(max_bullets=len(bullets(self.doc)) - 2)
        result = fit_one_page(self.main_tex, self.doc, compiler)
        self.assertEqual(result.adjustments[0], "Détails secondaires des projets et des formations retirés.")
        self.assertEqual([e["source_id"] for e in result.document["experiences"]],
                         [e["source_id"] for e in self.doc["experiences"]])     # expériences gardées

    def test_two_pages_is_never_a_success(self):
        compiler = FakeCompiler(max_bullets=None)                            # jamais une page
        with self.assertRaises(CvTooLongError) as context:
            fit_one_page(self.main_tex, self.doc, compiler)
        error = context.exception
        self.assertEqual((error.pages, error.folder), (2, self.main_tex.parent))
        self.assertIn("ne tient pas sur une page", str(error))
        self.assertLessEqual(compiler.calls, 1 + MAX_FIT_COMPILES + 1)        # tentatives limitées
        self.assertEqual(load_document(self.main_tex.parent), self.doc)        # contenu complet remis

    def test_an_unknown_page_count_is_not_a_success(self):
        def unreadable(main_tex):
            return main_tex.parent / "build" / "x.pdf", 0
        with self.assertRaises(CvTooLongError):
            fit_one_page(self.main_tex, self.doc, unreadable)
        self.assertEqual(pdf_pages(self.folder / "absent.pdf"), 0)

    @unittest.skipUnless(shutil.which("latexmk"), "latexmk n'est pas installé")
    def test_real_compilation_of_a_too_long_cv(self):
        doc = copy.deepcopy(self.doc)
        for entry in doc["experiences"] + doc["projects"]:
            entry["bullets"] = entry["bullets"] * 4
        main_tex = write_cv(doc, OFFER, applications_dir=self.folder)
        result = fit_one_page(main_tex, doc)
        self.assertEqual(result.pages, 1)
        self.assertEqual(pdf_pages(result.pdf), 1)
        self.assertTrue(result.adjustments)


class PipelineOnePageTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.profile = load_profile(EXAMPLE_PATH)

    def run_pipeline(self, compiler):
        analyze = mock.Mock(return_value={"status": "completed", "score": {}})
        never = mock.Mock(side_effect=AssertionError("préparation lancée pendant la génération"))
        with mock.patch.object(pipeline, "read_job", return_value={"url": "u", "title": "t", "text": "offre"}), \
             mock.patch.object(pipeline, "analyze_job", return_value=copy.deepcopy(OFFER)), \
             mock.patch.object(pipeline, "generate_cv", return_value=build_document(fake_draft(), self.profile)), \
             mock.patch.object(pipeline, "verify_cv", return_value=[]), \
             mock.patch.object(pipeline, "compile_cv", side_effect=compiler), \
             mock.patch.object(pipeline, "analyze_folder", analyze), \
             mock.patch("interview.preparation.prepare_folder", never), \
             mock.patch("interview.research.research_company", never), \
             mock.patch("llm.structured.generate_structured", never):
            try:
                return pipeline.generate_from_url("https://jobs.example.com/1", self.profile,
                                                  applications_dir=self.folder), analyze
            finally:
                never.assert_not_called()

    def test_generation_never_prepares_the_interview(self):
        result, analyze = self.run_pipeline(FakeCompiler(max_bullets=100))
        self.assertEqual((result.pages, result.adjustments), (1, []))
        analyze.assert_called_once()
        for name in ("preparation.json", "company_research.json"):
            self.assertFalse((result.folder / name).exists())

    def test_a_cv_that_stays_too_long_fails_without_analysis(self):
        with self.assertRaises(CvTooLongError) as context:
            self.run_pipeline(FakeCompiler(max_bullets=None))
        self.assertTrue((context.exception.folder / "cv.json").exists())       # gardé pour l'éditeur
        self.assertFalse((context.exception.folder / "analysis.json").exists())


class AnalysisPromptTest(unittest.TestCase):

    def test_fake_answer_matches_the_reduced_schema(self):
        from cv.analysis import ANALYSIS_SCHEMA
        self.assertEqual(set(fake_answer()), set(ANALYSIS_SCHEMA["properties"]))


if __name__ == "__main__":
    unittest.main()
