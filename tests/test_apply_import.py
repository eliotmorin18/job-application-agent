"""
Tests de l'application des décisions après l'import d'un CV.
Tout se passe dans des fichiers temporaires ; aucun appel à Claude.

Lancement :  python -m unittest discover tests
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from candidate import manager
from candidate.apply_import import DecisionError, apply_import
from candidate.profile import CANDIDATE_PATH, load_profile
from candidate.review_import import review_import


PROFILE = """# Mon profil
personal:
  first_name: Jane
  last_name: Doe
  email: jane.doe@example.com
  city: Paris

education:
  - school: Lycee Saint-Louis
    degree: CPGE
  - school: Telecom SudParis
    degree: Ingénieur
    start_date: "2023-09"

experiences:
  - id: cnrs-aubay
    company: CNRS Foundation - via Aubay
    title: Research Intern
    start_date: "2026-02"
    location: Paris, France
    responsibilities:
      - État de l'art
    context: Projet Science4Reefs.

# Mes projets
projects:
  - id: cassiopee
    name: Cassiopée

skills:
  programming:
    - Python

languages:
  - language: French
    level: Native

interests:
  - Tennis
"""

EXTRACTION = {
    "status": "proposal",
    "source_pdf": "cv.pdf",
    "profile": {
        "personal": {"first_name": "Jane", "email": "jane.doe@example.com", "phone": "+33 6 11 22 33 44",
                     "city": "Paris", "linkedin": "https://linkedin.com/in/janedoe"},
        "experiences": [
            {"company": "Fondation CNRS (Aubay)", "title": "Stagiaire Recherche IA", "start_date": "2026",
             "end_date": "2026", "responsibilities": ["État de l'art", "Prototypes avec SAM"], "skills": ["SAM"],
             "uncertain_fields": ["start_date", "end_date"]},
            {"company": "Dassault Systèmes", "title": "Stagiaire IA", "start_date": "2027-01"},
        ],
        "projects": [{"name": "Projet Cassiopée", "achievements": ["1er prix sur 200 projets"]},
                     {"name": "Drone Detector", "description": "Détection de drones."}],
        "education": [{"school": "Telecom SudParis", "degree": "Cursus d'ingénieur", "start_date": "2023",
                       "details": ["Machine learning"]}],
        "skills": {"programming": ["python", "Rust"], "cloud": ["AWS"]},
        "languages": [{"language": "Français", "level": "C2"}, {"language": "Espagnol"}],
        "interests": ["Tennis", "Chess"],
    },
    "warnings": ["Dates à vérifier."],
}


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class ApplyImportTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.profile = self.folder / "candidate.yaml"
        self.profile.write_text(PROFILE, encoding="utf-8")
        self.json = self.folder / "import.json"
        self.json.write_text(json.dumps(EXTRACTION, ensure_ascii=False), encoding="utf-8")

    def apply(self, decisions):
        return apply_import(self.json, decisions, self.profile)

    def data(self):
        return load_profile(self.profile).data

    def item(self, section, item_id):
        return next(entry for entry in self.data()[section] if entry.get("id") == item_id)

    def assertRefused(self, decisions, expected):
        before = self.profile.read_text(encoding="utf-8")
        with self.assertRaises(DecisionError) as context:
            self.apply(decisions)
        self.assertIn(expected, str(context.exception))
        self.assertEqual(self.profile.read_text(encoding="utf-8"), before, "rien ne doit être enregistré")
        self.assertEqual([p.name for p in self.folder.iterdir()], sorted(["candidate.yaml", "import.json"]) and
                         [p.name for p in self.folder.iterdir()])   # pas de fichier temporaire oublié
        self.assertFalse(any(p.name.endswith(".import-tmp") for p in self.folder.iterdir()))
        return context.exception

    # ---------- les proposition_id utilisés ----------

    def test_review_gives_the_proposal_ids(self):
        review = review_import(self.json, self.profile)
        self.assertEqual([p["proposal_id"] for p in review["experiences"]], ["experiences-1", "experiences-2"])
        self.assertEqual([p["proposal_id"] for p in review["skills"]], ["skills-1", "skills-2", "skills-3"])
        self.assertEqual(review["experiences"][0]["status"], "probable_duplicate")
        self.assertEqual(review["experiences"][1]["status"], "new")

    # ---------- ajouts ----------

    def test_add_new_elements(self):
        report = self.apply({
            "experiences-2": {"action": "add"},
            "projects-2": {"action": "add"},
            "skills-2": {"action": "add"},                                  # Rust, dans programming
            "skills-3": {"action": "add", "create_category": True},         # AWS, nouvelle catégorie cloud
            "languages-2": {"action": "add", "level": "A2"},
            "interests-2": {"action": "add"},
        })
        self.assertEqual({(entry["section"], entry.get("id") or entry.get("value")) for entry in report["added"]}, {
            ("experiences", "dassault-systemes"), ("projects", "drone-detector"), ("skills", "Rust"),
            ("skills", "AWS"), ("languages", "Espagnol"), ("interests", "Chess"),
        })
        data = self.data()
        self.assertEqual(self.item("experiences", "dassault-systemes")["start_date"], "2027-01")
        self.assertEqual(data["skills"], {"programming": ["Python", "Rust"], "cloud": ["AWS"]})
        self.assertEqual(data["languages"][-1], {"language": "Espagnol", "level": "A2"})
        self.assertEqual(data["interests"], ["Tennis", "Chess"])

    def test_add_only_some_fields(self):
        self.apply({"projects-2": {"action": "add", "fields": ["name"]}})
        self.assertEqual(self.item("projects", "drone-detector"), {"id": "drone-detector", "name": "Drone Detector"})

    # ---------- modifications ----------

    def test_partial_update_keeps_id_and_other_fields(self):
        report = self.apply({"experiences-1": {"action": "update", "target_id": "cnrs-aubay",
                                               "fields": ["responsibilities", "skills", "end_date"]}})
        experience = self.item("experiences", "cnrs-aubay")
        self.assertEqual(experience["responsibilities"], ["État de l'art", "Prototypes avec SAM"])   # complétée, rien retiré
        self.assertEqual(experience["skills"], ["SAM"])
        self.assertEqual(experience["end_date"], "2026")
        self.assertEqual(experience["company"], "CNRS Foundation - via Aubay")    # non choisi : inchangé
        self.assertEqual(experience["start_date"], "2026-02")
        self.assertEqual(experience["context"], "Projet Science4Reefs.")
        self.assertEqual(report["updated"][0]["id"], "cnrs-aubay")
        self.assertEqual(report["updated"][0]["fields"], ["responsibilities", "skills", "end_date"])

    def test_clear_an_optional_field(self):
        self.apply({"experiences-1": {"action": "update", "target_id": "cnrs-aubay", "fields": ["title"], "clear": ["context"]}})
        experience = self.item("experiences", "cnrs-aubay")
        self.assertNotIn("context", experience)
        self.assertEqual(experience["title"], "Stagiaire Recherche IA")

    def test_less_precise_value_needs_explicit_choice(self):
        self.assertRefused({"experiences-1": {"action": "update", "target_id": "cnrs-aubay", "fields": ["start_date"]}},
                           "« 2026 » est moins précis que « 2026-02 »")
        self.apply({"experiences-1": {"action": "update", "target_id": "cnrs-aubay", "fields": ["start_date"],
                                      "allow_less_precise": True}})
        self.assertEqual(self.item("experiences", "cnrs-aubay")["start_date"], "2026")

    def test_less_precise_location_is_refused(self):
        extraction = json.loads(self.json.read_text(encoding="utf-8"))
        extraction["profile"]["experiences"][0]["location"] = "Paris"
        self.json.write_text(json.dumps(extraction, ensure_ascii=False), encoding="utf-8")
        self.assertRefused({"experiences-1": {"action": "update", "target_id": "cnrs-aubay", "fields": ["location"]}},
                           "« Paris » est moins précis que « Paris, France »")

    def test_update_language_level_and_personal_fields(self):
        report = self.apply({"languages-1": {"action": "update"},
                             "personal": {"action": "update", "fields": ["phone", "linkedin"]}})
        data = self.data()
        self.assertEqual(data["languages"], [{"language": "French", "level": "C2"}])
        self.assertEqual(data["personal"]["phone"], "+33 6 11 22 33 44")
        self.assertEqual(data["personal"]["city"], "Paris")          # non choisi : inchangé
        self.assertEqual({entry["section"] for entry in report["updated"]}, {"languages", "personal"})

    # ---------- formations sans id ----------

    def test_old_education_without_id(self):
        review = review_import(self.json, self.profile)
        match = review["education"][0]["matches"][0]
        self.assertIsNone(match["id"])
        self.assertEqual(match["position"], 2)

        report = self.apply({"education-1": {"action": "update", "target_position": 2, "fields": ["details"]}})
        education = self.data()["education"]
        self.assertEqual(education[1]["id"], "telecom-sudparis")             # seule la formation visée reçoit un id
        self.assertEqual(education[1]["details"], ["Machine learning"])
        self.assertEqual(education[1]["degree"], "Ingénieur")
        self.assertNotIn("id", education[0])                                  # l'autre formation n'est pas touchée
        self.assertTrue(report["updated"][0]["id_assigned"])

    # ---------- ignorées ----------

    def test_skip_and_missing_decisions_change_nothing(self):
        before = sha(self.profile)
        report = self.apply({"experiences-1": {"action": "skip"}, "personal": {"action": "skip"}})
        self.assertEqual(sha(self.profile), before)
        self.assertEqual(report["added"], [])
        self.assertEqual(report["updated"], [])
        reasons = {entry["proposal_id"]: entry["reason"] for entry in report["skipped"]}
        self.assertEqual(reasons["experiences-1"], "ignorée")
        self.assertEqual(reasons["experiences-2"], "aucune décision")       # pas de décision : jamais appliqué
        self.assertEqual(len(report["skipped"]), 13)                         # 12 propositions + personal

    # ---------- doublons ----------

    def test_duplicates_are_never_added_without_confirmation(self):
        self.assertRefused({"experiences-1": {"action": "add"}}, "la revue a signalé un doublon (probable_duplicate)")
        self.assertRefused({"skills-1": {"action": "add"}}, "« python » est déjà dans la catégorie « programming »")
        self.assertRefused({"languages-1": {"action": "add"}}, "Utilise plutôt « update »")
        self.assertRefused({"interests-1": {"action": "add"}}, "« Tennis » est déjà dans les centres d'intérêt")

    def test_duplicate_added_on_purpose_gets_a_new_id(self):
        self.apply({"projects-1": {"action": "add", "allow_duplicate": True}})
        self.assertEqual([p["id"] for p in self.data()["projects"]], ["cassiopee", "projet-cassiopee"])

    def test_second_import_does_not_create_duplicates(self):
        decisions = {"experiences-2": {"action": "add"}, "projects-2": {"action": "add"}, "skills-2": {"action": "add"}}
        self.apply(decisions)
        once = self.profile.read_text(encoding="utf-8")

        # Même import, mêmes décisions : les éléments ajoutés sont maintenant des doublons, donc refusés
        error = self.assertRefused(decisions, "doublon")
        self.assertEqual(len(error.problems), 3)
        self.assertEqual(self.profile.read_text(encoding="utf-8"), once)
        review = review_import(self.json, self.profile)
        self.assertEqual(review["experiences"][1]["status"], "probable_duplicate")

    # ---------- erreurs : rien n'est enregistré ----------

    def test_unknown_target_id(self):
        self.assertRefused({"experiences-1": {"action": "update", "target_id": "inconnu", "fields": ["title"]}},
                           "aucun(e) expérience avec l'id « inconnu » (ids : cnrs-aubay)")

    def test_invalid_decisions(self):
        cases = [
            ({"experiences-9": {"action": "add"}}, "proposition(s) inconnue(s) : experiences-9"),
            ({"experiences-2": {"action": "merge"}}, "« action » doit valoir skip, add, update"),
            ({"experiences-1": {"action": "update", "target_id": "cnrs-aubay"}}, "« fields » est obligatoire"),
            ({"experiences-1": {"action": "update", "fields": ["title"]}}, "indique la cible"),
            ({"experiences-2": {"action": "add", "fields": ["salary"]}}, "champ(s) absent(s) de l'extraction : salary"),
            ({"experiences-1": {"action": "update", "target_id": "cnrs-aubay", "fields": ["title"], "clear": ["company"]}},
             "impossible(s) à vider : company"),
            ({"education-1": {"action": "update", "target_position": 7, "fields": ["details"]}}, "entre 1 et 2"),
            ({"skills-3": {"action": "add"}}, "la catégorie « cloud » n'existe pas"),
            ({"languages-2": {"action": "add"}}, "le niveau de « Espagnol » n'a pas été extrait"),
            ({"skills-2": {"action": "update"}}, "l'action « update » n'est pas possible ici"),
            ({"personal": {"action": "update", "fields": ["birth_date"]}}, "champ(s) absent(s) de l'extraction : birth_date"),
        ]
        for decisions, expected in cases:
            with self.subTest(decisions=decisions):
                self.assertRefused(decisions, expected)

    def test_one_invalid_decision_blocks_all_the_others(self):
        error = self.assertRefused({
            "experiences-2": {"action": "add"},                  # valide
            "projects-2": {"action": "add"},                     # valide
            "skills-2": {"action": "add"},                       # valide
            "experiences-1": {"action": "update", "target_id": "inconnu", "fields": ["title"]},   # invalide
        }, "aucun(e) expérience avec l'id « inconnu »")
        self.assertEqual(len(error.problems), 1)

    def test_all_problems_are_listed_at_once(self):
        error = self.assertRefused({"experiences-1": {"action": "add"}, "skills-3": {"action": "add"},
                                    "languages-2": {"action": "add"}}, "doublon")
        self.assertEqual(len(error.problems), 3)

    def test_failure_while_applying_saves_nothing(self):
        # Les deux premières opérations réussissent sur la copie, la troisième échoue : rien n'est gardé
        before = self.profile.read_text(encoding="utf-8")
        real_add_skill = manager.add_skill

        def failing_add_skill(*args, **kwargs):
            raise manager.ItemError("compétence", ["panne simulée"])

        with mock.patch.object(manager, "add_skill", failing_add_skill):
            with self.assertRaises(DecisionError) as context:
                self.apply({"experiences-2": {"action": "add"}, "projects-2": {"action": "add"}, "skills-2": {"action": "add"}})
        self.assertIn("le profil n'a pas été modifié", str(context.exception))
        self.assertEqual(self.profile.read_text(encoding="utf-8"), before)
        self.assertFalse(any(p.name.endswith(".import-tmp") for p in self.folder.iterdir()))
        self.assertIs(manager.add_skill, real_add_skill)


    # ---------- décisions mal formées : refusées proprement ----------

    def test_malformed_decisions_are_refused_cleanly(self):
        update = {"action": "update", "target_id": "cnrs-aubay", "fields": ["title"]}
        cases = [
            ({"experiences-1": {**update, "clear": "context"}}, "« clear » doit être une liste de noms de champs"),
            ({"experiences-1": {**update, "clear": 3}}, "« clear » doit être une liste de noms de champs"),
            ({"experiences-1": {**update, "clear": [3]}}, "« clear » doit être une liste de noms de champs"),
            ({"experiences-1": {"action": "update", "target_id": "cnrs-aubay", "fields": "title"}}, "« fields » doit être une liste"),
            ({"personal": {"action": "update", "fields": [3]}}, "« fields » doit être une liste"),
            ({"education-1": {"action": "update", "target_position": True, "fields": ["details"]}}, "« target_position » doit être un numéro"),
            ({"education-1": {"action": "update", "target_position": "2", "fields": ["details"]}}, "« target_position » doit être un numéro"),
            ({"experiences-1": {**update, "target_id": 42}}, "« target_id » doit être un texte non vide"),
            ({"languages-2": {"action": "add", "level": 3}}, "« level » doit être un texte non vide"),
            ({"skills-2": {"action": "add", "category": ["programming"]}}, "« category » doit être un texte non vide"),
            ({"interests-2": {"action": "update", "target": 1}}, "« target » doit être un texte non vide"),
            ({"projects-1": {"action": "add", "allow_duplicate": "oui"}}, "« allow_duplicate » doit valoir true ou false"),
            ({"skills-3": {"action": "add", "create_category": 1}}, "« create_category » doit valoir true ou false"),
            ({"experiences-1": {**update, "allow_less_precise": "yes"}}, "« allow_less_precise » doit valoir true ou false"),
            ({"projects-1": {"action": "add", "allow_duplicates": True}}, "option(s) inconnue(s) : allow_duplicates"),
            ({"experiences-2": {"action": "skip", "fields": ["title"]}}, "option(s) inconnue(s) : fields"),
            ({"experiences-2": "add"}, "« action » doit valoir"),
        ]
        for decisions, expected in cases:
            with self.subTest(decisions=decisions):
                self.assertRefused(decisions, expected)

    # ---------- allow_duplicate : mêmes règles que manager.py ----------

    def write_extraction(self, **changes):
        extraction = json.loads(json.dumps(EXTRACTION))
        extraction["profile"].update(changes)
        self.json.write_text(json.dumps(extraction, ensure_ascii=False), encoding="utf-8")

    def test_skill_already_in_the_same_category_is_always_refused(self):
        # manager.add_skill refuse toujours ce cas : allow_duplicate ne doit pas faire croire le contraire
        error = self.assertRefused({"skills-1": {"action": "add", "allow_duplicate": True}},
                                   "« python » est déjà dans la catégorie « programming » ; une compétence ne peut pas y figurer deux fois")
        self.assertNotIn("application a échoué", str(error))     # refusé dès la vérification, pas pendant l'application

    def test_skill_in_another_category_needs_allow_duplicate(self):
        self.write_extraction(skills={"tools": ["Python"]})
        self.assertRefused({"skills-1": {"action": "add", "create_category": True}},
                           "« Python » est déjà dans la catégorie « programming ». Pour l'ajouter aussi dans « tools »")
        self.apply({"skills-1": {"action": "add", "create_category": True, "allow_duplicate": True}})
        self.assertEqual(self.data()["skills"], {"programming": ["Python"], "tools": ["Python"]})

    def test_language_with_the_same_name_is_always_refused(self):
        self.write_extraction(languages=[{"language": "French", "level": "B2"}])
        error = self.assertRefused({"languages-1": {"action": "add", "allow_duplicate": True}},
                                   "« French » est déjà dans le profil. Utilise plutôt « update »")
        self.assertNotIn("application a échoué", str(error))

    def test_equivalent_language_needs_allow_duplicate(self):
        # « Français » ≈ « French » : manager l'accepte (noms différents), seulement si l'utilisateur le confirme
        self.assertRefused({"languages-1": {"action": "add"}}, "correspond à « French » déjà dans le profil")
        self.apply({"languages-1": {"action": "add", "allow_duplicate": True}})
        self.assertEqual([entry["language"] for entry in self.data()["languages"]], ["French", "Français"])

    def test_same_interest_is_always_refused(self):
        self.assertRefused({"interests-1": {"action": "add", "allow_duplicate": True}}, "« Tennis » est déjà dans les centres d'intérêt")

    def test_the_same_value_twice_in_one_batch(self):
        self.write_extraction(skills={"programming": ["Rust"], "systems": ["rust"]},
                              interests=["Chess", "chess"], languages=[{"language": "German", "level": "B1"},
                                                                         {"language": "german", "level": "B2"}])
        error = self.assertRefused({
            "skills-1": {"action": "add"}, "skills-2": {"action": "add", "category": "programming"},
            "interests-1": {"action": "add"}, "interests-2": {"action": "add", "allow_duplicate": True},
            "languages-1": {"action": "add"}, "languages-2": {"action": "add"},
        }, "déjà ajouté")
        self.assertEqual(len(error.problems), 3)

    # ---------- conservation et compte rendu ----------

    # ---------- corrections manuelles (overrides) ----------

    def test_corrected_values_are_saved(self):
        report = self.apply({"experiences-2": {
            "action": "add",
            "fields": ["company", "title", "start_date", "end_date", "responsibilities", "skills"],
            "overrides": {"company": "  Dassault Systèmes SE ", "start_date": "2026-11", "end_date": "2027-04",
                          "responsibilities": ["Agent IA pour la conception", " ", "Évaluation des modèles"],
                          "skills": ["Python", "LLM"]},
        }})
        self.assertEqual(report["added"][0]["id"], "dassault-systemes-se")
        self.assertEqual(report["added"][0]["corrected"],
                         ["company", "end_date", "responsibilities", "skills", "start_date"])
        self.assertEqual(self.item("experiences", "dassault-systemes-se"), {
            "id": "dassault-systemes-se", "company": "Dassault Systèmes SE", "title": "Stagiaire IA",
            "start_date": "2026-11", "end_date": "2027-04",
            "responsibilities": ["Agent IA pour la conception", "Évaluation des modèles"], "skills": ["Python", "LLM"],
        })

    def test_corrected_update_keeps_list_merging(self):
        self.apply({"experiences-1": {
            "action": "update", "target_id": "cnrs-aubay", "fields": ["responsibilities", "end_date", "achievements"],
            "overrides": {"responsibilities": ["État de l'art", "Prototypes avec SAM et MM-Grounding-DINO"],
                          "end_date": "2026-08", "achievements": ["Prototype présenté à la fondation"]},
        }})
        experience = self.item("experiences", "cnrs-aubay")
        self.assertEqual(experience["responsibilities"], ["État de l'art", "Prototypes avec SAM et MM-Grounding-DINO"])
        self.assertEqual(experience["end_date"], "2026-08")
        self.assertEqual(experience["achievements"], ["Prototype présenté à la fondation"])
        self.assertEqual(experience["start_date"], "2026-02")      # non repris : inchangé

    def test_corrected_personal_skill_language_interest(self):
        report = self.apply({
            "personal": {"action": "update", "fields": ["phone", "linkedin"],
                         "overrides": {"linkedin": "https://www.linkedin.com/in/jane-doe"}},
            "skills-2": {"action": "add", "overrides": {"skill": "Rust (notions)"}},
            "languages-2": {"action": "add", "level": "B1", "overrides": {"language": "Spanish"}},
            "interests-2": {"action": "add", "overrides": {"interest": "Échecs"}},
            "experiences-2": {"action": "add", "fields": ["company", "title"], "overrides": {"title": "AI Intern"}},
        })
        data = self.data()
        self.assertEqual(data["personal"]["linkedin"], "https://www.linkedin.com/in/jane-doe")
        self.assertEqual(data["personal"]["phone"], "+33 6 11 22 33 44")
        self.assertEqual(data["skills"]["programming"], ["Python", "Rust (notions)"])
        self.assertEqual(data["languages"][-1], {"language": "Spanish", "level": "B1"})
        self.assertEqual(data["interests"], ["Tennis", "Échecs"])
        self.assertEqual(self.item("experiences", "dassault-systemes")["title"], "AI Intern")
        corrected = {record["proposal_id"]: record.get("corrected") for record in report["added"] + report["updated"]}
        self.assertEqual(corrected["personal"], ["linkedin"])
        self.assertEqual(corrected["skills-2"], ["skill"])

    def test_invalid_corrections_are_refused(self):
        cases = [
            ({"experiences-2": {"action": "add", "fields": ["company", "title", "start_date"],
                                "overrides": {"start_date": "mars 2024"}}}, "AAAA"),
            ({"experiences-2": {"action": "add", "fields": ["company", "title", "start_date", "end_date"],
                                "overrides": {"end_date": "2026-05"}}}, "« end_date » est avant « start_date »"),
            ({"experiences-1": {"action": "update", "target_id": "cnrs-aubay", "fields": ["end_date"],
                                "overrides": {"end_date": "2025"}}}, "« end_date » est avant « start_date »"),
            ({"experiences-2": {"action": "add", "fields": ["company", "title"], "overrides": {"company": "  "}}},
             "vide"),
            ({"experiences-2": {"action": "add", "fields": ["company", "title"], "overrides": {"location": "Paris"}}},
             "non repris"),
            ({"projects-2": {"action": "add", "fields": ["name", "github_url"],
                             "overrides": {"github_url": "github.com/jane"}}}, "http"),
            ({"projects-2": {"action": "add", "overrides": {"tags": "ia"}}}, "liste de textes"),
            ({"personal": {"action": "update", "fields": ["phone"], "overrides": {"email": "jane@x.fr"}}}, "non repris"),
            ({"personal": {"action": "update", "fields": ["email"], "overrides": {"email": "jane at x"}}}, "e-mail"),
            ({"skills-2": {"action": "add", "overrides": {"category": "tools"}}}, "ne peut pas être corrigé"),
            ({"interests-2": {"action": "add", "overrides": "Échecs"}}, "overrides"),
            ({"languages-1": {"action": "update", "overrides": {"language": "Français"}}}, "option(s) inconnue(s)"),
        ]
        for decisions, expected in cases:
            with self.subTest(decisions=decisions):
                self.assertRefused(decisions, expected)

    def test_one_invalid_correction_saves_nothing(self):
        problems = self.assertRefused({
            "experiences-2": {"action": "add", "fields": ["company", "title"], "overrides": {"company": "Dassault"}},
            "personal": {"action": "update", "fields": ["phone"], "overrides": {"phone": "+33 7 00 00 00 00"}},
            "interests-2": {"action": "add", "overrides": {"interest": "Échecs"}},
            "projects-2": {"action": "add", "fields": ["name", "start_date"], "overrides": {"start_date": "bientôt"}},
        }, "projects-2").problems
        self.assertEqual(len(problems), 1)

    def test_correction_matching_an_existing_element_needs_confirmation(self):
        # « Drone Detector » est nouveau, mais corrigé en « Cassiopée » il existe déjà dans le profil
        decision = {"action": "add", "fields": ["name"], "overrides": {"name": "cassiopée"}}
        self.assertRefused({"projects-2": decision}, "après correction")
        self.apply({"projects-2": {**decision, "allow_duplicate": True}})
        self.assertEqual([p["name"] for p in self.data()["projects"]], ["Cassiopée", "cassiopée"])

    def test_corrected_names_keep_the_exact_duplicate_protections(self):
        self.assertRefused({"skills-2": {"action": "add", "allow_duplicate": True, "overrides": {"skill": "PYTHON"}}},
                           "ne peut pas y figurer deux fois")
        self.assertRefused({"languages-2": {"action": "add", "level": "B1", "overrides": {"language": "french"}}},
                           "déjà dans le profil")
        self.assertRefused({"interests-2": {"action": "add", "overrides": {"interest": "tennis"}}},
                           "déjà dans les centres d'intérêt")

    # ---------- actions désactivées dans l'interface : toujours refusées, même confirmées ----------
    # (frontend/src/features/import/decisions.ts, unavailableActions)

    def test_interface_blocked_actions_are_refused_even_with_allow_duplicate(self):
        cases = {
            "compétence déjà dans la catégorie (valeur corrigée)": (
                {"skills-2": {"action": "add", "allow_duplicate": True, "overrides": {"skill": " PYTHON"}}},
                "ne peut pas y figurer deux fois"),
            "langue du même nom (valeur corrigée)": (
                {"languages-2": {"action": "add", "level": "B1", "allow_duplicate": True,
                                 "overrides": {"language": "french"}}},
                "déjà dans le profil"),
            "centre d'intérêt identique (valeur corrigée)": (
                {"interests-2": {"action": "add", "allow_duplicate": True, "overrides": {"interest": "TENNIS"}}},
                "déjà dans les centres d'intérêt"),
            "même compétence deux fois dans l'import": (
                {"skills-2": {"action": "add"},
                 "skills-3": {"action": "add", "category": "programming", "allow_duplicate": True,
                              "overrides": {"skill": "rust"}}},
                "par une autre décision"),
            "même langue deux fois dans l'import": (
                {"languages-1": {"action": "add", "allow_duplicate": True, "overrides": {"language": "espagnol"}},
                 "languages-2": {"action": "add", "level": "A2", "allow_duplicate": True}},
                "par une autre décision"),
            "même centre d'intérêt deux fois dans l'import": (
                {"interests-1": {"action": "add", "allow_duplicate": True, "overrides": {"interest": "chess"}},
                 "interests-2": {"action": "add", "allow_duplicate": True}},
                "par une autre décision"),
        }
        for name, (decisions, expected) in cases.items():
            with self.subTest(name):
                self.assertRefused(decisions, expected)

    def test_rename_onto_another_existing_interest_is_refused(self):
        self.profile.write_text(PROFILE.replace("interests:\n  - Tennis\n", "interests:\n  - Tennis\n  - Chess\n"),
                                encoding="utf-8")
        self.assertRefused({"interests-1": {"action": "update", "target": "Tennis", "overrides": {"interest": "chess"}}},
                           "déjà dans les centres d'intérêt")
        # Changer seulement la casse de la cible reste permis
        self.apply({"interests-1": {"action": "update", "target": "Tennis", "overrides": {"interest": "TENNIS"}}})
        self.assertEqual(self.data()["interests"], ["TENNIS", "Chess"])

    def test_interface_allowed_actions_are_accepted_once_confirmed(self):
        report = self.apply({
            "skills-1": {"action": "add", "category": "cloud", "create_category": True,
                         "allow_duplicate": True},                     # python : aussi dans une autre catégorie
            "languages-1": {"action": "add", "allow_duplicate": True},  # Français ≈ French
            "interests-2": {"action": "add", "overrides": {"interest": "Échecs"}},
            "projects-2": {"action": "add", "fields": ["name"], "allow_duplicate": True,
                           "overrides": {"name": "Cassiopée"}},         # nom corrigé = projet existant, confirmé
        })
        self.assertEqual(len(report["added"]), 4)
        data = self.data()
        self.assertEqual(data["skills"]["cloud"], ["python"])
        self.assertEqual(data["languages"][-1]["language"], "Français")

    # ---------- C, C++ et C# : trois compétences distinctes ----------

    def use(self, skills, profile_skills="  programming:\n    - Python\n    - C\n"):
        """Profil et extraction réduits aux compétences."""
        self.profile.write_text(PROFILE.replace("  programming:\n    - Python\n", profile_skills), encoding="utf-8")
        extraction = {**EXTRACTION, "profile": {"skills": {"programming": skills}}}
        self.json.write_text(json.dumps(extraction, ensure_ascii=False), encoding="utf-8")

    def test_c_cpp_and_csharp_are_distinct_skills(self):
        self.use(["C++", "C#", "c++ ", "PYTHON", "C"])
        review = review_import(self.json, self.profile)
        self.assertEqual([(s["skill"], s["status"]) for s in review["skills"]], [
            ("C++", "new"), ("C#", "new"), ("c++ ", "new"), ("PYTHON", "duplicate"), ("C", "duplicate")])

        self.apply({"skills-1": {"action": "add"}, "skills-2": {"action": "add"}})
        self.assertEqual(self.data()["skills"]["programming"], ["Python", "C", "C++", "C#"])

    def test_a_second_cpp_is_refused(self):
        self.use(["C++", "c++ "])
        self.assertRefused({"skills-1": {"action": "add"}, "skills-2": {"action": "add", "allow_duplicate": True}},
                           "par une autre décision")                      # deux fois dans le même import
        self.apply({"skills-1": {"action": "add"}})
        self.use(["c++"], profile_skills="  programming:\n    - Python\n    - C\n    - C++\n")
        self.assertEqual(review_import(self.json, self.profile)["skills"][0]["status"], "duplicate")
        self.assertRefused({"skills-1": {"action": "add", "allow_duplicate": True}}, "ne peut pas y figurer deux fois")

    def test_case_and_spaces_are_still_ignored_for_skills(self):
        self.use(["PYTHON", "  python  "])
        self.assertRefused({"skills-1": {"action": "add", "allow_duplicate": True}}, "ne peut pas y figurer deux fois")
        self.assertRefused({"skills-2": {"action": "add", "overrides": {"skill": " Python"}}},
                           "ne peut pas y figurer deux fois")

    def test_skill_lists_of_an_experience_keep_c_cpp_and_csharp(self):
        extraction = {**EXTRACTION, "profile": {"experiences": [
            {"company": "CNRS Foundation - via Aubay", "title": "Research Intern", "start_date": "2026-02",
             "skills": ["c", "C++", "C#"]}]}}
        self.json.write_text(json.dumps(extraction, ensure_ascii=False), encoding="utf-8")
        self.profile.write_text(PROFILE.replace("    context: Projet Science4Reefs.\n",
                                                "    context: Projet Science4Reefs.\n    skills:\n      - C\n"),
                                encoding="utf-8")
        match = review_import(self.json, self.profile)["experiences"][0]["matches"][0]
        self.assertEqual(match["differences"]["skills"]["new_values"], ["C++", "C#"])
        self.apply({"experiences-1": {"action": "update", "target_id": "cnrs-aubay", "fields": ["skills"]}})
        self.assertEqual(self.item("experiences", "cnrs-aubay")["skills"], ["C", "C++", "C#"])

    def test_normalization_shared_with_the_frontend(self):
        # Même table que frontend/src/test/importDecisions.test.ts (PYTHON_NORM)
        from candidate.review_import import _norm
        expected = {
            "Python": "python", "  PyTorch  ": "pytorch", "Télécom SudParis": "telecom sudparis", "ÉCHECS": "echecs",
            "C++": "c", "C#": "c", "Node.js": "node js", "scikit-learn": "scikit learn", "Scikit Learn": "scikit learn",
            "CI/CD": "ci cd", "Course à pied": "course a pied", "Français": "francais",
            "Machine   Learning": "machine learning", "machine_learning": "machine learning", "Œuvre": "uvre",
            "naïve": "naive", "Straße": "strae", "L'Oréal": "l oreal", "": "", "1er Prix": "1er prix",
        }
        self.assertEqual({text: _norm(text) for text in expected}, expected)

        # Noms de compétences : même table que PYTHON_SKILL_NORM dans le test du frontend
        from candidate.review_import import _skill_norm
        skills = {
            "C": "c", "C++": "c++", "C#": "c#", "c++ ": "c++", "  PYTHON ": "python", "Python": "python",
            "F#": "f#", "Node.js": "node js", "scikit-learn": "scikit learn", "Scikit Learn": "scikit learn",
            ".NET": "net", "CI/CD": "ci cd", "Télécom": "telecom", "Machine   Learning": "machine learning", "": "",
        }
        self.assertEqual({text: _skill_norm(text) for text in skills}, skills)

    def test_comments_and_other_sections_are_kept(self):
        self.apply({"experiences-2": {"action": "add"},
                    "experiences-1": {"action": "update", "target_id": "cnrs-aubay", "fields": ["skills"]}})
        text = self.profile.read_text(encoding="utf-8")
        self.assertIn("# Mon profil", text)
        self.assertIn("# Mes projets", text)
        data = self.data()
        self.assertEqual(data["projects"], [{"id": "cassiopee", "name": "Cassiopée"}])
        self.assertEqual(data["education"][0], {"school": "Lycee Saint-Louis", "degree": "CPGE"})

    def test_report_is_json_for_the_frontend(self):
        report = self.apply({"experiences-2": {"action": "add"}})
        self.assertEqual(set(report), {"added", "updated", "skipped", "profile"})
        json.dumps(report)

    def test_real_private_profile_is_untouched(self):
        before = sha(CANDIDATE_PATH)
        self.apply({"experiences-2": {"action": "add"}})
        self.assertEqual(sha(CANDIDATE_PATH), before)


if __name__ == "__main__":
    unittest.main()
