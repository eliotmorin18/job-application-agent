"""
Tests du comptage de pages lu dans le journal LaTeX.

Lancement :  python -m unittest discover tests
"""

import unittest

from cv.build_cv import _count_pages


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
