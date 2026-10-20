"""
Tests de l'import d'un CV PDF. Claude est remplacé par un faux (mock) : aucun appel réel.
Les PDF de test sont créés à la volée dans des dossiers temporaires.

Lancement :  python -m unittest discover tests
"""

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from pypdf import PdfReader, PdfWriter

from candidate.import_cv import CVImportError, _fix_accents, extract_pdf_text, import_cv as run_import
from llm import extract_profile
from llm.extract_profile import EXTRACTION_SCHEMA, ITEM_FIELDS, PERSONAL_FIELDS, _clean_extraction
from candidate.profile import CANDIDATE_PATH, EXAMPLE_PATH


ROOT = Path(__file__).resolve().parents[1]

CV_LINES = [
    "Jane Doe - jane.doe@example.com - +33 6 12 34 56 78",
    "Experience",
    "Data Scientist Intern - Acme Robotics - Lyon - 2024-09 to 2025-02",
    "Trained object detection models with PyTorch",
    "Reduced inference time by 30 percent",
    "Education",
    "Ecole Polytechnique - Master of Science in Data Science - 2023 to 2025",
    "Projects",
    "Drone Detector - YOLO based drone detection",
    "Skills: Python, PyTorch, SQL, Docker",
    "Languages: French (native), English (C1)",
    "Interests: Tennis, Chess",
]


def make_pdf(path: Path, lines: list[str]) -> Path:
    """PDF d'une page avec du vrai texte (police Helvetica)."""
    content = "\n".join(
        f"BT /F1 10 Tf 50 {780 - 16 * number} Td ({line}) Tj ET" for number, line in enumerate(lines)
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
    ]
    out, offsets = "%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    path.write_bytes(out.encode("latin-1"))
    return path


def fake_claude_answer() -> dict:
    """Réponse de Claude telle que le schéma l'impose (champs non trouvés à null / [])."""
    empty_personal = {field: None for field in PERSONAL_FIELDS}

    def item(section, **values):
        entry = {field: [] if field in ("responsibilities", "achievements", "skills", "details") else None
                 for field in ITEM_FIELDS[section]}
        entry.update(values)
        entry.setdefault("uncertain_fields", [])
        return entry

    return {
        "personal": {**empty_personal, "first_name": "Jane", "last_name": "Doe", "email": "jane.doe@example.com",
                     "phone": "+33 6 12 34 56 78", "uncertain_fields": []},
        "experiences": [item("experiences", company="Acme Robotics", title="Data Scientist Intern", location="Lyon",
                             start_date="2024-09", end_date="2025-02",
                             responsibilities=["Trained object detection models with PyTorch"],
                             achievements=["Reduced inference time by 30 percent"], skills=["PyTorch"])],
        "projects": [item("projects", name="Drone Detector", description="YOLO based drone detection")],
        "education": [item("education", school="Ecole Polytechnique", degree="Master of Science",
                           specialization="Data Science", start_date="2023", end_date="2025",
                           uncertain_fields=["start_date"])],
        "skills": [{"category": "programming", "skills": ["Python", "SQL"]},
                   {"category": "Machine Learning", "skills": ["PyTorch"]},
                   {"category": "tools", "skills": ["Docker"]}],
        "languages": [{"language": "French", "level": "native"}, {"language": "English", "level": "C1"}],
        "interests": ["Tennis", "Chess"],
        "warnings": [],
    }


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class PdfTextTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)

    def test_extracts_text_from_a_pdf(self):
        text = extract_pdf_text(make_pdf(self.folder / "cv.pdf", CV_LINES))
        self.assertIn("Acme Robotics", text)
        self.assertIn("jane.doe@example.com", text)

    def test_missing_file(self):
        with self.assertRaises(CVImportError) as context:
            extract_pdf_text(self.folder / "absent.pdf")
        self.assertIn("n'existe pas", str(context.exception))

    def test_file_that_is_not_a_pdf(self):
        fake = self.folder / "cv.pdf"
        fake.write_text("ceci n'est pas un PDF", encoding="utf-8")
        with self.assertRaises(CVImportError) as context:
            extract_pdf_text(fake)
        self.assertIn("n'est pas un PDF lisible", str(context.exception))

    def test_pdf_without_text_like_a_scan(self):
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with open(self.folder / "scan.pdf", "wb") as file:
            writer.write(file)
        with self.assertRaises(CVImportError) as context:
            extract_pdf_text(self.folder / "scan.pdf")
        self.assertIn("ne contient pas de texte exploitable", str(context.exception))
        self.assertIn("OCR", str(context.exception))

    def test_password_protected_pdf(self):
        writer = PdfWriter(clone_from=PdfReader(make_pdf(self.folder / "cv.pdf", CV_LINES)))
        writer.encrypt("secret")
        with open(self.folder / "protected.pdf", "wb") as file:
            writer.write(file)
        with self.assertRaises(CVImportError) as context:
            extract_pdf_text(self.folder / "protected.pdf")
        self.assertIn("protégé par un mot de passe", str(context.exception))

    def test_latex_separated_accents_are_fixed(self):
        self.assertEqual(_fix_accents("d´ eveloppement, int´ erˆ et, Exp´erience, fran¸ cais, probl` emes, ´ Ecole"),
                         "développement, intérêt, Expérience, français, problèmes, École")


class CleanExtractionTest(unittest.TestCase):

    def setUp(self):
        self.text = "\n".join(CV_LINES)

    def test_format_of_the_profile(self):
        result = _clean_extraction(fake_claude_answer(), self.text)

        self.assertEqual(result["personal"], {"first_name": "Jane", "last_name": "Doe",
                                              "email": "jane.doe@example.com", "phone": "+33 6 12 34 56 78"})
        # Champs vides retirés, champs présents conservés
        self.assertEqual(result["projects"], [{"name": "Drone Detector", "description": "YOLO based drone detection"}])
        # Compétences au format du profil : {catégorie: [compétences]}
        self.assertEqual(result["skills"], {"programming": ["Python", "SQL"], "machine_learning": ["PyTorch"], "tools": ["Docker"]})
        self.assertEqual(result["languages"], [{"language": "French", "level": "native"}, {"language": "English", "level": "C1"}])
        self.assertEqual(result["interests"], ["Tennis", "Chess"])
        self.assertEqual(result["warnings"], [])

    def test_uncertain_fields_are_kept_only_for_present_fields(self):
        answer = fake_claude_answer()
        answer["education"][0]["uncertain_fields"] = ["start_date", "location"]   # location est null
        education = _clean_extraction(answer, self.text)["education"][0]
        self.assertEqual(education["uncertain_fields"], ["start_date"])

    def test_values_not_in_the_cv_are_flagged(self):
        answer = fake_claude_answer()
        answer["experiences"][0]["company"] = "Google"           # absent du CV
        answer["skills"][0]["skills"].append("Kubernetes")       # absent du CV
        answer["languages"].append({"language": "German", "level": None})
        result = _clean_extraction(answer, self.text)

        self.assertEqual(result["experiences"][0]["uncertain_fields"], ["company"])
        self.assertTrue(any("« Google »" in warning for warning in result["warnings"]))
        self.assertTrue(any("« Kubernetes »" in warning for warning in result["warnings"]))
        self.assertTrue(any("« German »" in warning for warning in result["warnings"]))
        self.assertEqual(result["languages"][-1], {"language": "German"})   # niveau absent : champ retiré

    def test_badly_formatted_dates_are_removed(self):
        answer = fake_claude_answer()
        answer["experiences"][0]["start_date"] = "septembre 2024"
        answer["personal"]["birth_date"] = "18/06/2001"
        result = _clean_extraction(answer, self.text)

        self.assertNotIn("start_date", result["experiences"][0])
        self.assertNotIn("birth_date", result["personal"])
        self.assertEqual(sum("a été retirée" in warning for warning in result["warnings"]), 2)

    def test_empty_answer(self):
        empty = {"personal": {}, "experiences": [], "projects": [], "education": [], "skills": [],
                 "languages": [], "interests": [], "warnings": []}
        self.assertEqual(_clean_extraction(empty, self.text), {**empty, "skills": {}})


class ImportCvTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.imports = self.folder / "imports"
        self.extracted = self.folder / "extracted"
        self.pdf = make_pdf(self.folder / "Mon CV 2025.pdf", CV_LINES)

    def run_import(self, pdf=None):
        with mock.patch.object(extract_profile, "run_claude", return_value=fake_claude_answer()) as claude:
            output = run_import(pdf or self.pdf, imports_dir=self.imports, extracted_dir=self.extracted)
        return output, claude

    def test_writes_a_json_proposal(self):
        output, claude = self.run_import()

        claude.assert_called_once()
        self.assertIn("Acme Robotics", claude.call_args.args[1])        # le texte du CV est envoyé à Claude
        self.assertEqual(output.parent, self.extracted)
        self.assertRegex(output.name, r"^Mon-CV-2025-\d{8}-\d{6}\.json$")

        saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "proposal")
        self.assertEqual(saved["source_pdf"], "Mon CV 2025.pdf")
        self.assertEqual(saved["profile"]["experiences"][0]["company"], "Acme Robotics")
        self.assertEqual(set(saved["profile"]),
                         {"personal", "experiences", "projects", "education", "skills", "languages", "interests"})
        self.assertIsInstance(saved["warnings"], list)

    def test_pdf_is_copied_to_imports(self):
        self.run_import()
        copies = list(self.imports.iterdir())
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_bytes(), self.pdf.read_bytes())
        self.assertTrue(self.pdf.exists())   # l'original n'est pas déplacé

    def test_pdf_already_in_imports_is_not_copied_again(self):
        self.imports.mkdir()
        inside = make_pdf(self.imports / "cv.pdf", CV_LINES)
        output, _ = self.run_import(inside)
        self.assertEqual([p.name for p in self.imports.iterdir()], ["cv.pdf"])
        self.assertEqual(json.loads(output.read_text())["imported_pdf"], str(inside.resolve()))

    def test_unreadable_pdf_does_not_call_claude(self):
        bad = self.folder / "scan.pdf"
        bad.write_bytes(b"%PDF-1.4 rien de lisible")
        with mock.patch.object(extract_profile, "run_claude") as claude:
            with self.assertRaises(CVImportError):
                run_import(bad, imports_dir=self.imports, extracted_dir=self.extracted)
        claude.assert_not_called()
        self.assertFalse(self.extracted.exists())

    def test_candidate_profile_is_not_modified(self):
        fake_profile = self.folder / "candidate.yaml"
        fake_profile.write_text("personal:\n  first_name: Jane\n  last_name: Doe\n", encoding="utf-8")
        before_private = sha(CANDIDATE_PATH)
        with mock.patch("candidate.profile.CANDIDATE_PATH", fake_profile):
            self.run_import()
        self.assertEqual(fake_profile.read_text(encoding="utf-8"), "personal:\n  first_name: Jane\n  last_name: Doe\n")
        self.assertEqual(sha(CANDIDATE_PATH), before_private)


class StructureTest(unittest.TestCase):

    def test_extracted_fields_exist_in_the_example_profile(self):
        # Le profil d'exemple sert de référence : chaque champ extrait doit y exister
        example = yaml.safe_load(EXAMPLE_PATH.read_text(encoding="utf-8"))
        self.assertTrue(set(PERSONAL_FIELDS) <= set(example["personal"]))
        for section, fields in ITEM_FIELDS.items():
            known = {field for entry in example[section] for field in entry}
            self.assertTrue(set(fields) <= known, f"{section} : {set(fields) - known}")
        self.assertEqual(set(EXTRACTION_SCHEMA["required"]) - {"warnings"},
                         {"personal", "education", "experiences", "projects", "skills", "languages", "interests"})

    def test_private_folders_are_ignored_by_git(self):
        for path in ("profile/private/imports/mon-cv.pdf", "profile/private/extracted/mon-cv.json"):
            result = subprocess.run(["git", "-c", "core.excludesfile=/dev/null", "check-ignore", "--no-index", path],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{path} n'est pas ignoré par Git")


if __name__ == "__main__":
    unittest.main()
