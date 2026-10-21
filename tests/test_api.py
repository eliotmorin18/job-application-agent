"""
Tests de l'API FastAPI (api/main.py), sur une copie temporaire du profil d'exemple.
Le vrai profil n'est jamais lu ni modifié ; Claude est remplacé par un faux (mock).

Lancement :  python -m unittest discover tests
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from fastapi.testclient import TestClient

from api import main
from candidate.profile import CANDIDATE_PATH, EXAMPLE_PATH
from candidate import extract_profile
from test_import_cv import CV_LINES, fake_claude_answer, make_pdf, sha


# Une ancienne formation sans id, pour tester l'adressage « index-N »
LEGACY_EDUCATION = """
  - school: Legacy High School
    degree: Baccalaureate
    start_date: "2017"
    end_date: "2020"
"""

REAL_PROFILE_HASH = None


def setUpModule():
    global REAL_PROFILE_HASH
    REAL_PROFILE_HASH = sha(CANDIDATE_PATH)


def tearDownModule():
    assert sha(CANDIDATE_PATH) == REAL_PROFILE_HASH, "le vrai profil a été modifié"


class ApiTestCase(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)

        text = EXAMPLE_PATH.read_text(encoding="utf-8")
        text = text.replace("\nexperiences:\n", LEGACY_EDUCATION + "\nexperiences:\n", 1)
        self.profile = self.folder / "candidate.yaml"
        self.profile.write_text(text, encoding="utf-8")

        self.imports, self.extracted = self.folder / "imports", self.folder / "extracted"
        main.app.dependency_overrides[main.profile_path] = lambda: self.profile
        main.app.dependency_overrides[main.import_dirs] = lambda: (self.imports, self.extracted)
        self.addCleanup(main.app.dependency_overrides.clear)
        self.client = TestClient(main.app)

    def data(self) -> dict:
        return yaml.safe_load(self.profile.read_text(encoding="utf-8"))

    def assertProblem(self, response, status: int, fragment: str):
        self.assertEqual(response.status_code, status, response.text)
        detail = response.json()["detail"]
        self.assertTrue(detail["message"])
        self.assertTrue(any(fragment in problem for problem in detail["problems"]), detail["problems"])


class ProfileRoutesTest(ApiTestCase):

    def test_get_profile(self):
        response = self.client.get("/api/profile")
        self.assertEqual(response.status_code, 200)
        profile = response.json()
        self.assertEqual(profile["personal"]["first_name"], "John")
        self.assertEqual(profile["experiences"][0]["id"], "example-research-company")
        self.assertNotIn("id", profile["education"][2])

    def test_add_experience(self):
        response = self.client.post("/api/profile/experiences", json={
            "company": "Acme Robotics", "title": "ML Engineer", "start_date": "2026-09", "skills": ["Python"]})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["id"], "acme-robotics")
        self.assertEqual(self.data()["experiences"][-1]["title"], "ML Engineer")

    def test_add_with_missing_required_field_is_refused(self):
        before = self.profile.read_bytes()
        self.assertProblem(self.client.post("/api/profile/experiences", json={"company": "Acme"}), 422, "title")
        self.assertEqual(self.profile.read_bytes(), before)

    def test_unknown_section(self):
        self.assertEqual(self.client.post("/api/profile/awards", json={"name": "x"}).status_code, 404)

    def test_update_sends_only_changed_fields(self):
        item = self.client.get("/api/profile").json()["experiences"][0]
        # Le formulaire renvoie tout ; seul le lieu change, un champ facultatif est vidé
        form = {**item, "location": "Lyon, France", "tags": None}
        form.pop("id")
        response = self.client.patch("/api/profile/experiences/example-research-company", json=form)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["location"], "Lyon, France")
        self.assertNotIn("tags", response.json())
        text = self.profile.read_text(encoding="utf-8")
        self.assertIn("context: >\n      Research internship", text)   # mise en forme conservée
        self.assertIn("# Résultats obtenus", text)                       # commentaire conservé

    def test_update_without_change_writes_nothing(self):
        before = self.profile.read_bytes()
        response = self.client.patch("/api/profile/projects/face-recognition", json={"name": "Face Recognition Pipeline"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.profile.read_bytes(), before)

    def test_update_with_invalid_date(self):
        response = self.client.patch("/api/profile/projects/face-recognition", json={"start_date": "oct. 2025"})
        self.assertProblem(response, 422, "AAAA")

    def test_unknown_id(self):
        self.assertProblem(self.client.patch("/api/profile/projects/nope", json={"name": "x"}), 404, "nope")

    def test_delete_project(self):
        response = self.client.delete("/api/profile/projects/bioinformatics-project")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"]["name"], "Bioinformatics Project")
        self.assertNotIn("bioinformatics-project", [p["id"] for p in self.data()["projects"]])


class LegacyEducationTest(ApiTestCase):
    """Formation sans id, adressée par « index-N » : id attribué et modification en une seule fois."""

    def test_update_assigns_an_id(self):
        response = self.client.patch("/api/profile/education/index-2", json={"school": "Legacy High School", "degree": "Bac S"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], "legacy-high-school")
        education = self.data()["education"]
        self.assertEqual(education[2]["degree"], "Bac S")
        self.assertEqual([e.get("id") for e in education[:2]], ["example-engineering-school", "example-university"])

    def test_failed_update_changes_nothing(self):
        before = self.profile.read_bytes()
        response = self.client.patch("/api/profile/education/index-2", json={"end_date": "2010"})   # avant le début
        self.assertProblem(response, 422, "end_date")
        self.assertEqual(self.profile.read_bytes(), before)            # pas d'id attribué non plus
        self.assertEqual(list(self.folder.iterdir()), [self.profile])  # pas de fichier temporaire

    def test_delete(self):
        response = self.client.delete("/api/profile/education/index-2")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["deleted"]["school"], "Legacy High School")
        self.assertNotIn("id", response.json()["deleted"])
        self.assertEqual(len(self.data()["education"]), 2)

    def test_index_out_of_range(self):
        self.assertEqual(self.client.delete("/api/profile/education/index-9").status_code, 404)


class SectionsTest(ApiTestCase):

    def test_update_personal_only_changed_fields(self):
        personal = self.client.get("/api/profile").json()["personal"]
        response = self.client.patch("/api/personal", json={**personal, "city": "Lyon", "gender": None})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["city"], "Lyon")
        self.assertEqual(self.data()["personal"]["gender"], "")
        self.assertIn('phone: "+33 6 00 00 00 00"', self.profile.read_text(encoding="utf-8"))

    def test_personal_name_cannot_be_emptied(self):
        self.assertProblem(self.client.patch("/api/personal", json={"first_name": None}), 422, "first_name")

    def test_career(self):
        response = self.client.patch("/api/career", json={"employment_status": "employed"})
        self.assertEqual(response.json()["employment_status"], "employed")
        self.assertProblem(self.client.patch("/api/career", json={"academic_status": "Diplômé"}), 422, "academic_status")

    def test_preferences(self):
        response = self.client.post("/api/preferences/preferred_locations", json={"value": "Lyon"})
        self.assertEqual(response.json()["preferred_locations"], ["Paris", "Remote", "Lyon"])
        response = self.client.patch("/api/preferences", json={"preferred_locations": ["Paris"]})
        self.assertEqual(response.json()["preferred_locations"], ["Paris"])
        self.assertProblem(self.client.post("/api/preferences/target_roles", json={"value": "data scientist"}), 422, "déjà")


class SkillsLanguagesInterestsTest(ApiTestCase):

    def test_skills(self):
        self.assertEqual(self.client.post("/api/skills", json={"category": "tools", "skill": "CI/CD"}).status_code, 201)
        self.assertProblem(self.client.post("/api/skills", json={"category": "Cloud", "skill": "AWS"}), 422, "n'existe pas")
        response = self.client.post("/api/skills", json={"category": "Cloud", "skill": "AWS", "create_category": True})
        self.assertEqual(response.json()["category"], "cloud")

        response = self.client.patch("/api/skills/tools/CI%2FCD", json={"new_name": "GitHub Actions"})
        self.assertIn("GitHub Actions", response.json()["tools"])
        response = self.client.delete("/api/skills/cloud/AWS")
        self.assertEqual(response.json()["cloud"], [])
        self.assertProblem(self.client.post("/api/skills", json={"category": "tools", "skill": "git"}), 422, "déjà")

    def test_c_cpp_and_csharp_coexist(self):
        for skill in ("C", "C++", "C#"):
            self.assertEqual(self.client.post("/api/skills", json={"category": "programming", "skill": skill}).status_code,
                             201, skill)
        self.assertProblem(self.client.post("/api/skills", json={"category": "programming", "skill": " c++"}), 422, "déjà")
        self.assertProblem(self.client.post("/api/skills", json={"category": "programming", "skill": "PYTHON"}), 422, "déjà")
        self.assertEqual(self.data()["skills"]["programming"][-3:], ["C", "C++", "C#"])
        self.assertEqual(self.client.delete("/api/skills/programming/C%2B%2B").json()["programming"][-2:], ["C", "C#"])

    def test_languages(self):
        self.assertEqual(self.client.post("/api/languages", json={"language": "German", "level": "B1"}).status_code, 201)
        self.assertProblem(self.client.post("/api/languages", json={"language": "german", "level": "B2"}), 422, "déjà")
        self.assertEqual(self.client.patch("/api/languages/German", json={"level": "B2"}).json()["level"], "B2")
        self.assertEqual(self.client.delete("/api/languages/German").json()["deleted"]["language"], "German")

    def test_interests(self):
        self.assertEqual(self.client.post("/api/interests", json={"interest": "Chess"}).json()[-1], "Chess")
        self.assertIn("Échecs", self.client.patch("/api/interests/Chess", json={"new_name": "Échecs"}).json())
        self.assertNotIn("Échecs", self.client.delete("/api/interests/%C3%89checs").json())


class ImportRoutesTest(ApiTestCase):

    def upload(self, name="Mon CV.pdf", content=None):
        if content is None:
            content = make_pdf(self.folder / "source.pdf", CV_LINES).read_bytes()
        with mock.patch.object(extract_profile, "run_claude", return_value=fake_claude_answer()) as claude:
            response = self.client.post("/api/imports", files={"file": (name, content, "application/pdf")})
        return response, claude

    def test_upload_returns_the_review(self):
        response, claude = self.upload()
        self.assertEqual(response.status_code, 201, response.text)
        claude.assert_called_once()
        review = response.json()
        self.assertTrue(review["import_id"].startswith("Mon-CV-"))
        self.assertNotIn("json", review["source"])
        self.assertEqual(review["source"]["source_pdf"], "Mon CV.pdf")
        self.assertEqual(review["experiences"][0]["proposal_id"], "experiences-1")
        self.assertEqual(len(list(self.imports.glob("*.pdf"))), 1)
        self.assertEqual(len(list(self.extracted.glob("*.json"))), 1)

        listed = self.client.get("/api/imports").json()
        self.assertEqual([entry["import_id"] for entry in listed], [review["import_id"]])
        again = self.client.get(f"/api/imports/{review['import_id']}/review")
        self.assertEqual(again.json()["summary"], review["summary"])

    def test_upload_of_a_non_pdf(self):
        response, claude = self.upload(name="cv.pdf", content=b"pas un PDF")
        self.assertProblem(response, 422, "PDF")
        claude.assert_not_called()

    def test_claude_failure(self):
        pdf = make_pdf(self.folder / "source.pdf", CV_LINES).read_bytes()
        with mock.patch.object(extract_profile, "run_claude", side_effect=RuntimeError("Claude n'a pas répondu.")):
            response = self.client.post("/api/imports", files={"file": ("cv.pdf", pdf, "application/pdf")})
        self.assertProblem(response, 502, "Claude")

    def test_apply_decisions(self):
        import_id = self.upload()[0].json()["import_id"]
        response = self.client.post(f"/api/imports/{import_id}/apply", json={"decisions": {
            "experiences-1": {"action": "add"},
            "interests-2": {"action": "add"},
            "personal": {"action": "update", "fields": ["phone"]},
        }})
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertNotIn("profile", report)
        self.assertEqual([entry["proposal_id"] for entry in report["added"]], ["experiences-1", "interests-2"])
        data = self.data()
        self.assertEqual(data["experiences"][-1]["company"], "Acme Robotics")
        self.assertEqual(data["interests"][-1], "Chess")
        self.assertEqual(data["personal"]["phone"], "+33 6 12 34 56 78")

    def test_apply_with_corrections(self):
        import_id = self.upload()[0].json()["import_id"]
        before = self.profile.read_bytes()
        bad = self.client.post(f"/api/imports/{import_id}/apply", json={"decisions": {
            "experiences-1": {"action": "add", "fields": ["company", "title", "start_date"],
                              "overrides": {"company": "Acme Robotics SA", "start_date": "sept. 2024"}},
        }})
        self.assertProblem(bad, 422, "experiences-1 : correction refusée")
        self.assertEqual(self.profile.read_bytes(), before)

        response = self.client.post(f"/api/imports/{import_id}/apply", json={"decisions": {
            "experiences-1": {"action": "add", "fields": ["company", "title", "responsibilities"],
                              "overrides": {"company": "Acme Robotics SA", "responsibilities": ["Mission corrigée"]}},
            "personal": {"action": "update", "fields": ["phone"], "overrides": {"phone": "+33 7 00 00 00 00"}},
        }})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["added"][0]["corrected"], ["company", "responsibilities"])
        data = self.data()
        self.assertEqual(data["experiences"][-1]["company"], "Acme Robotics SA")
        self.assertEqual(data["experiences"][-1]["responsibilities"], ["Mission corrigée"])
        self.assertEqual(data["personal"]["phone"], "+33 7 00 00 00 00")

    def test_refused_decisions_change_nothing(self):
        import_id = self.upload()[0].json()["import_id"]
        before = self.profile.read_bytes()
        response = self.client.post(f"/api/imports/{import_id}/apply", json={"decisions": {
            "experiences-1": {"action": "add"},
            "interests-1": {"action": "add"},                       # Tennis : déjà dans le profil
        }})
        self.assertProblem(response, 422, "interests-1")
        self.assertEqual(self.profile.read_bytes(), before)

    def test_unknown_import(self):
        self.assertEqual(self.client.get("/api/imports/absent/review").status_code, 404)
        self.assertEqual(self.client.post("/api/imports/..%2Fsecret/apply", json={"decisions": {}}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
