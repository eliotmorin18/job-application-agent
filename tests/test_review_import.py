"""
Tests de la comparaison d'un import de CV avec le profil candidat.
Tout se passe dans des fichiers temporaires ; aucun appel à Claude.

Lancement :  python -m unittest discover tests
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from candidate.profile import CANDIDATE_PATH
from candidate.review_import import ReviewError, review_import


PROFILE = """personal:
  first_name: Jane
  last_name: Doe
  email: jane.doe@example.com
  city: Paris

education:
  - school: Institut Polytechnique de Paris - Télécom SudParis
    degree: Diplôme d'ingénieur
    start_date: "2023-09"
  - id: ljubljana
    school: University of Ljubljana - Faculty of Computer Science
    start_date: "2025-10"

experiences:
  - id: cnrs-aubay
    company: CNRS Foundation - via Aubay
    title: AI & Computer Vision Research Intern
    start_date: "2026-02"
    location: Paris, France
    skills:
      - Python
  - id: acme
    company: Acme
    title: Data Analyst
    start_date: "2022-01"

projects:
  - id: cassiopee
    name: Cassiopée
  - id: pitch
    name: Start in Saclay Pitch Night

skills:
  programming:
    - Python
    - SQL
  tools:
    - Git

languages:
  - language: French
    level: Native
  - language: English
    level: C1 / Fluent

interests:
  - Tennis
  - Skiing
"""


def extraction(**profile) -> dict:
    base = {"personal": {}, "experiences": [], "projects": [], "education": [], "skills": {},
            "languages": [], "interests": []}
    base.update(profile)
    return {"status": "proposal", "source_pdf": "cv.pdf", "extracted_at": "2026-10-20T17:45:40",
            "profile": base, "warnings": ["Les projets n'ont aucune date."]}


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class ReviewImportTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.profile = self.folder / "candidate.yaml"
        self.profile.write_text(PROFILE, encoding="utf-8")

    def review(self, data: dict, profile_text: str | None = None) -> dict:
        if profile_text is not None:
            self.profile.write_text(profile_text, encoding="utf-8")
        path = self.folder / "import.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return review_import(path, self.profile)

    # ---------- expériences, projets, formations ----------

    def test_new_experience(self):
        result = self.review(extraction(experiences=[{"company": "Dassault Systèmes", "title": "Stagiaire IA", "start_date": "2027"}]))
        proposal = result["experiences"][0]
        self.assertEqual(proposal["status"], "new")
        self.assertEqual(proposal["matches"], [])
        self.assertEqual(proposal["proposal_id"], "experiences-1")

    def test_probable_duplicate_keeps_the_existing_id(self):
        result = self.review(extraction(experiences=[{
            "company": "Fondation CNRS (Aubay)", "title": "Stagiaire Recherche IA", "start_date": "2026",
            "location": "Paris", "responsibilities": ["État de l'art"], "uncertain_fields": ["start_date"],
        }]))
        proposal = result["experiences"][0]
        self.assertEqual(proposal["status"], "probable_duplicate")
        match = proposal["matches"][0]
        self.assertEqual(match["id"], "cnrs-aubay")
        self.assertIn("même année de début", match["reasons"])
        self.assertEqual(proposal["uncertain_fields"], ["start_date"])        # conservé depuis l'extraction
        self.assertNotIn("uncertain_fields", proposal["data"])
        # Ce qui pourrait corriger ou compléter l'expérience existante
        self.assertEqual(match["differences"]["responsibilities"]["change"], "missing_in_profile")
        self.assertEqual(match["differences"]["location"]["change"], "different")

    def test_same_name_in_another_order_is_probable(self):
        proposal = self.review(extraction(projects=[{"name": "Pitch Night Start In Saclay"}]))["projects"][0]
        self.assertEqual(proposal["status"], "probable_duplicate")
        self.assertEqual(proposal["matches"][0]["id"], "pitch")
        self.assertIn("même nom", proposal["matches"][0]["reasons"])

    def test_close_name_without_confirmation_is_only_possible(self):
        # « Projet Cassiopée » contient « Cassiopée », mais rien ne le confirme (pas de date)
        proposal = self.review(extraction(projects=[{"name": "Projet Cassiopée"}]))["projects"][0]
        self.assertEqual(proposal["status"], "possible_duplicate")
        self.assertEqual(proposal["matches"][0]["id"], "cassiopee")
        self.assertNotIn("même nom", proposal["matches"][0]["reasons"])

    def test_partly_similar_name_is_possible(self):
        proposal = self.review(extraction(education=[{"school": "Université de Ljubljana – Faculté d'Informatique", "start_date": "2025"}]))["education"][0]
        self.assertEqual(proposal["status"], "possible_duplicate")
        self.assertEqual(proposal["matches"][0]["id"], "ljubljana")

    def test_same_job_same_year_under_another_company_name_is_possible(self):
        proposal = self.review(extraction(experiences=[{"company": "Acme Group International", "title": "Data Analyst", "start_date": "2022"}]))["experiences"][0]
        self.assertIn(proposal["status"], ("possible_duplicate", "probable_duplicate"))
        self.assertEqual(proposal["matches"][0]["id"], "acme")

    def test_old_education_without_id_is_matched(self):
        proposal = self.review(extraction(education=[{"school": "Institut Polytechnique de Paris – Télécom SudParis", "start_date": "2023"}]))["education"][0]
        self.assertEqual(proposal["status"], "probable_duplicate")
        self.assertIsNone(proposal["matches"][0]["id"])      # formation existante sans id : signalé tel quel

    # ---------- compétences, langues, centres d'intérêt ----------

    def test_skills(self):
        skills = self.review(extraction(skills={"programming": ["python", "Rust"], "devops": ["Git", "Docker"]}))["skills"]
        by_name = {review["skill"]: review for review in skills}
        self.assertEqual(by_name["python"]["status"], "duplicate")                     # casse ignorée
        self.assertEqual(by_name["Rust"]["status"], "new")
        self.assertEqual(by_name["Rust"]["category_in_profile"], "programming")
        self.assertEqual(by_name["Git"]["status"], "duplicate")
        self.assertEqual(by_name["Git"]["note"], "déjà présente dans une autre catégorie")
        self.assertIsNone(by_name["Docker"]["category_in_profile"])                    # catégorie devops absente du profil

    def test_languages_with_simple_equivalences(self):
        languages = self.review(extraction(languages=[
            {"language": "Français", "level": "Langue maternelle"}, {"language": "Anglais", "level": "C1"},
            {"language": "english"}, {"language": "Espagnol", "level": "A2"}, {"language": "French", "level": "B2"},
        ]))["languages"]
        self.assertEqual([review["status"] for review in languages], ["duplicate", "duplicate", "duplicate", "new", "duplicate"])
        self.assertEqual(languages[0]["note"], "équivalent de « French »")
        self.assertNotIn("level_differs", languages[0])        # « Langue maternelle » = « Native »
        self.assertNotIn("level_differs", languages[1])        # « C1 » = « C1 / Fluent »
        self.assertTrue(languages[4]["level_differs"])         # « B2 » ≠ « Native »

    def test_interests(self):
        interests = self.review(extraction(interests=["tennis", "Ski", "Échecs", "Tennis de table"]))["interests"]
        self.assertEqual([review["status"] for review in interests], ["duplicate", "duplicate", "new", "possible_duplicate"])
        self.assertEqual(interests[1]["matches"], ["Skiing"])

    # ---------- coordonnées et champs absents ----------

    def test_personal_fields(self):
        personal = self.review(extraction(personal={"first_name": "Jane", "email": "JANE.DOE@example.com",
                                                    "city": "Lyon", "phone": "+33 6 00 00 00 00", "uncertain_fields": ["city"]}))["personal"]
        by_field = {review["field"]: review for review in personal}
        self.assertEqual(by_field["first_name"]["status"], "same")
        self.assertEqual(by_field["email"]["status"], "same")
        self.assertEqual(by_field["city"]["status"], "different")
        self.assertTrue(by_field["city"]["uncertain"])
        self.assertEqual(by_field["phone"]["status"], "missing_in_profile")
        self.assertNotIn("last_name", by_field)               # absent de l'extraction : pas proposé

    def test_missing_sections_in_the_extraction(self):
        result = self.review({"status": "proposal", "profile": {"experiences": [{"company": "Acme", "title": "Data Analyst"}]}})
        for section in ("projects", "education", "skills", "languages", "interests", "personal"):
            self.assertEqual(result[section], [], section)
        self.assertEqual(result["warnings"], [])

    def test_empty_existing_profile(self):
        result = self.review(extraction(
            experiences=[{"company": "Acme", "title": "Data Analyst"}], projects=[{"name": "Robot"}],
            education=[{"school": "MIT"}], skills={"programming": ["Python"]},
            languages=[{"language": "French"}], interests=["Tennis"], personal={"first_name": "Jane"},
        ), "personal:\n  first_name: Jane\n  last_name: Doe\n")
        for section in ("experiences", "projects", "education", "skills", "languages", "interests"):
            self.assertTrue(all(entry["status"] == "new" for entry in result[section]), section)
        self.assertEqual(result["summary"], {"new": 6})

    # ---------- structure générale ----------

    def test_output_structure_for_the_frontend(self):
        result = self.review(extraction(experiences=[{"company": "Acme", "title": "Data Analyst", "start_date": "2022"}]))
        self.assertEqual(set(result), {"source", "warnings", "personal", "experiences", "projects", "education",
                                       "skills", "languages", "interests", "summary"})
        self.assertEqual(result["warnings"], ["Les projets n'ont aucune date."])
        self.assertEqual(result["source"]["source_pdf"], "cv.pdf")
        json.dumps(result)   # entièrement sérialisable en JSON pour la future API

    def test_nothing_is_modified(self):
        before_profile, before_private = sha(self.profile), sha(CANDIDATE_PATH)
        self.review(extraction(experiences=[{"company": "Nouvelle", "title": "X"}], skills={"x": ["Y"]}))
        self.assertEqual(sha(self.profile), before_profile)
        self.assertEqual(sha(CANDIDATE_PATH), before_private)

    def test_unreadable_import_file(self):
        with self.assertRaises(ReviewError):
            review_import(self.folder / "absent.json", self.profile)
        bad = self.folder / "bad.json"
        bad.write_text("{pas du json", encoding="utf-8")
        with self.assertRaises(ReviewError):
            review_import(bad, self.profile)
        bad.write_text('{"status": "proposal"}', encoding="utf-8")
        with self.assertRaises(ReviewError) as context:
            review_import(bad, self.profile)
        self.assertIn("section « profile » manquante", str(context.exception))


if __name__ == "__main__":
    unittest.main()
