"""
Tests du CV structuré (cv/document.py) : construction à partir de la réponse de Claude,
validation, identifiants du profil, manipulation des listes, sauvegarde et relecture de cv.json.
Profils fictifs dans des fichiers temporaires ; aucun appel à Claude.

Lancement :  python -m unittest discover tests
"""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from candidate import manager
from candidate.profile import EXAMPLE_PATH, load_profile
from cv.document import (CVDocumentError, build_document, document_text, education_keys, entry_from_profile,
                         load_document, save_document, selected_ids, validate_document)
from cv.render import render_sections
from cv_fixtures import example_profile, fake_draft


class TempDirTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)

    def profile_with(self, old: str, new: str):
        path = self.folder / "candidate.yaml"
        text = EXAMPLE_PATH.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return load_profile(path)


class BuildDocumentTest(TempDirTest):

    def setUp(self):
        super().setUp()
        self.profile = example_profile()
        self.doc = build_document(fake_draft(), self.profile)

    def test_facts_come_from_the_profile(self):
        doc = self.doc
        self.assertEqual(doc["header"]["name"], "John Doe")
        self.assertEqual([c["type"] for c in doc["header"]["contacts"]], ["email", "phone", "linkedin", "github"])
        experience = doc["experiences"][0]
        self.assertEqual((experience["location"], experience["dates"]), ("Paris", "2026"))       # 2026-02 → 2026-08
        self.assertEqual(doc["experiences"][1]["dates"], "2024")
        self.assertEqual(doc["education"][0]["dates"], "2022–2026")
        self.assertEqual(doc["projects"][0]["link"], {"url": "https://github.com/johndoe/example-project", "label": "GitHub"})
        self.assertIsNone(doc["projects"][1]["link"])                                             # github_url: ""
        self.assertEqual(selected_ids(doc), (["example-research-company", "example-software-company"],
                                             ["multi-agent-system", "face-recognition"]))

    def test_claude_cannot_provide_facts(self):
        draft = fake_draft()
        draft["experiences"][0].update(dates="1999–2030", location="Tokyo")       # ignoré : vient du profil
        draft["experiences"][1]["context"] = "   "
        doc = build_document(draft, self.profile)
        self.assertEqual((doc["experiences"][0]["dates"], doc["experiences"][0]["location"]), ("2026", "Paris"))
        self.assertNotIn("1999", json.dumps(doc))
        self.assertIsNone(doc["experiences"][1]["context"])

    def test_empty_contacts_are_left_out(self):
        profile = self.profile_with('  phone: "+33 6 00 00 00 00"\n', '  phone: ""\n')
        doc = build_document(fake_draft(), profile)
        self.assertEqual([c["type"] for c in doc["header"]["contacts"]], ["email", "linkedin", "github"])

    def test_empty_bullets_skills_and_lists_are_cleaned(self):
        draft = fake_draft()
        draft["experiences"][0]["bullets"].append("   ")
        draft["skills"].append({"label": "Vide", "items": [" "]})
        draft["projects"], draft["interests"] = [], []
        doc = build_document(draft, self.profile)
        self.assertEqual(len(doc["experiences"][0]["bullets"]), 2)
        self.assertNotIn("Vide", [g["label"] for g in doc["skills"]])
        self.assertEqual(doc["projects"], [])
        self.assertNotIn("\\section*", render_sections(doc)["projects"])                       # section masquée

    def test_unknown_duplicate_and_too_many_items_are_refused(self):
        cases = []
        draft = fake_draft()
        draft["experiences"][0]["source_id"] = "inventee"
        cases.append((draft, "n'existent pas dans le profil"))
        draft = fake_draft()
        draft["projects"].append(copy.deepcopy(draft["projects"][0]))
        cases.append((draft, "plusieurs fois"))
        draft = fake_draft()
        draft["education"][0]["source_id"] = "example-school-inventee"
        cases.append((draft, "formations qui n'existent pas"))
        for draft, expected in cases:
            with self.subTest(expected):
                with self.assertRaises(CVDocumentError) as context:
                    build_document(draft, self.profile)
                self.assertIn(expected, str(context.exception))

    def test_limits_of_the_profile_rules(self):
        profile = self.profile_with("max_cv_projects: 3", "max_cv_projects: 1")
        with self.assertRaises(CVDocumentError) as context:
            build_document(fake_draft(), profile)
        self.assertIn("Claude a choisi 2 projets, le maximum est 1.", str(context.exception))


class EducationKeysTest(TempDirTest):

    LEGACY = """  - school: Lycée Saint-Louis
    degree: CPGE
  - school: Lycée Saint-Louis
    degree: Option informatique
  - school: ""
"""

    def test_keys_without_ids_are_stable_and_match_assign_missing_ids(self):
        profile = self.profile_with("\nexperiences:\n", "\n" + self.LEGACY + "\nexperiences:\n")
        keys = [key for key, _ in education_keys(profile.data)]
        self.assertEqual(keys, ["example-engineering-school", "example-university",
                                "lycee-saint-louis", "lycee-saint-louis-2", "formation"])
        self.assertEqual(keys, [key for key, _ in education_keys(profile.data)])               # stables

        # Le profil n'est pas modifié ; s'il reçoit des id plus tard, ce sont les mêmes
        before = profile.path.read_bytes()
        build_document({**fake_draft(), "education": [
            {"source_id": "lycee-saint-louis-2", "institution": "Lycée Saint-Louis", "bullets": []}]}, profile)
        self.assertEqual(profile.path.read_bytes(), before)
        manager.assign_missing_ids(profile.path)
        assigned = [item["id"] for item in load_profile(profile.path).data["education"]]
        self.assertEqual(assigned, keys)


class ValidationTest(unittest.TestCase):

    def setUp(self):
        self.profile = example_profile()
        self.doc = build_document(fake_draft(), self.profile)

    def assertInvalid(self, doc, expected, profile_data=None):
        with self.assertRaises(CVDocumentError) as context:
            validate_document(doc, profile_data)
        self.assertTrue(any(expected in problem for problem in context.exception.problems), context.exception.problems)

    def test_valid_document(self):
        validate_document(self.doc, self.profile.data)
        empty = copy.deepcopy(self.doc)
        for key in ("experiences", "education", "projects", "skills", "languages", "interests", "gaps"):
            empty[key] = []
        validate_document(empty, self.profile.data)

    def test_invalid_documents(self):
        def changed(change):
            doc = copy.deepcopy(self.doc)
            change(doc)
            return doc

        cases = [
            (lambda d: d.pop("skills"), "champ(s) manquant(s) : skills"),
            (lambda d: d.update(extra=1), "champ(s) inconnu(s) : extra"),
            (lambda d: d.update(schema_version=2), "schema_version 2"),
            (lambda d: d.update(language="de"), "language"),
            (lambda d: d["header"].update(name=" "), "header.name"),
            (lambda d: d["header"]["contacts"].append({"type": "fax", "value": "1"}), "header.contacts[4].type"),
            (lambda d: d["header"]["contacts"][2].update(value="linkedin.com/in/x"), "http"),
            (lambda d: d["experiences"][0]["bullets"].append(""), "experiences[0].bullets"),
            (lambda d: d["experiences"][0].update(bullets="une seule"), "experiences[0].bullets"),
            (lambda d: d["experiences"][0].pop("dates"), "experiences[0] : champ(s) manquant(s) : dates"),
            (lambda d: d["experiences"][0].update(note="x"), "champ(s) inconnu(s) : note"),
            (lambda d: d["projects"][0].update(link={"url": "github.com/x", "label": "GitHub"}), "projects[0].link"),
            (lambda d: d["skills"][0].update(items=[]), "ne peut pas être vide"),
            (lambda d: d["languages"].append({"name": ""}), "languages[3]"),
            (lambda d: d["interests"].append(3), "interests"),
            (lambda d: d["experiences"].append(copy.deepcopy(d["experiences"][0])), "déjà dans le CV"),
        ]
        for change, expected in cases:
            with self.subTest(expected):
                self.assertInvalid(changed(change), expected)

    def test_source_ids_are_checked_against_the_profile(self):
        doc = copy.deepcopy(self.doc)
        doc["projects"][0]["source_id"] = "projet-supprime-du-profil"
        validate_document(doc)                                                    # sans profil : structure seule
        self.assertInvalid(doc, "« projet-supprime-du-profil » n'existe pas dans le profil", self.profile.data)


class ManipulationTest(unittest.TestCase):
    """Ajouter, retirer et réordonner = modifier les listes du JSON."""

    def setUp(self):
        self.profile = example_profile()
        self.doc = build_document(fake_draft(), self.profile)

    def test_add_an_element_from_the_profile(self):
        entry = entry_from_profile("projects", "bioinformatics-project", self.profile.data)
        self.assertEqual(entry, {"source_id": "bioinformatics-project", "name": "Bioinformatics Project", "link": None,
                                 "bullets": ["Analyzed genomic sequences", "Implemented sequence alignment methods",
                                             "Studied evolutionary relationships"]})
        self.doc["projects"].append(entry)
        validate_document(self.doc, self.profile.data)
        self.assertIn("Bioinformatics Project", render_sections(self.doc)["projects"])

        education = entry_from_profile("education", "example-university", self.profile.data)
        self.assertEqual((education["location"], education["dates"]), ("Europe", "2025–2026"))
        with self.assertRaises(CVDocumentError):
            entry_from_profile("experiences", "inconnue", self.profile.data)

        self.doc["projects"].append(copy.deepcopy(entry))                          # deux fois : refusé
        with self.assertRaises(CVDocumentError):
            validate_document(self.doc, self.profile.data)

    def test_remove_an_element_without_touching_the_profile(self):
        before = EXAMPLE_PATH.read_bytes()
        del self.doc["experiences"][1]
        validate_document(self.doc, self.profile.data)
        self.assertNotIn("Example Software Company", render_sections(self.doc)["experience"])
        self.assertEqual(EXAMPLE_PATH.read_bytes(), before)
        self.doc["experiences"] = []
        self.assertNotIn("\\section*", render_sections(self.doc)["experience"])

    def test_reorder_elements_bullets_skills(self):
        self.doc["experiences"].reverse()
        self.doc["experiences"][1]["bullets"].reverse()
        self.doc["skills"].insert(0, self.doc["skills"].pop())
        self.doc["skills"][0]["items"].sort()
        validate_document(self.doc, self.profile.data)
        sections = render_sections(self.doc)
        experience = sections["experience"]
        self.assertLess(experience.index("Example Software Company"), experience.index("Example Research Company"))
        self.assertLess(experience.index("Amélioration du mAP"), experience.index("Évaluation d'architectures"))
        self.assertIn("\\textbf{Outils :} & Docker, Git, Jupyter, Linux \\\\\n    \\textbf{Programmation :}",
                      sections["technical-skills"])

    def test_edit_texts_and_bullets(self):
        self.doc["header"]["summary"] = "Résumé **modifié** à la main."
        self.doc["experiences"][0]["bullets"][0] = "Puce corrigée & complétée."
        self.doc["experiences"][0]["bullets"].append("Nouvelle puce.")
        validate_document(self.doc, self.profile.data)
        sections = render_sections(self.doc)
        self.assertIn("Résumé \\textbf{modifié} à la main.", sections["heading"])
        self.assertIn("\\resumeItemPlain{Puce corrigée \\& complétée.}", sections["experience"])
        self.assertIn("\\resumeItemPlain{Nouvelle puce.}", sections["experience"])


class SaveLoadTest(TempDirTest):

    def test_round_trip(self):
        doc = build_document(fake_draft(), example_profile())
        path = save_document(self.folder, doc)
        self.assertEqual(path.name, "cv.json")
        self.assertEqual(load_document(self.folder), doc)
        self.assertIn('"summary": "Jeune diplômé', path.read_text(encoding="utf-8"))           # UTF-8 lisible

    def test_invalid_documents_are_not_saved_nor_loaded(self):
        doc = build_document(fake_draft(), example_profile())
        doc["experiences"][0]["title"] = ""
        with self.assertRaises(CVDocumentError):
            save_document(self.folder, doc)
        self.assertFalse((self.folder / "cv.json").exists())

        with self.assertRaises(CVDocumentError) as context:
            load_document(self.folder)
        self.assertIn("n'existe pas", str(context.exception))
        (self.folder / "cv.json").write_text("{pas du json", encoding="utf-8")
        with self.assertRaises(CVDocumentError):
            load_document(self.folder)


class DocumentTextTest(unittest.TestCase):

    def test_readable_content_without_latex(self):
        doc = build_document(fake_draft(), example_profile())
        text = document_text(doc)
        self.assertEqual(list(text), ["heading", "experience", "education", "projects", "technical-skills", "interests"])
        self.assertIn("Stagiaire Vision par Ordinateur — Example Research Company (Recherche appliquée) | Paris, 2026",
                      text["experience"])
        self.assertIn("- Amélioration du mAP de 0,61 à 0,74", text["experience"])
        self.assertIn("Languages: Français (langue maternelle)", text["technical-skills"])
        self.assertNotIn("\\", "".join(text.values()))


if __name__ == "__main__":
    unittest.main()
