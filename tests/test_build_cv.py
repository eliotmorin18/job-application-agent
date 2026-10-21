"""
Tests de l'écriture du dossier d'un CV (cv.json, sections, sélection), de sa recompilation
et du comptage de pages lu dans le journal LaTeX. Données fictives, dossiers temporaires.

Lancement :  python -m unittest discover tests
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cv import build_cv
from cv.build_cv import _count_pages, rebuild_cv, write_cv
from cv.document import build_document, load_document, save_document
from cv.render import render_sections
from cv_fixtures import example_profile, fake_draft


class WriteCvTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        original = build_cv.APPLICATIONS_DIR
        build_cv.APPLICATIONS_DIR = self.folder
        self.addCleanup(setattr, build_cv, "APPLICATIONS_DIR", original)
        self.doc = build_document(fake_draft(), example_profile())

    def test_writes_cv_json_sections_offer_and_selection(self):
        issues = [{"section": "heading", "cv_text": "x", "problem": "y"}]
        main_tex = write_cv(self.doc, {"job_title": "Stage"}, verification_issues=issues)
        folder = main_tex.parent
        self.assertEqual(folder.name, "acme-robotics-stage-vision-par-ordinateur")
        self.assertEqual(main_tex.name, "John_Doe_Candidature_Acme_Robotics_Stage_Vision_par_Ordinateur.tex")
        self.assertEqual(load_document(folder), self.doc)
        for name, content in render_sections(self.doc).items():
            self.assertEqual((folder / "sections" / f"{name}.tex").read_text(encoding="utf-8"), content.strip() + "\n")
        selection = json.loads((folder / "selection.json").read_text(encoding="utf-8"))
        self.assertEqual(selection, {
            "language": "fr",
            "selected_experience_ids": ["example-research-company", "example-software-company"],
            "selected_project_ids": ["multi-agent-system", "face-recognition"],
            "gaps": ["Pas d'expérience en robotique industrielle."],
            "verification_issues": issues,
        })
        self.assertEqual(json.loads((folder / "offer.json").read_text(encoding="utf-8")), {"job_title": "Stage"})
        self.assertFalse((folder / "main.tex").exists())

    def test_a_second_cv_for_the_same_offer_gets_its_own_folder(self):
        first = write_cv(self.doc, {}).parent
        second = write_cv(self.doc, {}).parent
        self.assertEqual(second.name, first.name + "-2")

    @unittest.skipUnless(shutil.which("latexmk"), "latexmk n'est pas installé")
    def test_rebuild_after_editing_cv_json(self):
        folder = write_cv(self.doc, {}).parent
        self.doc["experiences"].reverse()
        self.doc["experiences"][0]["bullets"].append("Puce ajoutée dans l'éditeur.")
        save_document(folder, self.doc)
        pdf, pages = rebuild_cv(folder)
        self.assertEqual(pages, 1)
        experience = (folder / "sections" / "experience.tex").read_text(encoding="utf-8")
        self.assertIn("Puce ajoutée dans l'éditeur.", experience)
        self.assertLess(experience.index("Example Software Company"), experience.index("Example Research Company"))


class CountPagesTest(unittest.TestCase):

    def test_one_page_on_a_single_line(self):
        log = "Output written on build/CV.pdf (1 page, 135663 bytes).\n"
        self.assertEqual(_count_pages(log), 1)

    def test_one_page_cut_between_number_and_page(self):
        # Extrait réel : LaTeX a coupé la ligne entre « 1 » et « page »
        log = (
            "Output written on build/Eliot_Morin_Candidature_Test_Renommage_Template.pdf (1 \n"
            "page, 135663 bytes).\n"
        )
        self.assertEqual(_count_pages(log), 1)

    def test_one_page_cut_inside_the_file_name(self):
        # Extrait réel : la coupure tombe dans le nom du PDF
        log = (
            "Output written on build/Eliot_Morin_Candidature_Dassault_Systemes_Stage_IA_Segm\n"
            "entation_Medicale.pdf (1 page, 135663 bytes).\n"
        )
        self.assertEqual(_count_pages(log), 1)

    def test_two_pages_on_a_single_line(self):
        log = "Output written on build/CV.pdf (2 pages, 160000 bytes).\n"
        self.assertEqual(_count_pages(log), 2)

    def test_two_pages_cut_between_number_and_pages(self):
        log = "Output written on build/Un_Nom_De_Fichier_Assez_Long_Pour_Couper.pdf (2\npages, 160000 bytes).\n"
        self.assertEqual(_count_pages(log), 2)

    def test_no_output_line(self):
        self.assertEqual(_count_pages("No pages of output.\n"), 0)


if __name__ == "__main__":
    unittest.main()
