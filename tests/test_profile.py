"""
Tests de la lecture et de la validation du profil candidat.
Aucun appel à Claude ni navigateur : ils sont remplacés par des faux (mock).

Lancement :  python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from cv import cli
from cv import pipeline
from candidate.profile import EXAMPLE_PATH, CandidateProfile, ProfileError, load_profile, validate_profile
from cv import generate as generate_cv_module
from cv import verify as verify_cv_module
from cv.document import build_document
from cv_fixtures import fake_draft


MINIMAL = {"personal": {"first_name": "Jane", "last_name": "Doe"}}


def with_profile(**sections) -> dict:
    profile = {"personal": {"first_name": "Jane", "last_name": "Doe"}}
    profile.update(sections)
    return profile


class ValidProfilesTest(unittest.TestCase):

    def test_example_profile_is_valid(self):
        profile = load_profile(EXAMPLE_PATH)
        self.assertEqual(profile.data["personal"]["first_name"], "John")

    def test_minimal_profile_gets_empty_sections(self):
        profile = validate_profile(MINIMAL)
        self.assertEqual(profile["experiences"], [])
        self.assertEqual(profile["projects"], [])
        self.assertEqual(profile["education"], [])
        self.assertEqual(profile["application_rules"], {})
        self.assertEqual(profile["career"], {})

    def test_null_sections_become_empty(self):
        # « experiences: » sans valeur en YAML donne None
        profile = validate_profile(with_profile(experiences=None, projects=None, application_rules=None, skills=None))
        self.assertEqual(profile["experiences"], [])
        self.assertEqual(profile["projects"], [])
        self.assertEqual(profile["application_rules"], {})
        self.assertEqual(profile["skills"], {})

    def test_empty_lists_are_accepted(self):
        profile = validate_profile(with_profile(experiences=[], projects=[]))
        self.assertEqual(profile["experiences"], [])

    def test_items_with_only_an_id_are_accepted(self):
        profile = validate_profile(with_profile(experiences=[{"id": "stage"}], projects=[{"id": "projet"}]))
        self.assertEqual(len(profile["experiences"]), 1)

    def test_empty_contact_fields_are_accepted(self):
        validate_profile({"personal": {"first_name": "Jane", "last_name": "Doe", "email": "", "phone": None}})

    def test_original_data_is_not_modified(self):
        data = with_profile(experiences=None)
        validate_profile(data)
        self.assertIsNone(data["experiences"])


class InvalidProfilesTest(unittest.TestCase):

    def assertProblem(self, data, expected_text):
        with self.assertRaises(ProfileError) as context:
            validate_profile(data)
        message = str(context.exception)
        self.assertIn(expected_text, message)
        self.assertNotIn("Traceback", message)
        return context.exception

    def test_empty_profile(self):
        self.assertProblem(None, "le profil est vide")

    def test_profile_that_is_not_a_mapping(self):
        self.assertProblem(["a", "b"], "suite de sections")

    def test_missing_personal(self):
        self.assertProblem({"experiences": []}, "« personal » est manquante")

    def test_missing_first_name(self):
        self.assertProblem({"personal": {"last_name": "Doe"}}, "personal.first_name est obligatoire")

    def test_null_or_blank_last_name(self):
        self.assertProblem({"personal": {"first_name": "Jane", "last_name": None}}, "personal.last_name est obligatoire")
        self.assertProblem({"personal": {"first_name": "Jane", "last_name": "  "}}, "personal.last_name est obligatoire")

    def test_item_without_id(self):
        self.assertProblem(with_profile(experiences=[{"company": "Acme"}]), "expérience n°1 (« Acme ») : il manque un « id »")

    def test_duplicate_id_in_the_same_list(self):
        self.assertProblem(with_profile(projects=[{"id": "x"}, {"id": "x"}]), "l'id « x » est déjà utilisé par projet n°1")

    def test_duplicate_id_between_experiences_and_projects(self):
        self.assertProblem(with_profile(experiences=[{"id": "x"}], projects=[{"id": "x"}]), "déjà utilisé par expérience n°1")

    def test_education_ids_are_optional_but_unique(self):
        validate_profile(with_profile(education=[{"school": "A"}, {"id": "a", "school": "A"}]))
        self.assertProblem(with_profile(education=[{"id": "x", "school": "A"}], projects=[{"id": "x"}]),
                           "formation n°1 (« A ») : l'id « x » est déjà utilisé par projet n°1")
        self.assertProblem(with_profile(education=[{"id": "", "school": "A"}]), "formation n°1 (« A ») : il manque un « id »")

    def test_item_that_is_not_a_mapping(self):
        self.assertProblem(with_profile(projects=["Mon projet"]), "projet n°1 : doit contenir des champs")

    def test_list_section_with_wrong_type(self):
        self.assertProblem(with_profile(experiences="stage chez Acme"), "« experiences » doit être une liste")

    def test_invalid_limit(self):
        self.assertProblem(with_profile(application_rules={"max_cv_projects": "trois"}), "max_cv_projects doit être un nombre entier positif")

    def test_all_problems_are_reported_at_once(self):
        error = self.assertProblem(
            {"personal": {"first_name": ""}, "experiences": [{"company": "Acme"}]},
            "personal.first_name",
        )
        self.assertEqual(len(error.problems), 3)  # prénom, nom, id manquant


class LoadProfileTest(unittest.TestCase):

    def write(self, text: str) -> Path:
        folder = Path(tempfile.mkdtemp())
        path = folder / "candidate.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_file_explains_how_to_create_it(self):
        with self.assertRaises(ProfileError) as context:
            load_profile(Path(tempfile.mkdtemp()) / "candidate.yaml")
        self.assertIn("cp profile/candidate.example.yaml", str(context.exception))

    def test_invalid_yaml_syntax(self):
        with self.assertRaises(ProfileError) as context:
            load_profile(self.write("personal:\n  first_name: Jane\n last_name: Doe\n"))
        self.assertIn("n'est pas un YAML valide", str(context.exception))

    def test_empty_file(self):
        with self.assertRaises(ProfileError) as context:
            load_profile(self.write(""))
        self.assertIn("le profil est vide", str(context.exception))

    def test_yaml_with_empty_keys(self):
        profile = load_profile(self.write("personal:\n  first_name: Jane\n  last_name: Doe\nexperiences:\nprojects:\n"))
        self.assertEqual(profile.data["experiences"], [])
        self.assertEqual(profile.data["projects"], [])

    def test_profile_keeps_the_file_text_unchanged(self):
        # Claude reçoit le fichier tel qu'il est écrit, commentaires compris
        text = "# mon profil\npersonal:\n  first_name: Jane   # prénom\n  last_name: Doe\nprojects:\n"
        path = self.write(text)
        profile = load_profile(path)
        self.assertIsInstance(profile, CandidateProfile)
        self.assertEqual(profile.text, text)
        self.assertEqual(profile.path, path)
        self.assertEqual(profile.data["projects"], [])


# Réponse de Claude (cv/document.CLAUDE_SCHEMA) pour un profil sans expérience ni projet
FAKE_DRAFT = {
    "company": "Acme", "role": "Stage", "language": "fr", "summary": "Résumé.",
    "experiences": [], "education": [], "projects": [], "skills": [], "languages": [],
    "interests": [], "gaps": [],
}


def profile_from(text: str) -> CandidateProfile:
    path = Path(tempfile.mkdtemp()) / "candidate.yaml"
    path.write_text(text, encoding="utf-8")
    return load_profile(path)


class PipelineIntegrationTest(unittest.TestCase):

    def test_former_main_command_delegates_to_cv_cli(self):
        # « python main.py "<URL>" » reste disponible : il appelle le même pipeline que « python -m cv.cli »
        import main
        self.assertIs(main.main, cli.main)

    def test_invalid_profile_stops_main_before_browser_and_claude(self):
        bad = Path(tempfile.mkdtemp()) / "candidate.yaml"
        bad.write_text("personal:\n  first_name: Jane\n", encoding="utf-8")

        with mock.patch("candidate.profile.CANDIDATE_PATH", bad), \
             mock.patch.object(pipeline, "read_job") as read_job, \
             mock.patch.object(pipeline, "analyze_job") as analyze_job, \
             mock.patch("builtins.print"):
            with self.assertRaises(SystemExit) as context:
                cli.main("https://example.com/job")

        self.assertEqual(context.exception.code, 1)
        read_job.assert_not_called()
        analyze_job.assert_not_called()

    def test_generate_cv_accepts_null_sections(self):
        # Avant la validation, « projects: » vide faisait planter generate_cv après l'appel à Claude
        profile = profile_from("personal:\n  first_name: Jane\n  last_name: Doe\nexperiences:\nprojects:\napplication_rules:\n")

        with mock.patch.object(generate_cv_module, "run_claude", return_value=dict(FAKE_DRAFT)) as run_claude:
            cv = generate_cv_module.generate_cv({"job_title": "Stage"}, profile)

        run_claude.assert_called_once()
        self.assertEqual(cv["header"]["name"], "Jane Doe")
        self.assertEqual(cv["experiences"], [])

    def test_generator_and_verifier_send_the_same_profile_text_to_claude(self):
        text = "# commentaire conservé\npersonal:\n  first_name: Jane\n  last_name: Doe\nexperiences: []\nprojects:\n"
        profile = profile_from(text)

        with mock.patch.object(generate_cv_module, "run_claude", return_value=dict(FAKE_DRAFT)) as generate_claude, \
             mock.patch.object(verify_cv_module, "run_claude", return_value={"issues": []}) as verify_claude:
            cv = generate_cv_module.generate_cv({"job_title": "Stage"}, profile)
            verify_cv_module.verify_cv(cv, profile)

        generate_input = generate_claude.call_args.args[1]
        verify_input = verify_claude.call_args.args[1]
        self.assertIn("=== CANDIDATE PROFILE ===\n" + text, generate_input)
        self.assertIn("=== CANDIDATE PROFILE ===\n" + text, verify_input)

    def test_main_loads_the_profile_once_and_shares_it(self):
        profile = load_profile(EXAMPLE_PATH)
        issues = [{"section": "heading", "cv_text": "x", "problem": "y"}]

        with mock.patch.object(cli, "load_profile", return_value=profile) as load, \
             mock.patch.object(pipeline, "read_job", return_value={"url": "u", "title": "t", "text": "offre"}), \
             mock.patch.object(pipeline, "analyze_job", return_value={"job_title": "Stage", "company": "Acme"}), \
             mock.patch.object(pipeline, "generate_cv", return_value=build_document(fake_draft(), profile)) as generate, \
             mock.patch.object(pipeline, "verify_cv", side_effect=[issues, []]) as verify, \
             mock.patch.object(pipeline, "write_cv", return_value=Path("cv/applications/x/x.tex")) as write, \
             mock.patch.object(pipeline, "compile_cv", return_value=(Path("cv/applications/x/build/x.pdf"), 1)), \
             mock.patch.object(pipeline, "analyze_folder", return_value={"status": "completed",
                                                                        "score": {"value": 70, "level": "Bonne adéquation"}}), \
             mock.patch("builtins.print"):
            cli.main("https://example.com/job")

        load.assert_called_once()
        # 1 rédaction + 1 correction, 2 vérifications : toujours le même objet profil
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(verify.call_count, 2)
        for call in generate.call_args_list:
            self.assertIs(call.args[1], profile)
        for call in verify.call_args_list:
            self.assertIs(call.args[1], profile)
        # La correction reçoit le CV précédent et ses problèmes ; il ne reste aucun problème à l'écriture
        self.assertEqual(generate.call_args_list[1].kwargs["issues"], issues)
        self.assertEqual(write.call_args.kwargs["verification_issues"], [])

    def test_cli_output(self):
        profile = load_profile(EXAMPLE_PATH)
        doc = build_document(fake_draft(), profile)
        issues = [{"section": "experience", "cv_text": "mAP", "problem": "absent"}]
        printed = []
        with mock.patch.object(cli, "load_profile", return_value=profile), \
             mock.patch.object(pipeline, "read_job", return_value={"url": "u", "title": "t", "text": "offre"}), \
             mock.patch.object(pipeline, "analyze_job", return_value={"job_title": "Stage", "company": "Acme"}), \
             mock.patch.object(pipeline, "generate_cv", return_value=doc), \
             mock.patch.object(pipeline, "verify_cv", side_effect=[issues, []]), \
             mock.patch.object(pipeline, "write_cv", return_value=Path("cv/applications/x/x.tex")) as write, \
             mock.patch.object(pipeline, "compile_cv", return_value=(Path("cv/applications/x/build/x.pdf"), 2)), \
             mock.patch.object(pipeline, "analyze_folder", return_value={"status": "completed",
                                                                        "score": {"value": 72, "level": "Bonne adéquation"}}), \
             mock.patch("builtins.print", side_effect=lambda *a: printed.append(" ".join(map(str, a)))):
            cli.main("https://example.com/job")

        self.assertEqual(printed, [
            "1/6 Lecture de l'offre...",
            "2/6 Analyse de l'offre par Claude...",
            "    Stage — Acme",
            "3/6 Rédaction du CV par Claude...",
            "4/6 Vérification du CV contre candidate.yaml...",
            "    1 affirmation(s) absente(s) de ton profil, correction 1/2 :",
            "  - [experience] « mAP » : absent",
            "    OK : tout ce qui est dans le CV vient de ton profil.",
            "5/6 Compilation LaTeX...",
            "6/6 Analyse de correspondance entre l'offre et ton profil...",
            "",
            "Expériences choisies : example-research-company, example-software-company",
            "Projets choisis      : multi-agent-system, face-recognition",
            "Points de l'offre non couverts par ton profil :",
            "  - Pas d'expérience en robotique industrielle.",
            "\nAttention : le CV fait 2 pages au lieu d'une.",
            "\nAdéquation avec l'offre : 72/100 (Bonne adéquation) — détail dans cv/applications/x/analysis.json",
            "\nCV généré : cv/applications/x/build/x.pdf",
        ])
        # L'URL est gardée avec l'offre (offer.json), sans être envoyée à Claude
        self.assertEqual(write.call_args.args[1]["source_url"], "https://example.com/job")
        self.assertEqual(write.call_args.kwargs["verification_issues"], [])

    def test_generator_sends_structured_request_without_latex(self):
        profile = load_profile(EXAMPLE_PATH)
        with mock.patch.object(generate_cv_module, "run_claude", return_value=fake_draft()) as claude:
            doc = generate_cv_module.generate_cv({"job_title": "Stage"}, profile)
        prompt, stdin, schema = claude.call_args.args[:3]
        self.assertIs(schema, generate_cv_module.CLAUDE_SCHEMA)
        self.assertNotIn("=== TEMPLATE ===", stdin)
        self.assertIn("=== EDUCATION KEYS ===\nexample-engineering-school: Example Engineering School", stdin)
        self.assertNotIn("\\resumeItemPlain", prompt)
        self.assertIn("Never add a VERIFIABLE fact that is not in the profile", prompt)   # règles inchangées
        self.assertEqual(doc["experiences"][0]["dates"], "2026")

        issues = [{"section": "experience", "cv_text": "x", "problem": "y"}]
        with mock.patch.object(generate_cv_module, "run_claude", return_value=fake_draft()) as claude:
            generate_cv_module.generate_cv({"job_title": "Stage"}, profile, previous_cv=doc, issues=issues)
        prompt, stdin = claude.call_args.args[:2]
        self.assertIn("=== CORRECTION ===", prompt)
        self.assertIn('"unsupported_statements"', stdin)
        self.assertIn('"source_id": "example-research-company"', stdin)

    def test_verifier_reads_the_cv_content_not_latex(self):
        profile = load_profile(EXAMPLE_PATH)
        doc = build_document(fake_draft(), profile)
        with mock.patch.object(verify_cv_module, "run_claude", return_value={"issues": []}) as claude:
            self.assertEqual(verify_cv_module.verify_cv(doc, profile), [])
        prompt, stdin = claude.call_args.args[:2]
        self.assertIn("--- SECTION: experience ---\nStagiaire Vision par Ordinateur", stdin)
        self.assertNotIn("\\textbf", stdin)
        self.assertIn("the content of each section", prompt)


if __name__ == "__main__":
    unittest.main()
