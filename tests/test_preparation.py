"""
Tests de la préparation approfondie à l'entretien (interview/research.py, interview/preparation.py).
Offre et profil fictifs, modèle simulé (aucun appel réel, aucune recherche web), dossiers temporaires.

Lancement :  python -m unittest discover tests
"""

import copy
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from candidate.profile import EXAMPLE_PATH, load_profile
from cv import analysis as analysis_module
from cv.analysis import analyze_fit, failed_analysis, profile_references, save_analysis
from cv.document import build_document
from cv_fixtures import fake_draft
from interview.preparation import (PREPARATION_FILE, PreparationError, _interview_questions, compact_profile,
                                   load_preparation, prepare_folder, question_target)
from interview.research import RESEARCH_FILE, load_research, research_company, validate_research
from llm.claude_cli import WebPage
from llm.structured import StructuredResult
from test_analysis import OFFER, fake_answer, old_interview_questions
from test_import_cv import sha


TODAY = date(2026, 10, 22)
PAGES = [
    WebPage("https://www.acme-robotics.example/about/", "fetched",
            "Acme Robotics conçoit des robots de tri pour 120 centres logistiques en Europe."),
    WebPage("https://press.example.org/acme-levee", "search", "Acme Robotics lève 30 millions d'euros (mars 2026)."),
    WebPage("https://press.example.org/acme-2023", "search", "Acme Robotics ouvre un site à Lyon en 2023."),
]


def fact(topic, text, url, published=None, use="Utile pour parler des clients du poste."):
    return {"topic": topic, "text": text, "source_url": url, "source_title": "Titre", "published_at": published,
            "interview_use": use}


def research_answer(**identification) -> dict:
    return {
        "identification": {"status": "identified", "official_website": "https://acme-robotics.example",
                           "note": "", **identification},
        "facts": [
            fact("activity", "Acme Robotics conçoit des robots de tri pour 120 centres logistiques.",
                 "https://acme-robotics.example/about"),
            fact("news", "Acme Robotics a levé 30 millions d'euros.", "https://press.example.org/acme-levee", "2026-03"),
            fact("news", "Acme Robotics a levé 45 millions d'euros.", "https://press.example.org/acme-levee", "2026-03"),
            fact("news", "Acme Robotics a ouvert un site à Lyon.", "https://press.example.org/acme-2023", "2023-05"),
            fact("news", "Acme prépare une introduction en bourse.", "https://press.example.org/acme-levee", None),
            fact("clients", "Acme travaille pour un grand distributeur.", "https://inventee.example.com/page"),
            fact("products", "Acme vend un robot de tri.", "https://www.google.com/search?q=acme"),
            fact("activity", "acme robotics conçoit des robots de tri pour 120 centres logistiques",
                 "https://acme-robotics.example/about"),
            fact("positioning", "Acme se présente comme spécialiste du tri.", "https://acme-robotics.example/about",
                 use=" "),
        ],
    }


def fake_generate(research=None, answer=None, calls=None, research_error=None, preparation_error=None):
    """Remplace generate_structured : réponse de recherche (web) ou de préparation selon la demande."""

    def generate(request):
        if calls is not None:
            calls.append(request)
        if request.web_research:
            if research_error:
                raise research_error
            return StructuredResult(research or research_answer(), PAGES)
        if preparation_error:
            raise preparation_error
        return StructuredResult(answer or preparation_answer())
    return generate


def preparation_answer() -> dict:
    """Réponse de préparation (PREPARATION_SCHEMA), avec des erreurs volontaires à filtrer."""
    new = {"kind": "motivation", "question": "Qu'est-ce qui vous attire chez Acme Robotics ?", "purpose": "Motivation.",
           "answer_guidance": ["Relier la levée de fonds au projet du stage."], "evidence": [],
           "topics_to_review": [], "requirement_ids": [], "fact_ids": ["w2", "w99"]}
    return {
        "priorities": [
            {"title": "Vision par ordinateur", "why": "Exigence essentielle de l'offre.", "actions": ["Réviser le mAP."],
             "requirement_ids": ["req-1", "req-99"], "fact_ids": ["o1"]},
            {"title": "Sans justification", "why": " ", "actions": [], "requirement_ids": [], "fact_ids": []},
        ],
        "questions": {
            "keep": ["q1", "q2", "q2", "q42", "x"],
            "new": [
                new,
                {**new, "question": "Parlez-moi de votre stage en vision par ordinateur."},     # doublon d'une gardée
                {**new, "kind": "experience", "question": "Racontez votre stage chez Inventé.",
                 "evidence": [{"type": "experience", "id": "experience-inventee", "justification": ""}]},
            ],
        },
        "knowledge": [
            {"topic": "ROS", "why": "« Maîtrise de ROS »", "explanation": "Middleware robotique : nœuds, topics.",
             "check_points": ["Savoir expliquer un topic."], "requirement_ids": ["req-3"]},
            {"topic": "ros", "why": "doublon", "explanation": "x", "check_points": [], "requirement_ids": []},
        ],
        "experiences": [
            {"evidence": {"type": "experience", "id": "example-research-company"}, "angle": "Détection d'objets.",
             "key_points": ["mAP de 0,61 à 0,74."], "question_refs": ["q2", "n1", "n3"], "requirement_ids": ["req-1"]},
            {"evidence": {"type": "project", "id": "projet-inexistant"}, "angle": "x", "key_points": ["x"],
             "question_refs": [], "requirement_ids": []},
            {"evidence": {"type": "project", "id": "face-recognition"}, "angle": "x", "key_points": [],
             "question_refs": [], "requirement_ids": []},
        ],
        "vigilance": [
            {"requirement_ids": ["req-8"], "concern": "Kubernetes n'apparaît pas.", "how_to_address": ["Ne le citer que si…"]},
            {"requirement_ids": ["req-5"], "concern": "Expérience en robotique insuffisante.", "how_to_address": ["Reconnaître."]},
            {"requirement_ids": ["req-1"], "concern": "Vision : remplie.", "how_to_address": []},
            {"requirement_ids": ["req-2"], "concern": "SQL partiel.", "how_to_address": []},
            {"requirement_ids": [], "concern": "Stage de 6 mois.", "how_to_address": []},
        ],
    }


def build_analysis(profile) -> dict:
    """Analyse au format actuel : ni questions d'entretien ni recommandations."""
    with mock.patch.object(analysis_module, "run_claude", return_value=fake_answer()):
        return analyze_fit(OFFER, profile, build_document(fake_draft(), profile), ["Pas d'expérience en robotique."])


def old_analysis(profile) -> dict:
    """Analyse enregistrée avant la séparation : avec ses questions d'entretien et ses recommandations."""
    analysis = build_analysis(profile)
    analysis["interview_questions"] = _interview_questions(old_interview_questions(), profile_references(profile.data),
                                                           analysis["requirements"], [])
    analysis["recommendations"] = [{"category": "obstacle", "text": "Expérience demandée supérieure à la tienne.",
                                    "requirement_ids": ["req-5"]}]
    return analysis


class ResearchTest(unittest.TestCase):

    def test_only_verifiable_facts_are_kept(self):
        research = validate_research(research_answer(), PAGES, OFFER, TODAY)
        self.assertEqual(research["status"], "done")
        self.assertEqual(research["official_website"], "https://acme-robotics.example")
        self.assertEqual([f["text"] for f in research["facts"]], [
            "Acme Robotics conçoit des robots de tri pour 120 centres logistiques.",
            "Acme Robotics a levé 30 millions d'euros."])
        sources = {s["id"]: s for s in research["sources"]}
        first, second = (sources[f["source_ids"][0]] for f in research["facts"])
        self.assertEqual((first["url"], first["official"], first["access"]),
                         ("https://www.acme-robotics.example/about", True, "fetched"))
        self.assertEqual((second["official"], second["published_at"], second["access"], second["accessed_at"]),
                         (False, "2026-03", "search", "2026-10-22"))
        warnings = " ".join(research["warnings"])
        for expected in ("chiffres absents", "trop ancienne", "source non consultée"):
            self.assertIn(expected, warnings)

    def test_unidentified_company_gives_no_facts(self):
        for status, expected in (("ambiguous", "ambiguous"), ("not_found", "not_found")):
            research = validate_research(research_answer(status=status, note="Deux sociétés Acme."), PAGES, OFFER, TODAY)
            self.assertEqual((research["status"], research["facts"]), (expected, []))
        self.assertEqual(validate_research(research_answer(), [], OFFER, TODAY)["status"], "unavailable")

    def test_research_never_receives_the_profile_and_never_raises(self):
        calls = []
        research_company(OFFER, TODAY, fake_generate(calls=calls))
        request = calls[0]
        self.assertTrue(request.web_research)
        self.assertEqual(request.tier, "light")
        self.assertEqual(set(json.loads(request.input_text)),
                         {"company", "job_title", "location", "offer_summary", "offer_domain", "today"})
        profile_text = load_profile(EXAMPLE_PATH).text
        for private in ("john.doe@example.com", "Example Research Company", "John"):
            self.assertIn(private, profile_text)
            self.assertNotIn(private, request.input_text)

        failed = research_company(OFFER, TODAY, fake_generate(research_error=RuntimeError("limite atteinte")))
        self.assertEqual(failed["status"], "unavailable")
        self.assertIn("limite atteinte", failed["warnings"][0])
        calls.clear()
        self.assertEqual(research_company({**OFFER, "company": None}, TODAY, fake_generate(calls=calls))["status"], "skipped")
        self.assertEqual(calls, [])


class PreparationFolderTestCase(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.profile = load_profile(EXAMPLE_PATH)
        self.app = self.folder / "acme"
        self.app.mkdir()
        (self.app / "offer.json").write_text(json.dumps(OFFER, ensure_ascii=False), encoding="utf-8")
        self.analysis = old_analysis(self.profile)
        save_analysis(self.app, self.analysis)

    def prepare(self, calls=None, **fakes):
        return prepare_folder(self.app, self.profile, generate=fake_generate(calls=calls, **fakes), today=TODAY)


class PreparationTest(PreparationFolderTestCase):

    def test_existing_questions_are_reused_and_new_ones_checked(self):
        preparation = self.prepare()
        questions = preparation["questions"]
        existing = self.analysis["interview_questions"]
        self.assertEqual([q["id"] for q in questions], ["q1", "q2", "q3"])
        self.assertEqual({k: v for k, v in questions[0].items() if k not in ("id", "origin", "fact_ids")}, existing[0])
        self.assertEqual([q["origin"] for q in questions], ["analysis", "analysis", "preparation"])
        self.assertEqual(questions[2]["fact_ids"], ["w2"])                   # fait inconnu retiré
        self.assertIn("Seulement 3 question(s)", " ".join(preparation["warnings"]))

    def test_sections_are_checked_against_the_analysis_and_the_profile(self):
        p = self.prepare()
        self.assertEqual([x["title"] for x in p["priorities"]], ["Vision par ordinateur"])
        self.assertEqual(p["priorities"][0]["requirement_ids"], ["req-1"])
        self.assertEqual([k["topic"] for k in p["knowledge"]], ["ROS"])
        self.assertEqual(len(p["experiences"]), 1)                           # preuve inventée, sans point : retirées
        experience = p["experiences"][0]
        self.assertEqual(experience["evidence"]["label"], "Computer Vision Intern — Example Research Company")
        self.assertEqual(experience["question_ids"], ["q2", "q3"])           # n1 renuméroté, n3 rejetée
        kinds = [(v["kind"], v["requirement_ids"]) for v in p["vigilance"]]
        self.assertEqual(kinds, [("missing", ["req-5"]), ("not_documented", ["req-8"]), ("partial", ["req-2"]),
                                 ("other", [])])                             # exigence remplie : point retiré
        self.assertEqual(p["company"]["facts"][0]["origin"], "offer")
        self.assertEqual([f["origin"] for f in p["company"]["facts"][1:]], ["web", "web"])
        self.assertEqual(p["analysis_generated_at"], self.analysis["generated_at"])

    def test_two_calls_at_most_then_files_are_final(self):
        calls = []
        analysis_before = sha(self.app / "analysis.json")
        self.prepare(calls=calls)
        self.assertEqual([c.web_research for c in calls], [True, False])
        self.assertEqual(calls[1].tier, "default")
        self.assertIsNotNone(load_preparation(self.app))
        self.assertIsNotNone(load_research(self.app))
        self.assertEqual(sha(self.app / "analysis.json"), analysis_before)   # l'analyse n'est jamais réécrite

    def test_saved_research_is_reused_when_the_preparation_fails(self):
        calls = []
        with self.assertRaises(RuntimeError):
            self.prepare(calls=calls, preparation_error=RuntimeError("Claude n'a pas répondu."))
        self.assertFalse((self.app / PREPARATION_FILE).exists())             # rien d'écrit en cas d'échec
        self.assertTrue((self.app / RESEARCH_FILE).exists())
        calls.clear()
        self.prepare(calls=calls)
        self.assertEqual([c.web_research for c in calls], [False])           # un seul appel au nouvel essai

    def test_failed_research_is_not_cached_and_does_not_block(self):
        calls = []
        preparation = self.prepare(calls=calls, research_error=RuntimeError("délai dépassé"))
        self.assertEqual(preparation["company"]["research_status"], "unavailable")
        self.assertEqual([f["origin"] for f in preparation["company"]["facts"]], ["offer"])
        self.assertFalse((self.app / RESEARCH_FILE).exists())

    def test_a_completed_analysis_is_required(self):
        save_analysis(self.app, failed_analysis("L'analyse a échoué", ["x"]))
        calls = []
        with self.assertRaises(PreparationError):
            self.prepare(calls=calls)
        (self.app / "analysis.json").unlink()
        with self.assertRaises(PreparationError):
            self.prepare(calls=calls)
        (self.app / "offer.json").unlink()
        with self.assertRaises(PreparationError):
            self.prepare(calls=calls)
        self.assertEqual(calls, [])

    def test_new_analysis_without_questions_gets_its_questions_from_the_preparation(self):
        analysis = build_analysis(self.profile)
        self.assertNotIn("interview_questions", analysis)
        save_analysis(self.app, analysis)
        calls = []
        preparation = self.prepare(calls=calls)
        self.assertEqual(len(calls), 2)                                      # pas d'appel supplémentaire
        self.assertNotIn('=== EXISTING QUESTIONS ===', calls[1].input_text)      # blocs vides non envoyés
        self.assertNotIn('=== RECOMMENDATIONS ===', calls[1].input_text)
        self.assertIn('=== QUESTION TARGET ===\n{"min": 5, "max": 8}', calls[1].input_text)
        questions = preparation["questions"]
        self.assertEqual([q["origin"] for q in questions], ["preparation", "preparation"])
        self.assertEqual([q["id"] for q in questions], ["q1", "q2"])
        self.assertEqual(preparation["experiences"][0]["question_ids"], ["q1"])   # n1 -> q1 ; q2 et n3 inconnues

    def test_unreadable_preparation_can_be_redone(self):
        (self.app / PREPARATION_FILE).write_text("{pas du json", encoding="utf-8")
        self.assertIsNone(load_preparation(self.app))


class PreparationInputTest(PreparationFolderTestCase):

    def test_input_is_compact_and_without_personal_data(self):
        calls = []
        self.prepare(calls=calls)
        text = calls[1].input_text
        self.assertIn('=== EXISTING QUESTIONS ===\n[{"id": "q1"', text)          # ancienne analyse : blocs envoyés
        self.assertIn('=== RECOMMENDATIONS ===\n[{"id": "r1", "category": "obstacle"', text)
        for private in ("john.doe@example.com", "+33 6", "1 rue Exemple", "2000-01-01", "linkedin", "salary",
                        "disability", "Tennis"):
            self.assertNotIn(private, text)
        self.assertNotIn("https://", text.split("=== COMPANY FACTS ===")[1].split("===")[0])   # pas d'URL
        self.assertNotIn("answer_guidance", text)                            # recopiées par Python, pas renvoyées
        self.assertIn('"id": "q1"', text)
        self.assertIn("Improved object-detection mAP", text)                 # élément cité : en détail
        self.assertIn("6 months minimum", text)                              # disponibilités utiles

    def test_profile_elements_not_cited_are_on_one_line(self):
        compact = compact_profile(self.profile.data, {("experience", "example-research-company")})
        detailed, short = compact["experiences"][0], compact["experiences"][1]
        self.assertIn("achievements", detailed)
        self.assertNotIn("priority", detailed)
        self.assertEqual(set(short), {"id", "title", "company", "start_date", "end_date"})
        self.assertNotIn("personal", compact)

    def test_question_target(self):
        self.assertEqual(question_target(0), {"min": 5, "max": 8})
        self.assertEqual(question_target(3), {"min": 2, "max": 5})
        self.assertEqual(question_target(6), {"min": 0, "max": 2})
        self.assertEqual(question_target(8), {"min": 0, "max": 0})


if __name__ == "__main__":
    unittest.main()
