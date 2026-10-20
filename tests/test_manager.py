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
from candidate.manager import (
    ExperienceError, ItemError, add_education, add_experience, add_interest, add_language, add_project, add_skill,
    add_preference, assign_missing_ids, update_career, update_item, update_personal, update_preferences,
)
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


class SimpleSectionsTest(unittest.TestCase):
    """Compétences, langues et centres d'intérêt."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = self.folder / "candidate.yaml"

    def example(self) -> Path:
        shutil.copy(EXAMPLE_PATH, self.path)
        return self.path

    def minimal(self, extra: str = "") -> Path:
        self.path.write_text(MINIMAL + extra, encoding="utf-8")
        return self.path

    def assertRejected(self, function, expected, *args, **kwargs):
        before = self.path.read_text(encoding="utf-8")
        with self.assertRaises(ItemError) as context:
            function(*args, **kwargs)
        self.assertIn(expected, str(context.exception))
        self.assertEqual(self.path.read_text(encoding="utf-8"), before, "le fichier ne doit pas changer")

    def assertOnlyLinesAdded(self, before: str):
        self.assertTrue(set(before.splitlines()) <= set(self.path.read_text(encoding="utf-8").splitlines()))

    # ---------- Compétences ----------

    def test_add_skill_to_existing_category(self):
        before = self.example().read_text(encoding="utf-8")
        self.assertEqual(add_skill("Rust", "programming", self.path), "programming")
        self.assertEqual(load_profile(self.path).data["skills"]["programming"], ["Python", "SQL", "Bash", "Julia", "Rust"])
        self.assertOnlyLinesAdded(before)

    def test_category_is_found_whatever_its_spelling(self):
        self.example()
        self.assertEqual(add_skill("JAX", "Machine Learning", self.path), "machine_learning")
        self.assertIn("JAX", load_profile(self.path).data["skills"]["machine_learning"])

    def test_unknown_category_needs_create_category(self):
        self.example()
        self.assertRejected(add_skill, "la catégorie « Cloud » n'existe pas (catégories : programming, machine_learning", "AWS", "Cloud", self.path)
        self.assertEqual(add_skill("AWS", "Cloud Platforms", self.path, create_category=True), "cloud_platforms")
        self.assertEqual(load_profile(self.path).data["skills"]["cloud_platforms"], ["AWS"])

    def test_duplicate_skill_in_same_category_is_rejected(self):
        self.example()
        self.assertRejected(add_skill, "« python » est déjà dans la catégorie « programming »", "python", "programming", self.path)

    def test_same_skill_in_another_category_is_allowed(self):
        self.example()
        add_skill("Python", "tools", self.path)
        self.assertIn("Python", load_profile(self.path).data["skills"]["tools"])

    def test_skills_section_absent_or_empty(self):
        for extra in ("", "skills:\n", "skills: {}\n", "skills:\n  programming:\n"):
            with self.subTest(extra=extra):
                self.minimal(extra)
                add_skill("Python", "programming", self.path, create_category="programming" not in extra)
                self.assertEqual(load_profile(self.path).data["skills"]["programming"], ["Python"])
                self.assertIn("skills:\n  programming:\n    - Python\n", self.path.read_text(encoding="utf-8"))

    def test_invalid_skill_values(self):
        self.example()
        self.assertRejected(add_skill, "« skill » est obligatoire", "  ", "programming", self.path)
        self.assertRejected(add_skill, "« category » est obligatoire", "Rust", "", self.path)
        self.assertRejected(add_skill, "doit contenir des lettres ou des chiffres", "Rust", "!!!", self.path)
        self.assertRejected(add_skill, "« skill » est obligatoire", None, "programming", self.path)

    def test_ambiguous_skill_is_read_back_as_text(self):
        self.example()
        add_skill("yes", "tools", self.path)
        self.assertIn("yes", load_profile(self.path).data["skills"]["tools"])

    # ---------- Langues ----------

    def test_add_language(self):
        before = self.example().read_text(encoding="utf-8")
        self.assertEqual(add_language("German", "B1 / Intermediate", self.path), "German")
        self.assertEqual(load_profile(self.path).data["languages"][-1], {"language": "German", "level": "B1 / Intermediate"})
        self.assertOnlyLinesAdded(before)

    def test_duplicate_language_is_rejected(self):
        self.example()
        self.assertRejected(add_language, "« spanish » est déjà dans le profil (niveau : Basic)", "spanish", "B2", self.path)

    def test_language_needs_a_level(self):
        self.example()
        self.assertRejected(add_language, "« level » est obligatoire", "German", "", self.path)
        self.assertRejected(add_language, "« language » est obligatoire", "", "B2", self.path)

    def test_languages_section_absent_or_empty(self):
        for extra in ("", "languages:\n", "languages: []\n"):
            with self.subTest(extra=extra):
                self.minimal(extra)
                add_language("French", "Native", self.path)
                self.assertEqual(load_profile(self.path).data["languages"], [{"language": "French", "level": "Native"}])
                self.assertIn("languages:\n  - language: French\n    level: Native\n", self.path.read_text(encoding="utf-8"))

    # ---------- Centres d'intérêt ----------

    def test_add_interest_at_the_end(self):
        before = self.example().read_text(encoding="utf-8")
        self.assertEqual(add_interest("  Chess ", self.path), "Chess")
        self.assertEqual(load_profile(self.path).data["interests"], ["Tennis", "Football", "Running", "Guitar", "Chess"])
        self.assertOnlyLinesAdded(before)

    def test_duplicate_interest_is_rejected(self):
        self.example()
        self.assertRejected(add_interest, "« tennis » est déjà dans les centres d'intérêt", "tennis", self.path)

    def test_invalid_interest(self):
        self.example()
        self.assertRejected(add_interest, "« interest » est obligatoire", "", self.path)
        self.assertRejected(add_interest, "« interest » est obligatoire", ["Chess"], self.path)

    def test_interests_section_absent_or_empty(self):
        for extra in ("", "interests:\n", "interests: []\n"):
            with self.subTest(extra=extra):
                self.minimal(extra)
                add_interest("Tennis", self.path)
                self.assertEqual(load_profile(self.path).data["interests"], ["Tennis"])

    # ---------- Commun ----------

    def test_other_sections_and_comments_are_kept(self):
        before = self.example().read_text(encoding="utf-8")
        add_skill("Rust", "programming", self.path)
        add_language("German", "B1", self.path)
        add_interest("Chess", self.path)

        self.assertOnlyLinesAdded(before)
        self.assertIn("# Résultats obtenus (chiffrés si possible), distincts des missions ci-dessus", self.path.read_text(encoding="utf-8"))
        old, new = load_profile(EXAMPLE_PATH).data, load_profile(self.path).data
        for section in old:
            if section not in ("skills", "languages", "interests"):
                self.assertEqual(new[section], old[section], section)

    def test_invalid_profile_is_not_modified(self):
        self.path.write_text("personal:\n  first_name: Jane\n", encoding="utf-8")
        for function, args in ((add_skill, ("Python", "programming")), (add_language, ("French", "Native")), (add_interest, ("Tennis",))):
            with self.subTest(function=function.__name__):
                with self.assertRaises(ProfileError):
                    function(*args, self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "personal:\n  first_name: Jane\n")


class UpdateSectionsTest(unittest.TestCase):
    """Informations personnelles, statut et préférences : mise à jour champ par champ."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = self.folder / "candidate.yaml"

    def example(self) -> str:
        shutil.copy(EXAMPLE_PATH, self.path)
        return self.path.read_text(encoding="utf-8")

    def minimal(self, extra: str = "") -> None:
        self.path.write_text(MINIMAL + extra, encoding="utf-8")

    def assertRejected(self, function, fields, expected):
        before = self.path.read_text(encoding="utf-8")
        with self.assertRaises(ItemError) as context:
            function(fields, self.path)
        self.assertIn(expected, str(context.exception))
        self.assertEqual(self.path.read_text(encoding="utf-8"), before, "le fichier ne doit pas changer")

    def assertOnlyChanged(self, before: str, changed_sections: set):
        old = load_profile(EXAMPLE_PATH).data
        new = load_profile(self.path).data
        for section in old:
            if section not in changed_sections:
                self.assertEqual(new[section], old[section], section)

    # ---------- personal ----------

    def test_update_some_personal_fields_only(self):
        before = self.example()
        section = update_personal({"city": "Lyon", "phone": "+33 6 11 22 33 44"}, self.path)

        self.assertEqual(section["city"], "Lyon")
        self.assertEqual(section["phone"], "+33 6 11 22 33 44")
        self.assertEqual(section["first_name"], "John")   # non fourni : inchangé
        self.assertEqual(section["email"], "john.doe@example.com")
        self.assertOnlyChanged(before, {"personal"})
        self.assertIn("# Situation actuelle du candidat", self.path.read_text(encoding="utf-8"))

    def test_new_personal_field_and_empty_fields(self):
        self.minimal()
        section = update_personal({"email": "jane@example.com", "linkedin": "", "github": None}, self.path)
        self.assertEqual(section, {"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com", "linkedin": "", "github": ""})

    def test_values_keep_their_type(self):
        self.example()
        section = update_personal({"postal_code": "75116", "birth_date": "2001-06-18"}, self.path)
        self.assertEqual(section["postal_code"], "75116")   # pas le nombre 75116
        self.assertEqual(section["birth_date"], "2001-06-18")  # pas une date
        self.assertIn('birth_date: "2001-06-18"', self.path.read_text(encoding="utf-8"))

    def test_invalid_personal_values(self):
        self.example()
        cases = [
            ({"first_name": ""}, "« first_name » est obligatoire et ne peut pas être vidé"),
            ({"last_name": None}, "« last_name » est obligatoire"),
            ({"email": "john.example.com"}, "n'est pas une adresse e-mail valide"),
            ({"linkedin": "linkedin.com/in/john"}, "« linkedin » doit commencer par http"),
            ({"birth_date": "18/06/2001"}, "AAAA-MM-JJ"),
            ({"phone": 612345678}, "« phone » doit être un texte"),
            ({"website": "https://john.dev"}, "champ(s) inconnu(s) : website"),
            ({}, "aucun champ à mettre à jour"),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                self.assertRejected(update_personal, fields, expected)

    # ---------- career ----------

    def test_update_career(self):
        before = self.example()
        section = update_career({"academic_status": "student", "graduation_date": "2027-06"}, self.path)
        self.assertEqual(section, {"academic_status": "student", "employment_status": "job_seeking", "graduation_date": "2027-06"})
        # Le commentaire en fin de ligne est conservé
        self.assertIn("academic_status: student", self.path.read_text(encoding="utf-8"))
        self.assertIn("# student | graduated", self.path.read_text(encoding="utf-8"))
        self.assertOnlyChanged(before, {"career"})

    def test_career_section_is_created_after_personal(self):
        # Comme le profil privé : pas de section career
        self.minimal("education:\n  - school: X\ninterests:\n  - Tennis\n")
        update_career({"employment_status": "employed"}, self.path)

        text = self.path.read_text(encoding="utf-8")
        self.assertLess(text.index("personal:"), text.index("career:"))
        self.assertLess(text.index("career:"), text.index("education:"))
        self.assertEqual(load_profile(self.path).data["career"], {"employment_status": "employed"})

    def test_empty_career_section(self):
        for extra in ("career:\n", "career: {}\n"):
            with self.subTest(extra=extra):
                self.minimal(extra)
                update_career({"academic_status": "graduated"}, self.path)
                self.assertEqual(load_profile(self.path).data["career"], {"academic_status": "graduated"})

    def test_invalid_career_values(self):
        self.example()
        self.assertRejected(update_career, {"academic_status": "diplômé"}, "« academic_status » doit valoir student, graduated")
        self.assertRejected(update_career, {"employment_status": "chômage"}, "« employment_status » doit valoir employed")
        self.assertRejected(update_career, {"graduation_date": "juin 2026"}, "AAAA-MM")

    # ---------- preferences ----------

    def test_update_preferences_replaces_given_lists(self):
        before = self.example()
        section = update_preferences({"preferred_locations": ["Lyon", "lyon", " Remote ", ""]}, self.path)
        self.assertEqual(section["preferred_locations"], ["Lyon", "Remote"])   # doublons et vides retirés
        self.assertEqual(section["target_roles"][0], "Computer Vision Engineer")  # non fourni : inchangé
        self.assertOnlyChanged(before, {"preferences"})

    def test_preferences_absent_or_emptied(self):
        self.minimal()
        update_preferences({"target_roles": ["Data Scientist"]}, self.path)
        update_preferences({"employment_types": []}, self.path)
        self.assertEqual(load_profile(self.path).data["preferences"], {"target_roles": ["Data Scientist"], "employment_types": []})

    def test_invalid_preferences(self):
        self.example()
        self.assertRejected(update_preferences, {"target_roles": "Data Scientist"}, "« target_roles » doit être une liste de textes")
        self.assertRejected(update_preferences, {"salary": ["50k"]}, "champ(s) inconnu(s) : salary")

    # ---------- add_preference : ajoute sans rien retirer ----------

    def test_add_preference_keeps_existing_values(self):
        before = self.example()
        values = add_preference("employment_types", "Internship", self.path)
        self.assertEqual(values, ["Full-time", "Internship"])
        self.assertEqual(load_profile(self.path).data["preferences"]["target_roles"][0], "Computer Vision Engineer")
        self.assertTrue(set(before.splitlines()) <= set(self.path.read_text(encoding="utf-8").splitlines()))
        self.assertOnlyChanged(before, {"preferences"})

    def test_add_preference_versus_update_preferences(self):
        # add_preference ajoute ; update_preferences remplace la liste
        self.example()
        self.assertEqual(add_preference("preferred_locations", "Lyon", self.path), ["Paris", "Remote", "Lyon"])
        self.assertEqual(update_preferences({"preferred_locations": ["Lyon"]}, self.path)["preferred_locations"], ["Lyon"])

    def test_add_preference_duplicate_is_rejected(self):
        self.example()
        self.assertRejected(lambda fields, path: add_preference("preferred_locations", fields, path), "  paris ", "« paris » est déjà dans « preferred_locations »")

    def test_add_preference_invalid_values(self):
        self.example()
        self.assertRejected(lambda fields, path: add_preference("salary", fields, path), "50k", "catégorie inconnue : « salary »")
        self.assertRejected(lambda fields, path: add_preference("target_roles", fields, path), "", "« value » est obligatoire")
        self.assertRejected(lambda fields, path: add_preference("target_roles", fields, path), ["AI Engineer"], "« value » est obligatoire")

    def test_add_preference_with_absent_or_empty_section(self):
        for extra in ("", "preferences:\n", "preferences: {}\n", "preferences:\n  target_roles:\n", "preferences:\n  target_roles: []\n"):
            with self.subTest(extra=extra):
                self.minimal(extra)
                self.assertEqual(add_preference("target_roles", "Data Scientist", self.path), ["Data Scientist"])
                self.assertIn("preferences:\n  target_roles:\n    - Data Scientist\n", self.path.read_text(encoding="utf-8"))

    # ---------- commun ----------

    def test_invalid_profile_is_not_modified(self):
        self.path.write_text("personal:\n  first_name: Jane\n", encoding="utf-8")
        for function, fields in ((update_personal, {"city": "Lyon"}), (update_career, {"academic_status": "student"}),
                                 (update_preferences, {"target_roles": ["X"]})):
            with self.subTest(function=function.__name__):
                with self.assertRaises(ProfileError):
                    function(fields, self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "personal:\n  first_name: Jane\n")

    def test_updated_profile_still_works_for_the_generator(self):
        self.example()
        update_personal({"city": "Lyon"}, self.path)
        update_career({"academic_status": "student"}, self.path)
        update_preferences({"target_roles": ["AI Engineer"]}, self.path)
        profile = load_profile(self.path)
        self.assertEqual(profile.data["personal"]["first_name"], "John")
        self.assertIn("academic_status: student", profile.text)


class UpdateItemTest(unittest.TestCase):
    """Modification d'une expérience, d'un projet ou d'une formation existant(e)."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = self.folder / "candidate.yaml"
        shutil.copy(EXAMPLE_PATH, self.path)
        self.before_text = self.path.read_text(encoding="utf-8")
        self.before = load_profile(self.path).data

    def item(self, section, item_id):
        return next(e for e in load_profile(self.path).data[section] if e.get("id") == item_id)

    def assertNothingElseChanged(self, section, item_id, changed_fields):
        after = load_profile(self.path).data
        # Toutes les autres sections : identiques
        for name in self.before:
            if name != section:
                self.assertEqual(after[name], self.before[name], name)
        # Tous les autres éléments de la section : identiques et dans le même ordre
        old_others = [e for e in self.before[section] if e.get("id") != item_id]
        new_others = [e for e in after[section] if e.get("id") != item_id]
        self.assertEqual(new_others, old_others)
        self.assertEqual([e.get("id") for e in after[section]], [e.get("id") for e in self.before[section]])
        # Dans l'élément : les champs non modifiés sont identiques
        old_item = next(e for e in self.before[section] if e.get("id") == item_id)
        new_item = next(e for e in after[section] if e.get("id") == item_id)
        for field in set(old_item) - set(changed_fields):
            self.assertEqual(new_item.get(field), old_item[field], field)

    def assertRejected(self, expected, *args):
        with self.assertRaises(ItemError) as context:
            update_item(*args, self.path)
        self.assertIn(expected, str(context.exception))
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.before_text, "le fichier ne doit pas changer")

    # ---------- les trois types ----------

    def test_update_experience(self):
        item = update_item("experiences", "example-research-company",
                           {"title": "Senior CV Intern", "achievements": ["Nouveau résultat"]}, self.path)
        self.assertEqual(item["title"], "Senior CV Intern")
        self.assertEqual(item["achievements"], ["Nouveau résultat"])
        self.assertEqual(item["company"], "Example Research Company")
        self.assertNothingElseChanged("experiences", "example-research-company", {"title", "achievements"})

    def test_update_project(self):
        update_item("projects", "face-recognition", {"github_url": "https://github.com/johndoe/face", "end_date": "2026-02"}, self.path)
        project = self.item("projects", "face-recognition")
        self.assertEqual(project["github_url"], "https://github.com/johndoe/face")
        self.assertEqual(project["end_date"], "2026-02")
        self.assertNothingElseChanged("projects", "face-recognition", {"github_url", "end_date"})

    def test_update_education(self):
        update_item("education", "example-university", {"degree": "Erasmus Exchange", "details": ["Computer Vision"]}, self.path)
        education = self.item("education", "example-university")
        self.assertEqual(education["degree"], "Erasmus Exchange")
        self.assertEqual(education["details"], ["Computer Vision"])
        self.assertNothingElseChanged("education", "example-university", {"degree", "details"})

    # ---------- comportement ----------

    def test_only_modified_lines_change_and_comments_are_kept(self):
        update_item("experiences", "example-software-company", {"location": "Lyon, France"}, self.path)
        after = self.path.read_text(encoding="utf-8")
        removed = set(self.before_text.splitlines()) - set(after.splitlines())
        self.assertEqual(removed, {"    location: Paris, France"} & removed)   # seule la ligne modifiée disparaît
        self.assertIn("# Résultats obtenus (chiffrés si possible), distincts des missions ci-dessus", after)
        self.assertIn("    context: >", after)   # les textes sur plusieurs lignes gardent leur forme

    def test_clear_optional_fields(self):
        item = update_item("projects", "multi-agent-system", {"github_url": "", "achievements": [], "context": None}, self.path)
        for field in ("github_url", "achievements", "context"):
            self.assertNotIn(field, item)
        self.assertNothingElseChanged("projects", "multi-agent-system", {"github_url", "achievements", "context"})

    def test_new_optional_field_can_be_added(self):
        item = update_item("education", "example-engineering-school", {"location": "Palaiseau, France"}, self.path)
        self.assertEqual(item["location"], "Palaiseau, France")

    def test_id_is_kept_when_the_name_changes(self):
        item = update_item("experiences", "example-software-company", {"company": "Acme"}, self.path)
        self.assertEqual(item["id"], "example-software-company")
        self.assertEqual(item["company"], "Acme")

    # ---------- refus ----------

    def test_id_cannot_be_changed(self):
        self.assertRejected("l'id est géré automatiquement", "projects", "face-recognition", {"id": "autre-id"})

    def test_unknown_id(self):
        self.assertRejected("aucun(e) projet avec l'id « robot ». Ids existants : multi-agent-system, face-recognition",
                            "projects", "robot", {"name": "Robot"})

    def test_required_fields_cannot_be_emptied(self):
        self.assertRejected("« company » est obligatoire et ne peut pas être vidé", "experiences", "example-research-company", {"company": ""})
        self.assertRejected("« name » est obligatoire", "projects", "face-recognition", {"name": None})
        self.assertRejected("« school » est obligatoire", "education", "example-university", {"school": "  "})

    def test_invalid_changes(self):
        cases = [
            ({"start_date": "septembre"}, "AAAA-MM"),
            ({"end_date": "2025-01"}, "« end_date » est avant « start_date »"),   # comparé au start_date existant
            ({"priority": "urgent"}, "« priority » doit valoir"),
            ({"skills": "Python"}, "liste de textes"),
            ({"salary": "50k"}, "champ(s) inconnu(s) : salary"),
            ({}, "aucun champ à modifier"),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.assertRejected(expected, "experiences", "example-research-company", changes)

    def test_unknown_section(self):
        self.assertRejected("section inconnue : « skills »", "skills", "programming", {"x": "y"})

    # ---------- anciennes formations sans id ----------

    def test_old_education_without_id(self):
        self.path.write_text(
            MINIMAL + "education:\n  - school: Telecom SudParis\n    degree: Ingénieur\n  - id: mit\n    school: MIT\n"
                      "  - school: Lycée Saint-Louis\n",
            encoding="utf-8",
        )
        # Avant : l'erreur indique la solution
        with self.assertRaises(ItemError) as context:
            update_item("education", "telecom-sudparis", {"degree": "Master"}, self.path)
        self.assertIn("utilise assign_missing_ids()", str(context.exception))

        # assign_missing_ids donne un id aux formations qui n'en ont pas, sans rien changer d'autre
        self.assertEqual(assign_missing_ids(self.path), {1: "telecom-sudparis", 3: "lycee-saint-louis"})
        education = load_profile(self.path).data["education"]
        self.assertEqual([e["id"] for e in education], ["telecom-sudparis", "mit", "lycee-saint-louis"])
        self.assertEqual(education[0], {"id": "telecom-sudparis", "school": "Telecom SudParis", "degree": "Ingénieur"})
        self.assertEqual(assign_missing_ids(self.path), {})   # deuxième fois : rien à faire

        # Ensuite, la formation se modifie normalement
        self.assertEqual(update_item("education", "telecom-sudparis", {"degree": "Master"}, self.path)["degree"], "Master")

    def test_assign_missing_ids_keeps_ids_unique(self):
        self.path.write_text(MINIMAL + "projects:\n  - id: mit\neducation:\n  - school: MIT\n  - school: MIT\n", encoding="utf-8")
        self.assertEqual(assign_missing_ids(self.path), {1: "mit-2", 2: "mit-3"})


if __name__ == "__main__":
    unittest.main()
