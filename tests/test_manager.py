"""
Tests de l'ajout d'une expérience au profil candidat.
Tout se passe dans des fichiers temporaires : le vrai profil n'est jamais touché.

Lancement :  python -m unittest discover tests
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from candidate import manager
from candidate.manager import ExperienceError, ItemError, add_education, add_experience, add_project
from candidate.profile import CANDIDATE_PATH, EXAMPLE_PATH, ProfileError, load_profile


MINIMAL = "personal:\n  first_name: Jane\n  last_name: Doe\n"


class AddExperienceTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)

    def profile_file(self, text: str) -> Path:
        path = self.folder / "candidate.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    def example_copy(self) -> Path:
        path = self.folder / "candidate.yaml"
        shutil.copy(EXAMPLE_PATH, path)
        return path

    # ---------- Ajout et id ----------

    def test_adds_experience_and_returns_generated_id(self):
        path = self.example_copy()
        new_id = add_experience({"company": "Acme Robotics", "title": "ML Engineer Intern"}, path)

        self.assertEqual(new_id, "acme-robotics")
        experiences = load_profile(path).data["experiences"]
        self.assertEqual(experiences[-1], {"id": "acme-robotics", "company": "Acme Robotics", "title": "ML Engineer Intern"})

    def test_id_is_unique_across_experiences_and_projects(self):
        path = self.profile_file(MINIMAL + "experiences:\n  - id: acme\nprojects:\n  - id: acme-2\n")
        self.assertEqual(add_experience({"company": "Acme", "title": "Stagiaire"}, path), "acme-3")
        self.assertEqual(add_experience({"company": "Acme", "title": "Alternant"}, path), "acme-4")

    def test_id_from_accented_company_name(self):
        path = self.profile_file(MINIMAL)
        self.assertEqual(add_experience({"company": "Société Générale — Paris", "title": "Analyste"}, path), "societe-generale-paris")

    def test_id_cannot_be_provided(self):
        with self.assertRaises(ExperienceError):
            add_experience({"id": "mon-id", "company": "Acme", "title": "Stagiaire"}, self.profile_file(MINIMAL))

    # ---------- Champs facultatifs ----------

    def test_all_fields_are_written(self):
        path = self.profile_file(MINIMAL)
        add_experience({
            "company": "Acme", "title": "Stagiaire", "start_date": "2025-01", "end_date": "2025-06",
            "location": "Lyon, France", "priority": "high", "context": "Startup de robotique.",
            "description": "Vision embarquée.", "tags": ["robotics"], "responsibilities": ["Entraîné un modèle YOLO"],
            "achievements": ["Latence divisée par 2"], "skills": ["Python", "PyTorch"],
        }, path)

        experience = load_profile(path).data["experiences"][0]
        self.assertEqual(experience["start_date"], "2025-01")
        self.assertEqual(experience["achievements"], ["Latence divisée par 2"])
        self.assertEqual(list(experience)[:3], ["id", "company", "title"])

    def test_empty_optional_fields_are_omitted(self):
        path = self.profile_file(MINIMAL)
        add_experience({
            "company": "Acme", "title": "Stagiaire", "location": "", "context": "   ", "description": None,
            "responsibilities": [], "achievements": ["", "  "], "skills": None,
        }, path)

        experience = load_profile(path).data["experiences"][0]
        self.assertEqual(set(experience), {"id", "company", "title"})

    def test_values_are_read_back_as_the_same_text(self):
        # Sans guillemets, « 2025 » serait relu comme un nombre et « No » comme faux
        path = self.profile_file(MINIMAL)
        add_experience({
            "company": "No", "title": "2025", "start_date": "2025", "end_date": "2025-06",
            "skills": ["yes", "1.5", "null", "C++"],
        }, path)

        text = path.read_text(encoding="utf-8")
        self.assertIn('start_date: "2025"', text)
        self.assertIn('end_date: "2025-06"', text)

        experience = load_profile(path).data["experiences"][0]
        self.assertEqual(experience["company"], "No")
        self.assertEqual(experience["title"], "2025")
        self.assertEqual(experience["start_date"], "2025")
        self.assertEqual(experience["skills"], ["yes", "1.5", "null", "C++"])

    def test_file_is_untouched_if_the_written_text_would_be_invalid(self):
        # Si le texte produit ne se relisait pas correctement, rien ne doit être écrit
        path = self.example_copy()
        before = path.read_text(encoding="utf-8")
        with mock.patch.object(manager, "_to_text", return_value="personal:\n  first_name: Jane\n"):
            with self.assertRaises(ProfileError):
                add_experience({"company": "Acme", "title": "Stagiaire"}, path)
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_ordinary_text_is_not_quoted(self):
        path = self.profile_file(MINIMAL)
        add_experience({"company": "Acme Robotics", "title": "ML Engineer"}, path)
        self.assertIn("    company: Acme Robotics\n    title: ML Engineer\n", path.read_text(encoding="utf-8"))

    # ---------- Données incorrectes : rien n'est écrit ----------

    def test_invalid_experience_is_rejected_and_file_unchanged(self):
        path = self.example_copy()
        before = path.read_text(encoding="utf-8")

        cases = [
            ({"title": "Stagiaire"}, "« company » est obligatoire"),
            ({"company": "Acme"}, "« title » est obligatoire"),
            ({"company": "Acme", "title": "X", "start_date": "janvier 2025"}, "AAAA-MM"),
            ({"company": "Acme", "title": "X", "start_date": "2025-06", "end_date": "2025-01"}, "avant « start_date »"),
            ({"company": "Acme", "title": "X", "priority": "urgent"}, "« priority » doit valoir"),
            ({"company": "Acme", "title": "X", "skills": "Python"}, "liste de textes"),
            ({"company": "Acme", "title": "X", "salary": "50k"}, "champ(s) inconnu(s) : salary"),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                with self.assertRaises(ExperienceError) as context:
                    add_experience(fields, path)
                self.assertIn(expected, str(context.exception))

        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_invalid_profile_is_not_modified(self):
        path = self.profile_file("personal:\n  first_name: Jane\n")  # nom manquant
        with self.assertRaises(ProfileError):
            add_experience({"company": "Acme", "title": "Stagiaire"}, path)
        self.assertEqual(path.read_text(encoding="utf-8"), "personal:\n  first_name: Jane\n")

    def test_missing_profile_file(self):
        with self.assertRaises(ProfileError):
            add_experience({"company": "Acme", "title": "Stagiaire"}, self.folder / "absent.yaml")

    # ---------- Conservation du fichier existant ----------

    def test_existing_content_and_comments_are_kept(self):
        path = self.example_copy()
        before = path.read_text(encoding="utf-8")

        add_experience({"company": "Acme", "title": "Stagiaire"}, path)
        after = path.read_text(encoding="utf-8")

        # Toutes les lignes d'avant sont toujours là, commentaires compris
        self.assertTrue(set(before.splitlines()) <= set(after.splitlines()))
        self.assertIn("# Résultats obtenus (chiffrés si possible), distincts des missions ci-dessus", after)

        old, new = load_profile(EXAMPLE_PATH).data, load_profile(path).data
        self.assertEqual(new["experiences"][:-1], old["experiences"])
        for section in old:
            if section != "experiences":
                self.assertEqual(new[section], old[section], section)

    def test_empty_or_missing_experiences_sections(self):
        for text in (MINIMAL, MINIMAL + "experiences:\n", MINIMAL + "experiences: []\nprojects: []\n"):
            with self.subTest(text=text):
                path = self.profile_file(text)
                add_experience({"company": "Acme", "title": "Stagiaire"}, path)
                self.assertEqual([e["id"] for e in load_profile(path).data["experiences"]], ["acme"])
                self.assertIn("experiences:\n  - id: acme\n    company: Acme\n", path.read_text(encoding="utf-8"))

    def test_no_temporary_file_left_behind(self):
        path = self.profile_file(MINIMAL)
        add_experience({"company": "Acme", "title": "Stagiaire"}, path)
        self.assertEqual([p.name for p in self.folder.iterdir()], ["candidate.yaml"])

    def test_default_path_is_the_private_profile(self):
        # Sans chemin, c'est bien le profil privé qui est visé (ici remplacé par un fichier temporaire)
        path = self.profile_file(MINIMAL)
        with mock.patch("candidate.profile.CANDIDATE_PATH", path):
            add_experience({"company": "Acme", "title": "Stagiaire"})
        self.assertEqual(load_profile(path).data["experiences"][0]["id"], "acme")
        self.assertNotEqual(path, CANDIDATE_PATH)


class AddProjectTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = self.folder / "candidate.yaml"

    def test_adds_project_with_all_fields(self):
        shutil.copy(EXAMPLE_PATH, self.path)
        new_id = add_project({
            "name": "Détecteur de Drones", "start_date": "2026-03", "end_date": "2026-05", "priority": "high",
            "context": "Projet personnel.", "description": "Détection de drones par vision.",
            "tags": ["computer_vision"], "responsibilities": ["Annoté 500 images"],
            "achievements": ["mAP de 0.8"], "skills": ["Python", "YOLO"],
            "github_url": "https://github.com/janedoe/drones",
        }, self.path)

        self.assertEqual(new_id, "detecteur-de-drones")
        project = load_profile(self.path).data["projects"][-1]
        self.assertEqual(list(project)[:2], ["id", "name"])
        self.assertEqual(project["github_url"], "https://github.com/janedoe/drones")
        self.assertEqual(project["start_date"], "2026-03")

    def test_minimal_project_and_empty_optional_fields(self):
        self.path.write_text(MINIMAL + "projects:\n", encoding="utf-8")
        add_project({"name": "Robot", "github_url": "", "skills": [], "context": None}, self.path)
        self.assertEqual(load_profile(self.path).data["projects"], [{"id": "robot", "name": "Robot"}])

    def test_project_id_is_unique_across_the_whole_profile(self):
        self.path.write_text(MINIMAL + "experiences:\n  - id: robot\neducation:\n  - id: robot-2\n    school: X\n", encoding="utf-8")
        self.assertEqual(add_project({"name": "Robot"}, self.path), "robot-3")

    def test_invalid_project_is_rejected(self):
        shutil.copy(EXAMPLE_PATH, self.path)
        before = self.path.read_text(encoding="utf-8")
        cases = [
            ({"context": "Sans nom"}, "« name » est obligatoire"),
            ({"name": "X", "github_url": "github.com/janedoe/x"}, "« github_url » doit commencer par http"),
            ({"name": "X", "company": "Acme"}, "champ(s) inconnu(s) : company"),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                with self.assertRaises(ItemError) as context:
                    add_project(fields, self.path)
                self.assertIn(expected, str(context.exception))
                self.assertTrue(str(context.exception).startswith("Projet invalide"))
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


class AddEducationTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = self.folder / "candidate.yaml"

    def test_adds_education_with_generated_id(self):
        shutil.copy(EXAMPLE_PATH, self.path)
        new_id = add_education({
            "school": "Université Paris-Saclay", "degree": "Master 2", "specialization": "Data Science",
            "start_date": "2026-09", "end_date": "2027-06", "location": "Orsay, France",
            "details": ["Deep Learning", "Statistiques"],
        }, self.path)

        self.assertEqual(new_id, "universite-paris-saclay")
        education = load_profile(self.path).data["education"]
        self.assertEqual(len(education), 3)
        self.assertEqual(education[-1]["details"], ["Deep Learning", "Statistiques"])
        self.assertEqual(list(education[-1])[:2], ["id", "school"])

    def test_works_with_old_education_entries_without_id(self):
        # Les profils existants (dont le profil privé) ont des formations sans id
        self.path.write_text(MINIMAL + "education:\n  - school: Lycee Saint-Louis\n  - school: Telecom\n", encoding="utf-8")
        new_id = add_education({"school": "Telecom"}, self.path)

        self.assertEqual(new_id, "telecom")
        education = load_profile(self.path).data["education"]
        self.assertEqual([e.get("id") for e in education], [None, None, "telecom"])

    def test_same_school_twice_gets_two_ids(self):
        self.path.write_text(MINIMAL, encoding="utf-8")
        self.assertEqual(add_education({"school": "MIT", "degree": "Bachelor"}, self.path), "mit")
        self.assertEqual(add_education({"school": "MIT", "degree": "Master"}, self.path), "mit-2")

    def test_existing_content_is_kept(self):
        shutil.copy(EXAMPLE_PATH, self.path)
        before = self.path.read_text(encoding="utf-8")
        add_education({"school": "MIT"}, self.path)
        after = self.path.read_text(encoding="utf-8")
        self.assertTrue(set(before.splitlines()) <= set(after.splitlines()))

        old, new = load_profile(EXAMPLE_PATH).data, load_profile(self.path).data
        self.assertEqual(new["education"][:-1], old["education"])
        for section in old:
            if section != "education":
                self.assertEqual(new[section], old[section], section)

    def test_invalid_education_is_rejected(self):
        self.path.write_text(MINIMAL, encoding="utf-8")
        with self.assertRaises(ItemError) as context:
            add_education({"degree": "Master", "start_date": "sept 2025"}, self.path)
        message = str(context.exception)
        self.assertTrue(message.startswith("Formation invalide"))
        self.assertIn("« school » est obligatoire", message)
        self.assertIn("AAAA-MM", message)
        self.assertEqual(self.path.read_text(encoding="utf-8"), MINIMAL)


if __name__ == "__main__":
    unittest.main()
