"""
Tests de l'analyse de correspondance offre / profil (cv/analysis.py) et de son intégration au
pipeline. Offre et profil fictifs, Claude simulé, dossiers temporaires.

Lancement :  python -m unittest discover tests
"""

import contextlib
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from candidate.profile import EXAMPLE_PATH, load_profile
from cv import analysis as analysis_module
from cv import pipeline
from cv.analysis import (ANALYSIS_SCHEMA, AnalysisError, analyze_fit, analyze_folder, load_analysis,
                         profile_fingerprint, requirements_from_offer, save_analysis)
from cv.build_cv import write_cv
from cv.document import build_document
from cv_fixtures import fake_draft
from test_import_cv import sha


OFFER = {
    "company": "Acme Robotics", "job_title": "Stage Vision par Ordinateur", "location": "Lyon",
    "contract_type": "Stage", "job_level": "Stage", "offer_language": "fr",
    "summary": "Stage dans l'équipe perception d'un fabricant de robots de tri.",
    "missions": ["Entraîner des modèles de détection", "Annoter des jeux de données"],
    "must_have": ["Vision par ordinateur", "Python et SQL", "Maîtrise de ROS"],
    "nice_to_have": ["Docker", "Connaissance de Kubernetes"],
    "education": "Bac+5 en informatique", "experience": "3 ans d'expérience en robotique",
    "languages": ["Anglais courant"], "soft_skills": ["Rigueur"],
    "keywords": ["PyTorch", "YOLO", "ROS"],
    "key_points": [{"point": "Vision par ordinateur", "quote": "vision par ordinateur"}],
    "practical_info": ["6 mois"], "source_url": "https://jobs.example.com/offre/1",
}


def evidence(kind, ref, why="lien direct"):
    return {"type": kind, "id": ref, "justification": why}


def part(text, status, importance="normal", proofs=(), explanation="Explication."):
    return {"text": text, "status": status, "importance": importance, "explanation": explanation,
            "evidence": list(proofs)}


def fake_answer() -> dict:
    """Réponse de Claude (ANALYSIS_SCHEMA), avec des erreurs volontaires à filtrer."""
    return {
        "overview": {
            "summary": "Stage de perception pour des robots de tri.",
            "plain_explanation": "Tu aiderais les robots à reconnaître les objets sur un tapis roulant.",
            "technologies": ["PyTorch", "YOLO", "TensorFlow"],              # TensorFlow n'est pas dans l'offre
            "skills_sought": ["Vision par ordinateur", "Python"],
            "possible_tasks": ["Par exemple, tu pourrais comparer deux modèles de détection."],
            "glossary": [{"term": "ROS", "explanation": "Logiciel qui relie les composants d'un robot."},
                         {"term": "MLOps", "explanation": "Absent de l'offre."}],
        },
        "requirements": [
            {"id": "req-1", "duplicate_of": None, "parts": [part("Vision par ordinateur", "met", "high", [
                evidence("skill", "computer vision", "« Vision par ordinateur » = « Computer Vision »"),
                evidence("experience", "example-research-company")])]},
            {"id": "req-2", "duplicate_of": None, "parts": [
                part("Python", "met", proofs=[evidence("skill", "Python")]),
                part("SQL", "partial", proofs=[evidence("skill", "SQL")])]},
            {"id": "req-3", "duplicate_of": None, "parts": [part("Maîtrise de ROS", "met", proofs=[
                evidence("skill", "ROS")])]},                                   # preuve inventée
            {"id": "req-4", "duplicate_of": None, "parts": [part("Bac+5 en informatique", "met", proofs=[
                evidence("education", "example-engineering-school")])]},
            {"id": "req-5", "duplicate_of": None, "parts": [part(
                "3 ans d'expérience en robotique", "missing", explanation="Le profil ne montre que des stages.")]},
            {"id": "req-6", "duplicate_of": None, "parts": [part("Anglais courant", "partial", proofs=[
                evidence("language", "english", "le profil indique Fluent")])]},
            {"id": "req-7", "duplicate_of": None, "parts": [part("Docker", "met", proofs=[evidence("skill", "Docker")])]},
            {"id": "req-8", "duplicate_of": None, "parts": [part("Connaissance de Kubernetes", "not_documented")]},
            {"id": "req-99", "duplicate_of": None, "parts": [part("Inventée", "met")]},
        ],
        "strengths": [
            {"title": "Détection d'objets", "explanation": "Stage en vision.", "requirement_ids": ["req-1", "req-99"],
             "evidence": [evidence("experience", "example-research-company")]},
            {"title": "Projet inventé", "explanation": "x", "requirement_ids": [],
             "evidence": [evidence("project", "projet-inexistant")]},
        ],
        "recommendations": [
            {"category": "cv", "text": "Mettre en avant le mAP.", "requirement_ids": ["req-2a", "req-99"]},
            {"category": "obstacle", "text": "Expérience demandée supérieure à la tienne.", "requirement_ids": ["req-5"]},
        ],
    }


class RequirementsTest(unittest.TestCase):

    def test_requirements_come_from_the_offer_only(self):
        requirements = requirements_from_offer(OFFER)
        self.assertEqual([(r["id"], r["category"], r["source"]) for r in requirements], [
            ("req-1", "required", "must_have"), ("req-2", "required", "must_have"), ("req-3", "required", "must_have"),
            ("req-4", "required", "education"), ("req-5", "required", "experience"), ("req-6", "required", "languages"),
            ("req-7", "preferred", "nice_to_have"), ("req-8", "preferred", "nice_to_have")])
        self.assertNotIn("Rigueur", [r["text"] for r in requirements])          # qualités personnelles non notées

    def test_exact_duplicates_are_merged(self):
        offer = {**OFFER, "must_have": ["Python", "python "], "nice_to_have": ["Python", "Git"], "education": None,
                 "experience": "", "languages": []}
        self.assertEqual([r["text"] for r in requirements_from_offer(offer)], ["Python", "Git"])


class AnalyzeFitTest(unittest.TestCase):

    def setUp(self):
        self.profile = load_profile(EXAMPLE_PATH)
        with mock.patch.object(analysis_module, "run_claude", return_value=fake_answer()) as claude:
            self.analysis = analyze_fit(OFFER, self.profile, build_document(fake_draft(), self.profile),
                                        ["Pas d'expérience en robotique."])
        self.claude = claude
        self.items = {item["id"]: item for item in self.analysis["requirements"]}

    def test_claude_receives_the_fixed_requirements_and_profile_references(self):
        prompt, stdin, schema = self.claude.call_args.args[:3]
        self.assertIs(schema, ANALYSIS_SCHEMA)
        self.assertIn('"id": "req-8"', stdin)
        self.assertIn("example-research-company (Computer Vision Intern — Example Research Company)", stdin)
        self.assertIn("example-engineering-school", stdin)
        self.assertIn("=== CANDIDATE PROFILE ===\n" + self.profile.text, stdin)
        self.assertIn("--- experience ---", stdin)                                  # contenu du CV
        self.assertIn("- Pas d'expérience en robotique.", stdin)                    # gaps de la génération
        self.assertNotIn("jobs.example.com", stdin)                                 # l'URL n'est pas envoyée
        self.assertIn("Write everything in French", prompt)

    def test_semantic_evidence_is_kept_when_its_id_exists(self):
        vision = self.items["req-1"]
        self.assertEqual(vision["status"], "met")
        self.assertEqual(vision["weight"], 2)
        self.assertEqual([(e["type"], e["id"]) for e in vision["evidence"]],
                         [("skill", "Computer Vision"), ("experience", "example-research-company")])
        self.assertEqual(vision["evidence"][1]["label"], "Computer Vision Intern — Example Research Company")
        self.assertIn("Computer Vision", vision["evidence"][0]["justification"])

    def test_invented_evidence_is_removed_and_cannot_raise_the_score(self):
        ros = self.items["req-3"]
        self.assertEqual((ros["status"], ros["evidence"]), ("not_documented", []))
        self.assertIn("Aucune preuve vérifiable", ros["explanation"])
        self.assertIn("Preuve ignorée : skill « ROS » n'existe pas dans le profil.", self.analysis["warnings"])

    def test_valid_evidence_does_not_force_met(self):
        self.assertEqual(self.items["req-6"]["status"], "partial")
        self.assertEqual(self.items["req-6"]["evidence"][0]["id"], "English")

    def test_split_requirement_keeps_its_origin_and_weight(self):
        self.assertNotIn("req-2", self.items)
        python, sql = self.items["req-2a"], self.items["req-2b"]
        self.assertEqual((python["text"], python["status"], python["weight"]), ("Python", "met", 0.5))
        self.assertEqual((sql["text"], sql["status"], sql["weight"]), ("SQL", "partial", 0.5))
        self.assertEqual((sql["parent_id"], sql["parent_text"]), ("req-2", "Python et SQL"))

    def test_missing_and_not_documented_stay_distinct(self):
        weaknesses = [(w["requirement_id"], w["kind"]) for w in self.analysis["weaknesses"]]
        self.assertEqual(weaknesses, [("req-5", "missing"), ("req-3", "not_documented"), ("req-2b", "partial"),
                                      ("req-6", "partial"), ("req-8", "not_documented")])
        self.assertEqual(self.analysis["weaknesses"][0]["explanation"], "Le profil ne montre que des stages.")

    def test_deterministic_score_without_cap(self):
        score = self.analysis["score"]
        # indispensables : (2 + 0,5 + 0,25 + 0 + 1 + 0 + 0,5) / 7 × 80 = 48,6 ; appréciées : 1 / 2 × 20 = 10
        self.assertEqual((score["value"], score["level"]), (59, "Adéquation partielle"))
        self.assertEqual(score["breakdown"]["required"]["earned"], 4.25)
        self.assertIn("Exigence indispensable non remplie : « 3 ans d'expérience en robotique ».", score["warnings"])

    def test_overview_strengths_and_recommendations_are_filtered(self):
        overview = self.analysis["overview"]
        self.assertEqual(overview["technologies"], ["PyTorch", "YOLO"])
        self.assertEqual([g["term"] for g in overview["glossary"]], ["ROS"])
        self.assertEqual(overview["missions"], OFFER["missions"])
        self.assertEqual([s["title"] for s in self.analysis["strengths"]], ["Détection d'objets"])
        self.assertEqual(self.analysis["strengths"][0]["requirement_ids"], ["req-1"])
        self.assertEqual(self.analysis["recommendations"][0]["requirement_ids"], ["req-2a"])
        self.assertIn("Évaluation ignorée : exigence « req-99 » inconnue.", self.analysis["warnings"])
        self.assertEqual(self.analysis["offer"], {"company": "Acme Robotics", "job_title": "Stage Vision par Ordinateur",
                                                  "location": "Lyon", "contract_type": "Stage",
                                                  "source_url": "https://jobs.example.com/offre/1"})
        self.assertEqual(self.analysis["profile_fingerprint"], profile_fingerprint(self.profile))
        self.assertNotIn("John", self.analysis["profile_fingerprint"])

    def test_bad_splits_duplicates_and_forgotten_requirements(self):
        answer = fake_answer()
        answer["requirements"][1]["parts"] = [part("Python", "met", proofs=[evidence("skill", "Python")]),
                                              part("Docker", "met", proofs=[evidence("skill", "Docker")])]
        answer["requirements"][3]["duplicate_of"] = "req-1"          # doublon d'une exigence indispensable : accepté
        answer["requirements"][6]["duplicate_of"] = "req-7"          # doublon de lui-même : refusé
        answer["requirements"] = [r for r in answer["requirements"] if r["id"] != "req-8"]
        with mock.patch.object(analysis_module, "run_claude", return_value=answer):
            result = analyze_fit(OFFER, self.profile)
        items = {item["id"]: item for item in result["requirements"]}
        self.assertNotIn("req-2a", items)                            # « Docker » n'est pas dans « Python et SQL »
        self.assertEqual((items["req-2"]["text"], items["req-2"]["weight"]), ("Python et SQL", 1))
        self.assertEqual((items["req-4"]["duplicate_of"], items["req-4"]["weight"]), ("req-1", 0))
        self.assertIsNone(items["req-7"]["duplicate_of"])
        self.assertEqual(items["req-8"]["status"], "not_documented")
        self.assertTrue(any("Découpage ignoré" in w for w in result["warnings"]))
        self.assertTrue(any("non évaluée" in w for w in result["warnings"]))
        self.assertNotIn("req-4", [w["requirement_id"] for w in result["weaknesses"]])

    def test_required_cannot_be_hidden_as_duplicate_of_preferred(self):
        answer = fake_answer()
        answer["requirements"][4]["duplicate_of"] = "req-8"
        with mock.patch.object(analysis_module, "run_claude", return_value=answer):
            result = analyze_fit(OFFER, self.profile)
        experience = next(i for i in result["requirements"] if i["id"] == "req-5")
        self.assertEqual((experience["duplicate_of"], experience["weight"]), (None, 1))

    def test_unavailable_score_when_the_offer_has_too_few_requirements(self):
        offer = {**OFFER, "must_have": [], "education": None, "experience": None, "languages": [], "nice_to_have": ["Git"]}
        answer = fake_answer()
        answer["requirements"] = [{"id": "req-1", "duplicate_of": None, "parts": [part("Git", "met", proofs=[
            evidence("skill", "Git")])]}]
        with mock.patch.object(analysis_module, "run_claude", return_value=answer):
            result = analyze_fit(offer, self.profile)
        self.assertIsNone(result["score"]["value"])
        self.assertIn("Score non calculé", result["score"]["explanation"][0])


class FolderTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.profile = load_profile(EXAMPLE_PATH)

    def make_cv(self, with_cv_json=True) -> Path:
        main_tex = write_cv(build_document(fake_draft(), self.profile), OFFER, applications_dir=self.folder)
        if not with_cv_json:
            (main_tex.parent / "cv.json").unlink()
        return main_tex.parent

    def test_analysis_is_saved_with_the_application_without_touching_the_cv(self):
        folder = self.make_cv()
        before = {name: sha(folder / name) for name in ("cv.json", "offer.json", "selection.json")}
        profile_before = sha(EXAMPLE_PATH)
        with mock.patch.object(analysis_module, "run_claude", return_value=fake_answer()) as claude:
            result = analyze_folder(folder, self.profile)
        self.assertEqual(load_analysis(folder), result)
        self.assertEqual(result["status"], "completed")
        self.assertIn("--- experience ---", claude.call_args.args[1])
        self.assertEqual({name: sha(folder / name) for name in before}, before)
        self.assertEqual(sha(EXAMPLE_PATH), profile_before)
        self.assertEqual([p.name for p in folder.glob("*.tmp")], [])

    def test_older_cv_without_cv_json_uses_offer_and_selection(self):
        folder = self.make_cv(with_cv_json=False)
        with mock.patch.object(analysis_module, "run_claude", return_value=fake_answer()) as claude:
            analyze_folder(folder, self.profile)
        stdin = claude.call_args.args[1]
        self.assertIn("=== CV ===\n(absent)", stdin)
        self.assertIn("- Pas d'expérience en robotique industrielle.", stdin)       # gaps de selection.json

    def test_missing_offer_and_unreadable_analysis(self):
        with self.assertRaises(AnalysisError):
            analyze_folder(self.folder, self.profile)
        self.assertIsNone(load_analysis(self.folder))
        (self.folder / "analysis.json").write_text("{pas du json", encoding="utf-8")
        self.assertEqual(load_analysis(self.folder)["status"], "failed")
        save_analysis(self.folder, {"status": "completed", "score": {}})
        self.assertEqual(load_analysis(self.folder)["status"], "completed")


class PipelineTest(unittest.TestCase):
    """L'analyse est faite après la compilation ; son échec ne fait jamais perdre le CV."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.profile = load_profile(EXAMPLE_PATH)

    def run_pipeline(self, **patches):
        def fake_compile(main_tex):
            pdf = main_tex.parent / "build" / f"{main_tex.stem}.pdf"
            pdf.parent.mkdir(exist_ok=True)
            pdf.write_bytes(b"%PDF")
            return pdf, 1

        steps = []
        with mock.patch.object(pipeline, "read_job", return_value={"url": "u", "title": "t", "text": "offre"}), \
             mock.patch.object(pipeline, "analyze_job", return_value=copy.deepcopy(OFFER)), \
             mock.patch.object(pipeline, "generate_cv", return_value=build_document(fake_draft(), self.profile)), \
             mock.patch.object(pipeline, "verify_cv", return_value=[]), \
             mock.patch.object(pipeline, "compile_cv", side_effect=fake_compile), \
             mock.patch.multiple(pipeline, **patches) if patches else contextlib.nullcontext():
            result = pipeline.generate_from_url("https://jobs.example.com/1", self.profile,
                                                on_step=lambda step, **d: steps.append(step), applications_dir=self.folder)
        return result, steps

    def test_analysis_is_the_last_step(self):
        with mock.patch.object(analysis_module, "run_claude", return_value=fake_answer()):
            result, steps = self.run_pipeline()
        self.assertEqual(steps[-2:], ["compile", "analyze_fit"])
        self.assertEqual(result.analysis["status"], "completed")
        self.assertEqual(load_analysis(result.folder)["score"]["value"], result.analysis["score"]["value"])

    def test_analysis_failure_keeps_the_cv(self):
        failing = mock.Mock(side_effect=RuntimeError("Claude n'a pas répondu."))
        result, steps = self.run_pipeline(analyze_folder=failing)
        self.assertEqual(result.analysis["status"], "failed")
        self.assertEqual(result.analysis["error"]["problems"], ["Claude n'a pas répondu."])
        self.assertEqual(load_analysis(result.folder)["status"], "failed")
        self.assertTrue(result.pdf.exists())
        self.assertTrue((result.folder / "cv.json").exists())

        unexpected = mock.Mock(side_effect=KeyError("détail interne"))
        result, _ = self.run_pipeline(analyze_folder=unexpected)
        self.assertEqual(result.analysis["error"]["problems"], ["KeyError"])          # pas de détail interne


if __name__ == "__main__":
    unittest.main()
