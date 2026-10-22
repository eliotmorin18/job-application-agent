"""
Tests du score d'adéquation (cv/fit_score.py) : calcul déterministe, sans Claude.

Lancement :  python -m unittest discover tests
"""

import unittest

from cv.fit_score import compute_score, level_for


def item(status, category="required", weight=1, text="x"):
    return {"text": text, "category": category, "status": status, "weight": weight}


class ScoreTest(unittest.TestCase):

    def test_credits_and_80_20_weighting(self):
        score = compute_score([item("met"), item("partial"), item("not_documented"), item("met"),
                               item("met", "preferred"), item("missing", "preferred")])
        # indispensables : (1 + 0,5 + 0 + 1) / 4 = 0,625 -> 50 ; appréciées : 1 / 2 -> 10
        self.assertEqual(score["value"], 60)
        self.assertEqual(score["breakdown"]["required"], {"earned": 2.5, "max": 4, "count": 4, "weight": 80, "points": 50.0})
        self.assertEqual(score["breakdown"]["preferred"]["points"], 10.0)
        self.assertEqual(score["level"], "Bonne adéquation")

    def test_important_requirements_count_twice(self):
        light = compute_score([item("met"), item("not_documented"), item("met", "preferred")])
        heavy = compute_score([item("met", weight=2), item("not_documented"), item("met", "preferred")])
        self.assertEqual((light["value"], heavy["value"]), (60, 73))      # 80 × 1/2 + 20 ; 80 × 2/3 + 20

    def test_split_parts_share_the_weight_and_duplicates_do_not_count(self):
        whole = compute_score([item("partial"), item("met"), item("met")])
        split = compute_score([item("met", weight=0.5), item("not_documented", weight=0.5), item("met"), item("met")])
        self.assertEqual(whole["value"], split["value"])                   # « Python et SQL » séparé = même poids
        with_duplicate = compute_score([item("met"), item("met"), item("met"), item("missing", weight=0)])
        self.assertEqual(with_duplicate["value"], 100)

    def test_no_preferred_requirement(self):
        score = compute_score([item("met"), item("partial"), item("met")])
        self.assertEqual(score["value"], 83)                               # 100 × 2,5 / 3
        self.assertEqual(score["breakdown"]["required"]["weight"], 100)
        self.assertIn("Aucune exigence appréciée", " ".join(score["explanation"]))

    def test_missing_gives_a_warning_but_no_cap(self):
        score = compute_score([item("met")] * 8 + [item("missing", text="Bac+5 obtenu")])
        self.assertEqual(score["value"], 89)                               # pas de plafond à 60
        self.assertIn("Exigence indispensable non remplie : « Bac+5 obtenu ».", score["warnings"])

    def test_missing_and_not_documented_are_distinguished(self):
        score = compute_score([item("met"), item("missing"), item("not_documented"), item("not_documented")])
        self.assertEqual(score["status_counts"], {"met": 1, "partial": 0, "not_documented": 2, "missing": 1})
        self.assertEqual(len(score["warnings"]), 2)
        self.assertIn("non documentée(s)", score["warnings"][1])
        self.assertIn("pas forcément absentes", score["warnings"][1])
        self.assertIn("2 non documentée(s) dans le profil, 1 non remplie(s)", " ".join(score["explanation"]))

    def test_unavailable_score_rather_than_a_misleading_one(self):
        for items in ([], [item("met", "preferred")] * 5, [item("met"), item("met", "preferred")]):
            with self.subTest(len(items)):
                score = compute_score(items)
                self.assertIsNone(score["value"])
                self.assertIsNone(score["level"])
                self.assertTrue(score["explanation"][0].startswith("Score non calculé"))

    def test_levels_and_disclaimer(self):
        self.assertEqual([level_for(v) for v in (0, 39, 40, 59, 60, 79, 80, 100, None)],
                         ["Adéquation faible", "Adéquation faible", "Adéquation partielle", "Adéquation partielle",
                          "Bonne adéquation", "Bonne adéquation", "Forte adéquation", "Forte adéquation", None])
        self.assertIn("pas une probabilité d'être recruté", compute_score([item("met")] * 3)["explanation"][-1])

    def test_deterministic(self):
        items = [item("met", weight=2), item("partial"), item("missing"), item("not_documented", "preferred")]
        self.assertEqual(compute_score(items), compute_score(list(items)))


if __name__ == "__main__":
    unittest.main()
