"""
Tests des routes « Mes CV » (api/cvs.py) et du contrôle des URL (jobs/url_check.py).
Pipeline simulé (aucun navigateur, aucun appel à Claude), profil fictif et dossiers temporaires.
Le test de compilation réelle est ignoré si latexmk n'est pas installé.

Lancement :  python -m unittest discover tests
"""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from functools import partial
from pathlib import Path

from unittest import mock

from fastapi.testclient import TestClient

from api import cvs, main
from cv import build_cv
from candidate.profile import CANDIDATE_PATH, EXAMPLE_PATH, load_profile
from cv.analysis import failed_analysis, load_analysis, save_analysis
from cv.build_cv import ROOT, rebuild_cv, write_cv
from cv.document import build_document, entry_from_profile
from cv.pipeline import GenerationResult
from cv_fixtures import fake_draft
from jobs.url_check import UnsafeUrlError, check_public_url
from test_import_cv import sha


PUBLIC = {"jobs.example.com": "93.184.216.34", "careers.example.org": "2606:2800:220:1::1",
          "evil.example.com": "10.0.0.5", "mapped.example.com": "::ffff:127.0.0.1"}


def fake_resolve(host, port, proto=0):
    if host not in PUBLIC:
        import socket
        raise socket.gaierror("introuvable")
    return [(0, 0, 0, "", (PUBLIC[host], port or 443))]


check = partial(check_public_url, resolve=fake_resolve)
REAL_PROFILE_HASH = None


def setUpModule():
    global REAL_PROFILE_HASH
    REAL_PROFILE_HASH = sha(CANDIDATE_PATH)


def tearDownModule():
    assert sha(CANDIDATE_PATH) == REAL_PROFILE_HASH, "le vrai profil a été modifié"


class UrlCheckTest(unittest.TestCase):

    def test_public_pages_are_accepted(self):
        for url in ("https://jobs.example.com/offre/123?ref=x", "http://careers.example.org/job#apply",
                    "  https://jobs.example.com/a  "):
            self.assertEqual(check(url), url.strip())

    def test_local_and_internal_addresses_are_refused(self):
        refused = {
            "file:///etc/passwd": "http", "javascript:alert(1)": "http", "ftp://jobs.example.com/x": "http",
            "data:text/html,x": "http", "": "vide", "https://": "nom de site",
            "http://localhost:8000/api/profile": "locale", "http://127.0.0.1/": "locale", "http://[::ffff:10.0.0.1]/": "locale",
            "http://[::1]/": "locale", "http://10.0.0.1/": "locale", "http://192.168.1.10/": "locale",
            "http://172.16.0.1/": "locale", "http://169.254.169.254/latest/meta-data": "locale",
            "http://0.0.0.0/": "locale", "http://intranet/offres": "locale", "http://printer.local/": "locale",
            "http://api.internal/": "locale", "https://user:secret@jobs.example.com/": "identifiants",
            "https://evil.example.com/": "interne", "https://mapped.example.com/": "interne",
            "https://unknown.example.net/": "introuvable", "https://jobs.example.com:99999/": "port",
        }
        for url, expected in refused.items():
            with self.subTest(url):
                with self.assertRaises(UnsafeUrlError) as context:
                    check(url)
                self.assertIn(expected, str(context.exception))


def wait_for(client, task_id, statuses=("completed", "failed"), timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/cvs/tasks/{task_id}").json()
        if task["status"] in statuses:
            return task
        time.sleep(0.02)
    raise AssertionError(f"la tâche est restée {task['status']}")


class ApiCvTestCase(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.profile_path = self.folder / "candidate.yaml"
        shutil.copy(EXAMPLE_PATH, self.profile_path)
        self.applications = self.folder / "applications"
        self.applications.mkdir()
        self.profile = load_profile(self.profile_path)
        self.generator_calls = []
        self.rebuilds = []
        self.analyses = []

        overrides = main.app.dependency_overrides
        overrides[main.profile_path] = lambda: self.profile_path
        overrides[cvs.applications_dir] = lambda: self.applications
        overrides[cvs.url_checker] = lambda: check
        overrides[cvs.cv_generator] = lambda: self.fake_generator
        overrides[cvs.cv_rebuilder] = lambda: self.fake_rebuilder
        overrides[cvs.cv_analyzer] = lambda: self.fake_analyzer
        self.addCleanup(overrides.clear)
        self.client = TestClient(main.app)

    # Faux pipeline : mêmes étapes et même dossier que le vrai, sans navigateur ni Claude ni LaTeX
    def fake_generator(self, url, profile, on_step=None, applications_dir=None):
        self.generator_calls.append(url)
        for step in ("read_offer", "analyze_offer", "write_cv", "verify_cv", "verified"):
            on_step(step, issues=[])
        doc = build_document(fake_draft(), profile)
        main_tex = write_cv(doc, {"job_title": "Stage", "company": "Acme Robotics", "source_url": url},
                            applications_dir=applications_dir)
        on_step("compile", folder=main_tex.parent)
        pdf, pages = self.fake_compile(main_tex.parent)
        on_step("analyze_fit", folder=main_tex.parent)
        analysis = self.fake_analyzer(main_tex.parent, profile)
        return GenerationResult(folder=main_tex.parent, main_tex=main_tex, pdf=pdf, pages=pages,
                                document=doc, issues=[], offer={}, analysis=analysis)

    def fake_analyzer(self, folder, profile):
        """Analyse fictive enregistrée comme la vraie (cv/analysis.analyze_folder), sans Claude."""
        self.analyses.append(Path(folder).name)
        analysis = {"schema_version": 1, "status": "completed", "generated_at": "2026-10-22T10:00:00",
                    "profile_fingerprint": "0" * 16, "offer": {"company": "Acme Robotics"},
                    "overview": {}, "requirements": [], "strengths": [], "weaknesses": [], "recommendations": [],
                    "score": {"value": 72, "level": "Bonne adéquation"}, "warnings": []}
        save_analysis(folder, analysis)
        return analysis

    def fake_compile(self, folder, pages=1):
        main_tex = next(folder.glob("*.tex"))
        build = folder / "build"
        build.mkdir(exist_ok=True)
        pdf = build / f"{main_tex.stem}.pdf"
        pdf.write_bytes(b"%PDF-1.4 faux " + str(time.time()).encode())
        (build / "layout.json").write_text(json.dumps({"version": 1, "pages": pages, "regions": []}), encoding="utf-8")
        return pdf, pages

    def fake_rebuilder(self, folder):
        self.rebuilds.append(folder)
        pages = 2 if len(json.loads((folder / "cv.json").read_text(encoding="utf-8"))["experiences"][0]["bullets"]) > 10 else 1
        return self.fake_compile(folder, pages)

    def new_cv(self) -> str:
        """Un CV complet (cv.json, sections, PDF, layout) créé par le faux pipeline."""
        return self.fake_generator("https://jobs.example.com/1", self.profile, on_step=lambda *a, **k: None,
                                   applications_dir=self.applications).folder.name

    def legacy_cv(self) -> str:
        """Un CV créé avant cv.json : sections LaTeX et PDF seulement."""
        folder = self.applications / "ancienne-offre"
        (folder / "sections").mkdir(parents=True)
        (folder / "build").mkdir()
        (folder / "Jane_Doe_Candidature_Ancienne.tex").write_text("% ancien\n", encoding="utf-8")
        (folder / "build" / "Jane_Doe_Candidature_Ancienne.pdf").write_bytes(b"%PDF-1.4 ancien")
        (folder / "offer.json").write_text(json.dumps({"company": "Ancienne", "job_title": "Stage"}), encoding="utf-8")
        return folder.name

    def assertProblem(self, response, status, fragment):
        self.assertEqual(response.status_code, status, response.text)
        detail = response.json()["detail"]
        self.assertTrue(detail["message"])
        text = " ".join([detail["message"], *detail["problems"]])
        self.assertIn(fragment, text)
        return detail


class GenerationTest(ApiCvTestCase):

    def test_generation_runs_in_the_background(self):
        response = self.client.post("/api/cvs/generate", json={"url": "https://jobs.example.com/offre/42"})
        self.assertEqual(response.status_code, 202)
        task_id = response.json()["task_id"]
        task = wait_for(self.client, task_id)
        self.assertEqual(task["status"], "completed", task)
        self.assertEqual((task["step"], task["error"]), ("done", None))
        self.assertEqual(task["result"], {"pages": 1, "fits_one_page": True, "verification_issues": 0, "gaps": 1,
                                          "analysis_status": "completed", "fit_score": 72})
        self.assertEqual(self.generator_calls, ["https://jobs.example.com/offre/42"])
        cv = self.client.get(f"/api/cvs/{task['cv_id']}").json()
        self.assertEqual(cv["document"]["header"]["name"], "John Doe")
        self.assertEqual(cv["cv"]["source_url"], "https://jobs.example.com/offre/42")

    def test_status_while_running_and_queue(self):
        started, release = threading.Event(), threading.Event()

        def slow_generator(url, profile, on_step=None, applications_dir=None):
            on_step("read_offer")
            on_step("write_cv")
            started.set()
            release.wait(5)
            return self.fake_generator(url, profile, on_step, applications_dir)

        main.app.dependency_overrides[cvs.cv_generator] = lambda: slow_generator
        first = self.client.post("/api/cvs/generate", json={"url": "https://jobs.example.com/1"}).json()["task_id"]
        self.assertTrue(started.wait(5))
        second = self.client.post("/api/cvs/generate", json={"url": "https://jobs.example.com/2"}).json()["task_id"]

        running = self.client.get(f"/api/cvs/tasks/{first}").json()
        self.assertEqual((running["status"], running["step"], running["step_label"]),
                         ("running", "write_cv", "Rédaction du CV"))
        self.assertEqual(self.client.get(f"/api/cvs/tasks/{second}").json()["status"], "pending")   # une à la fois
        self.assertEqual(self.client.get("/api/profile").status_code, 200)                         # rien n'est bloqué
        release.set()
        self.assertEqual(wait_for(self.client, first)["status"], "completed")
        self.assertEqual(wait_for(self.client, second)["status"], "completed")

    def test_failures_are_readable_and_without_server_paths(self):
        def failing(error):
            def generator(url, profile, on_step=None, applications_dir=None):
                on_step("read_offer")
                raise error
            return generator

        cases = [
            (RuntimeError(f"Claude a échoué : fichier {ROOT}/profile/private/candidate.yaml dans {Path.home()}"),
             "La génération a échoué"),
            (ValueError("détail interne avec des données personnelles"), "Erreur inattendue pendant la génération"),
        ]
        for error, message in cases:
            with self.subTest(type(error).__name__):
                main.app.dependency_overrides[cvs.cv_generator] = lambda error=error: failing(error)
                task_id = self.client.post("/api/cvs/generate", json={"url": "https://jobs.example.com/x"}).json()["task_id"]
                task = wait_for(self.client, task_id)
                self.assertEqual(task["status"], "failed")
                self.assertEqual(task["error"]["message"], message)
                text = json.dumps(task, ensure_ascii=False)
                self.assertNotIn(str(ROOT), text)
                self.assertNotIn(str(Path.home()), text)
                self.assertNotIn("données personnelles", text)
                self.assertNotIn("Traceback", text)

    def test_error_messages_keep_relative_paths_only(self):
        self.assertEqual(cvs._clean("La compilation a échoué (/private/var/folders/T/tmp/applications/acme/x.tex) :\n"
                                    "./sections/experience.tex:12: Undefined"),
                         "La compilation a échoué (x.tex) :\n./sections/experience.tex:12: Undefined")
        self.assertEqual(cvs._clean(f"Fichier {ROOT}/profile/private/candidate.yaml"), "Fichier profile/private/candidate.yaml")
        self.assertEqual(cvs._clean(f"Dans {Path.home()}/Documents/cv.pdf"), "Dans cv.pdf")

    def test_refused_urls_and_invalid_profile_start_nothing(self):
        for url in ("file:///etc/passwd", "http://localhost:8000/api/profile", "http://169.254.169.254/", "", None):
            with self.subTest(url):
                self.assertProblem(self.client.post("/api/cvs/generate", json={"url": url}), 422, "URL refusée")
        self.assertProblem(self.client.post("/api/cvs/generate", json={}), 422, "URL refusée")
        self.profile_path.write_text("personal:\n  first_name: Jane\n", encoding="utf-8")
        self.assertProblem(self.client.post("/api/cvs/generate", json={"url": "https://jobs.example.com/1"}),
                           422, "last_name")
        time.sleep(0.1)
        self.assertEqual(self.generator_calls, [])

    def test_unknown_tasks(self):
        self.assertProblem(self.client.get(f"/api/cvs/tasks/{'0' * 32}"), 404, "Tâche introuvable")
        self.assertEqual(self.client.get("/api/cvs/tasks/../../etc").status_code, 404)


class ReadTest(ApiCvTestCase):

    def test_list_with_metadata(self):
        legacy = self.legacy_cv()
        cv_id = self.new_cv()
        os.utime(self.applications / legacy / "build" / "Jane_Doe_Candidature_Ancienne.pdf", (1, 1))
        cvs_list = self.client.get("/api/cvs").json()
        self.assertEqual([cv["id"] for cv in cvs_list], [cv_id, legacy])               # le plus récent d'abord
        new, old = cvs_list
        self.assertEqual((new["company"], new["role"], new["language"], new["editable"]),
                         ("Acme Robotics", "Stage Vision par Ordinateur", "fr", True))
        self.assertEqual((new["has_pdf"], new["has_layout"], new["pages"], new["fits_one_page"]), (True, True, 1, True))
        self.assertEqual((old["company"], old["editable"], old["has_pdf"], old["has_layout"]),
                         ("Ancienne", False, True, False))
        self.assertNotIn(str(self.applications), json.dumps(cvs_list))                 # aucun chemin du serveur

    def test_read_document_pdf_and_layout(self):
        cv_id = self.new_cv()
        cv = self.client.get(f"/api/cvs/{cv_id}").json()
        self.assertEqual(set(cv), {"cv", "document", "verification_issues"})
        self.assertEqual(cv["document"]["experiences"][0]["source_id"], "example-research-company")
        pdf = self.client.get(f"/api/cvs/{cv_id}/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertTrue(pdf.headers["content-disposition"].startswith("inline"))
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(f"/api/cvs/{cv_id}/layout").json()["pages"], 1)

    def test_legacy_and_missing_files(self):
        legacy = self.legacy_cv()
        self.assertProblem(self.client.get(f"/api/cvs/{legacy}"), 409, "avant cv.json")
        self.assertEqual(self.client.get(f"/api/cvs/{legacy}/pdf").status_code, 200)
        self.assertProblem(self.client.get(f"/api/cvs/{legacy}/layout"), 404, "Zones introuvables")
        cv_id = self.new_cv()
        shutil.rmtree(self.applications / cv_id / "build")
        self.assertProblem(self.client.get(f"/api/cvs/{cv_id}/pdf"), 404, "PDF introuvable")

    def test_dangerous_identifiers(self):
        (self.folder / "secret.txt").write_text("secret", encoding="utf-8")
        os.symlink(self.folder, self.applications / "lien-vers-le-parent")
        os.symlink(self.applications / self.new_cv(), self.applications / "lien-vers-un-cv")
        for cv_id in ("..", "...", "%2e%2e", "..%2F..%2Fcandidate.yaml", "Majuscules", "a_b", "x" * 200,
                      "lien-vers-le-parent", "lien-vers-un-cv", "inexistant"):
            for suffix in ("", "/pdf", "/layout"):
                with self.subTest(cv_id=cv_id, suffix=suffix):
                    response = self.client.get(f"/api/cvs/{cv_id}{suffix}")
                    self.assertIn(response.status_code, (404, 405))
                    self.assertNotIn(b"secret", response.content)
                    self.assertNotIn(b"first_name", response.content)
        listed = [cv["id"] for cv in self.client.get("/api/cvs").json()]
        self.assertNotIn("lien-vers-le-parent", listed)
        self.assertNotIn("lien-vers-un-cv", listed)


class UpdateTest(ApiCvTestCase):

    def setUp(self):
        super().setUp()
        self.cv_id = self.new_cv()
        self.cv_folder = self.applications / self.cv_id
        self.doc = self.client.get(f"/api/cvs/{self.cv_id}").json()["document"]

    def files(self):
        return {name: sha(self.cv_folder / name) for name in
                ("cv.json", "sections/experience.tex", "build/layout.json",
                 f"build/{next(self.cv_folder.glob('*.tex')).stem}.pdf")}

    def test_edit_reorder_and_recompile(self):
        self.doc["experiences"].reverse()
        self.doc["experiences"][0]["bullets"][0] = "Puce modifiée & complétée."
        self.doc["projects"].append(entry_from_profile("projects", "bioinformatics-project", self.profile.data))
        response = self.client.put(f"/api/cvs/{self.cv_id}", json=self.doc)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["pages"], body["fits_one_page"], body["has_layout"]), (1, True, True))
        self.assertEqual(body["document"]["experiences"][0]["source_id"], "example-software-company")
        saved = json.loads((self.cv_folder / "cv.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, self.doc)
        self.assertEqual(self.rebuilds, [self.cv_folder.resolve()])
        self.assertEqual(sha(self.profile_path), sha(EXAMPLE_PATH))                    # le profil ne change pas

    def test_more_than_one_page_is_reported(self):
        self.doc["experiences"][0]["bullets"] *= 6
        body = self.client.put(f"/api/cvs/{self.cv_id}", json=self.doc).json()
        self.assertEqual((body["pages"], body["fits_one_page"]), (2, False))
        self.assertFalse(self.client.get("/api/cvs").json()[0]["fits_one_page"])

    def test_invalid_documents_change_nothing(self):
        before = self.files()
        cases = [
            ({**self.doc, "experiences": [{**self.doc["experiences"][0], "title": ""}]}, "experiences[0].title"),
            ({**self.doc, "extra": True}, "inconnu"),
            ({k: v for k, v in self.doc.items() if k != "header"}, "header"),
            ({**self.doc, "projects": self.doc["projects"] + [{**self.doc["projects"][0], "source_id": "invente"}]},
             "« invente » n'existe pas dans le profil"),
            ({**self.doc, "experiences": self.doc["experiences"] * 2}, "déjà dans le CV"),
        ]
        for doc, fragment in cases:
            with self.subTest(fragment):
                self.assertProblem(self.client.put(f"/api/cvs/{self.cv_id}", json=doc), 422, fragment)
        self.assertEqual(self.client.put(f"/api/cvs/{self.cv_id}", json=["pas un objet"]).status_code, 422)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.rebuilds, [])

    def test_failed_compilation_restores_the_previous_version(self):
        before = self.files()

        def broken(folder):
            (folder / "build" / "layout.json").unlink()
            next((folder / "build").glob("*.pdf")).write_bytes(b"%PDF partiel")
            raise RuntimeError(f"La compilation LaTeX a échoué ({folder}/x.tex) :\n./sections/experience.tex:12: Undefined")

        main.app.dependency_overrides[cvs.cv_rebuilder] = lambda: broken
        self.doc["experiences"][0]["bullets"].append("Nouvelle puce.")
        detail = self.assertProblem(self.client.put(f"/api/cvs/{self.cv_id}", json=self.doc), 422,
                                    "la version précédente du CV a été conservée")
        self.assertNotIn(str(self.applications), json.dumps(detail))
        self.assertEqual(self.files(), before)
        self.assertNotIn("Nouvelle puce.", (self.cv_folder / "cv.json").read_text(encoding="utf-8"))

    def test_concurrent_edits_and_legacy_cvs(self):
        cvs.LOCKS.acquire(self.cv_id)
        try:
            self.assertProblem(self.client.put(f"/api/cvs/{self.cv_id}", json=self.doc), 409, "en cours")
        finally:
            cvs.LOCKS.release(self.cv_id)
        self.assertEqual(self.client.put(f"/api/cvs/{self.cv_id}", json=self.doc).status_code, 200)
        self.assertProblem(self.client.put(f"/api/cvs/{self.legacy_cv()}", json=self.doc), 409, "avant cv.json")
        self.assertProblem(self.client.put("/api/cvs/inexistant", json=self.doc), 404, "CV introuvable")

    @unittest.skipUnless(shutil.which("latexmk"), "latexmk n'est pas installé")
    def test_real_recompilation(self):
        main.app.dependency_overrides[cvs.cv_rebuilder] = lambda: rebuild_cv
        self.doc["header"]["summary"] = "Résumé modifié avec **gras**, 100 % et R&D."
        body = self.client.put(f"/api/cvs/{self.cv_id}", json=self.doc).json()
        self.assertEqual((body["pages"], body["fits_one_page"], body["has_layout"]), (1, True, True))
        self.assertTrue(self.client.get(f"/api/cvs/{self.cv_id}/pdf").content.startswith(b"%PDF"))
        regions = self.client.get(f"/api/cvs/{self.cv_id}/layout").json()["regions"]
        self.assertIn("experiences/0", [r["key"] for r in regions])


class AnalysisRoutesTest(ApiCvTestCase):

    def test_saved_analysis_is_read_without_calling_claude(self):
        cv_id = self.new_cv()
        self.analyses.clear()
        analysis = self.client.get(f"/api/cvs/{cv_id}/analysis").json()
        self.assertEqual((analysis["status"], analysis["score"]["value"], analysis["running"]), ("completed", 72, False))
        summary = self.client.get("/api/cvs").json()[0]
        self.assertEqual((summary["analysis_status"], summary["fit_score"], summary["fit_level"]),
                         ("completed", 72, "Bonne adéquation"))
        self.assertEqual(self.client.get(f"/api/cvs/{cv_id}").json()["cv"]["analysis_status"], "completed")
        self.assertEqual(self.analyses, [])                                           # lecture seule : pas d'analyse

    def test_older_cv_gets_its_analysis_on_demand_without_regeneration(self):
        legacy = self.legacy_cv()
        folder = self.applications / legacy
        before = {p.name: sha(p) for p in folder.rglob("*") if p.is_file()}
        self.assertProblem(self.client.get(f"/api/cvs/{legacy}/analysis"), 404, "Analyse non disponible")
        self.assertEqual(self.client.get("/api/cvs").json()[0]["analysis_status"], "missing")
        self.assertEqual(self.analyses, [])

        task_id = self.client.post(f"/api/cvs/{legacy}/analysis").json()["task_id"]
        task = wait_for(self.client, task_id)
        self.assertEqual((task["status"], task["kind"], task["cv_id"]), ("completed", "analysis", legacy))
        self.assertEqual(task["result"]["fit_score"], 72)
        self.assertEqual(self.client.get(f"/api/cvs/{legacy}/analysis").json()["status"], "completed")
        self.assertEqual(self.generator_calls, [])                                    # le CV n'est pas régénéré
        after = {p.name: sha(p) for p in folder.rglob("*") if p.is_file() and p.name != "analysis.json"}
        self.assertEqual(after, before)

    def test_analysis_requests_are_refused_when_impossible(self):
        cv_id = self.new_cv()
        (self.applications / cv_id / "offer.json").unlink()
        self.assertProblem(self.client.post(f"/api/cvs/{cv_id}/analysis"), 409, "offer.json")
        self.assertProblem(self.client.post("/api/cvs/inexistant/analysis"), 404, "CV introuvable")
        self.assertEqual(self.client.post("/api/cvs/..%2F..%2Fprofile/analysis").status_code, 404)

    def test_one_analysis_at_a_time_per_cv_and_running_status(self):
        cv_id = self.new_cv()
        started, release = threading.Event(), threading.Event()

        def slow(folder, profile):
            started.set()
            release.wait(5)
            return self.fake_analyzer(folder, profile)

        main.app.dependency_overrides[cvs.cv_analyzer] = lambda: slow
        first = self.client.post(f"/api/cvs/{cv_id}/analysis").json()["task_id"]
        self.assertTrue(started.wait(5))
        self.assertProblem(self.client.post(f"/api/cvs/{cv_id}/analysis"), 409, "déjà en cours")
        self.assertEqual(self.client.get("/api/cvs").json()[0]["analysis_status"], "running")
        self.assertTrue(self.client.get(f"/api/cvs/{cv_id}/analysis").json()["running"])
        release.set()
        self.assertEqual(wait_for(self.client, first)["status"], "completed")

    def test_failed_analysis_is_reported_without_server_details(self):
        cv_id = self.new_cv()
        save_analysis(self.applications / cv_id, failed_analysis(
            "L'analyse de correspondance a échoué", [f"Claude a échoué dans {ROOT}/llm et {Path.home()}/x"]))
        analysis = self.client.get(f"/api/cvs/{cv_id}/analysis").json()
        self.assertEqual(analysis["status"], "failed")
        self.assertNotIn(str(ROOT), json.dumps(analysis))
        self.assertNotIn(str(Path.home()), json.dumps(analysis))
        self.assertEqual(self.client.get("/api/cvs").json()[0]["analysis_status"], "failed")

        def broken(folder, profile):
            raise RuntimeError(f"Claude n'a pas répondu ({ROOT}/x).")
        main.app.dependency_overrides[cvs.cv_analyzer] = lambda: broken
        task = wait_for(self.client, self.client.post(f"/api/cvs/{cv_id}/analysis").json()["task_id"])
        self.assertEqual(task["status"], "failed")
        self.assertNotIn(str(ROOT), json.dumps(task))
        self.assertEqual(load_analysis(self.applications / cv_id)["status"], "failed")  # l'ancienne reste en place

    def test_older_analysis_without_interview_questions_is_served_unchanged(self):
        # Analyses enregistrées avant interview_questions : lues telles quelles, jamais régénérées
        cv_id = self.new_cv()
        path = self.applications / cv_id / "analysis.json"
        self.assertNotIn("interview_questions", json.loads(path.read_text(encoding="utf-8")))
        before = sha(path)
        self.analyses.clear()
        analysis = self.client.get(f"/api/cvs/{cv_id}/analysis").json()
        self.assertEqual(analysis["status"], "completed")
        self.assertNotIn("interview_questions", analysis)
        self.assertEqual(self.client.get("/api/cvs").json()[0]["analysis_status"], "completed")
        self.assertEqual((sha(path), self.analyses), (before, []))

    def test_generation_keeps_the_cv_when_the_analysis_fails(self):
        # Le pipeline enregistre une analyse en échec (cv/pipeline.py) : le CV reste disponible
        self.fake_analyzer = lambda folder, profile: failed_analysis("L'analyse de correspondance a échoué",
                                                                     ["Claude n'a pas répondu."])
        task = wait_for(self.client, self.client.post("/api/cvs/generate", json={"url": "https://jobs.example.com/1"})
                        .json()["task_id"])
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"]["analysis_status"], "failed")
        self.assertEqual(self.client.get(f"/api/cvs/{task['cv_id']}/pdf").status_code, 200)


class DeleteTest(ApiCvTestCase):

    def setUp(self):
        super().setUp()
        self.cv_id = self.new_cv()
        self.folder = self.applications / self.cv_id

    def tree(self, folder: Path) -> dict:
        return {str(p.relative_to(folder)): sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}

    def test_the_whole_application_is_deleted(self):
        names = {p.name for p in self.folder.rglob("*") if p.is_file()}
        for expected in ("cv.json", "offer.json", "selection.json", "analysis.json", "layout.json", "experience.tex"):
            self.assertIn(expected, names)
        response = self.client.delete(f"/api/cvs/{self.cv_id}")
        self.assertEqual((response.status_code, response.content), (204, b""))
        self.assertFalse(self.folder.exists())
        self.assertEqual(list(self.applications.iterdir()), [])                       # pas de dossier caché restant
        self.assertEqual(self.client.get("/api/cvs").json(), [])
        for method, suffix in (("get", ""), ("get", "/pdf"), ("get", "/layout"), ("get", "/analysis"),
                               ("post", "/analysis"), ("delete", "")):
            with self.subTest(f"{method} {suffix}"):
                self.assertEqual(getattr(self.client, method)(f"/api/cvs/{self.cv_id}{suffix}").status_code, 404)
        self.assertEqual(self.client.put(f"/api/cvs/{self.cv_id}", json={}).status_code, 404)

    def test_other_applications_profile_and_template_are_kept(self):
        other = self.new_cv()
        legacy = self.legacy_cv()
        kept = {name: self.tree(self.applications / name) for name in (other, legacy)}
        profile, template = sha(self.profile_path), {p.name: sha(p) for p in build_cv.TEMPLATE_DIR.rglob("*") if p.is_file()}
        self.assertEqual(self.client.delete(f"/api/cvs/{self.cv_id}").status_code, 204)
        self.assertEqual({name: self.tree(self.applications / name) for name in kept}, kept)
        self.assertEqual(sha(self.profile_path), profile)
        self.assertEqual({p.name: sha(p) for p in build_cv.TEMPLATE_DIR.rglob("*") if p.is_file()}, template)
        self.assertEqual(sorted(cv["id"] for cv in self.client.get("/api/cvs").json()), sorted([other, legacy]))
        self.assertEqual(self.client.delete(f"/api/cvs/{legacy}").status_code, 204)          # ancien CV aussi

    def test_unknown_invalid_and_traversal_identifiers(self):
        outside = self.folder.parent.parent / "a-garder"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret", encoding="utf-8")
        before = self.tree(self.folder)
        for cv_id in ("inexistant", "..", "...", "%2e%2e", "..%2F..%2Fa-garder", "..%2Fcandidate.yaml", "Majuscules",
                      "a_b", "x" * 200, ".deleting-x", "%2Etmp", "a-garder"):
            with self.subTest(cv_id):
                self.assertIn(self.client.delete(f"/api/cvs/{cv_id}").status_code, (404, 405))
        self.assertEqual(self.client.delete("/api/cvs/").status_code, 405)
        self.assertTrue((outside / "secret.txt").exists())
        self.assertTrue(self.profile_path.exists())
        self.assertEqual(self.tree(self.folder), before)

    def test_symbolic_links(self):
        target = self.folder.parent.parent / "cible-externe"
        target.mkdir()
        (target / "important.txt").write_text("à garder", encoding="utf-8")
        os.symlink(target, self.applications / "lien-externe")
        os.symlink(self.folder, self.applications / "lien-vers-cv")
        for cv_id in ("lien-externe", "lien-vers-cv"):
            with self.subTest(cv_id):
                self.assertEqual(self.client.delete(f"/api/cvs/{cv_id}").status_code, 404)
        self.assertTrue((target / "important.txt").exists())
        self.assertTrue((self.folder / "cv.json").exists())

        # Un lien à l'intérieur du dossier supprimé est retiré, sa cible reste intacte
        os.symlink(target, self.folder / "lien-interne")
        os.symlink(target / "important.txt", self.folder / "fichier-lie.txt")
        self.assertEqual(self.client.delete(f"/api/cvs/{self.cv_id}").status_code, 204)
        self.assertEqual((target / "important.txt").read_text(encoding="utf-8"), "à garder")

    def test_refused_while_an_edit_is_running(self):
        cvs.LOCKS.acquire(self.cv_id)
        try:
            self.assertProblem(self.client.delete(f"/api/cvs/{self.cv_id}"), 409, "en cours")
        finally:
            cvs.LOCKS.release(self.cv_id)
        self.assertTrue((self.folder / "cv.json").exists())
        self.assertEqual(self.client.delete(f"/api/cvs/{self.cv_id}").status_code, 204)

    def test_refused_while_an_analysis_is_running(self):
        started, release = threading.Event(), threading.Event()

        def slow(folder, profile):
            started.set()
            release.wait(5)
            return self.fake_analyzer(folder, profile)

        main.app.dependency_overrides[cvs.cv_analyzer] = lambda: slow
        task_id = self.client.post(f"/api/cvs/{self.cv_id}/analysis").json()["task_id"]
        self.assertTrue(started.wait(5))
        self.assertProblem(self.client.delete(f"/api/cvs/{self.cv_id}"), 409, "Suppression impossible")
        release.set()
        self.assertEqual(wait_for(self.client, task_id)["status"], "completed")
        self.assertEqual(self.client.delete(f"/api/cvs/{self.cv_id}").status_code, 204)

    def test_refused_while_the_generation_of_this_cv_is_running(self):
        started, release = threading.Event(), threading.Event()

        def generator(url, profile, on_step=None, applications_dir=None):
            main_tex = write_cv(build_document(fake_draft(), profile), {"job_title": "Stage"},
                                applications_dir=applications_dir)
            on_step("compile", folder=main_tex.parent)                 # le dossier existe, la tâche le vise
            started.set()
            release.wait(5)
            pdf, pages = self.fake_compile(main_tex.parent)
            return GenerationResult(folder=main_tex.parent, main_tex=main_tex, pdf=pdf, pages=pages,
                                    document=build_document(fake_draft(), profile), issues=[], offer={})

        main.app.dependency_overrides[cvs.cv_generator] = lambda: generator
        task_id = self.client.post("/api/cvs/generate", json={"url": "https://jobs.example.com/2"}).json()["task_id"]
        self.assertTrue(started.wait(5))
        generating = self.client.get(f"/api/cvs/tasks/{task_id}").json()["cv_id"]
        self.assertNotEqual(generating, self.cv_id)
        self.assertProblem(self.client.delete(f"/api/cvs/{generating}"), 409, "en cours")
        self.assertEqual(self.client.delete(f"/api/cvs/{self.cv_id}").status_code, 204)       # un autre CV : permis
        release.set()
        self.assertEqual(wait_for(self.client, task_id)["status"], "completed")
        self.assertEqual(self.client.delete(f"/api/cvs/{generating}").status_code, 204)

    def test_deletion_errors_are_readable_and_without_local_paths(self):
        def refuse(source, destination):
            raise PermissionError(13, "Permission denied", str(source))

        with mock.patch.object(cvs.os, "replace", side_effect=refuse):
            detail = self.assertProblem(self.client.delete(f"/api/cvs/{self.cv_id}"), 500, "rien n'a été effacé")
        self.assertNotIn(str(self.applications), json.dumps(detail))
        self.assertTrue((self.folder / "cv.json").exists())                       # rien n'a été effacé

        def partial(path):
            raise OSError(66, "Directory not empty", str(path))

        with mock.patch.object(cvs.shutil, "rmtree", side_effect=partial):
            detail = self.assertProblem(self.client.delete(f"/api/cvs/{self.cv_id}"), 500, "Suppression incomplète")
        self.assertNotIn(str(self.applications), json.dumps(detail))
        self.assertNotIn(self.cv_id, [cv["id"] for cv in self.client.get("/api/cvs").json()])   # n'apparaît plus
        self.assertFalse(cvs.LOCKS._lock(self.cv_id).locked())                                  # verrou libéré


class DatesTest(ApiCvTestCase):
    """created_at = vraie date de génération (metadata.json), jamais celle du template ; updated_at suit les modifications."""

    OLD = time.mktime((2001, 1, 1, 12, 0, 0, 0, 0, -1))

    def dates(self, cv_id):
        listed = next(cv for cv in self.client.get("/api/cvs").json() if cv["id"] == cv_id)
        return listed["created_at"], listed["updated_at"]

    def test_creation_date_is_the_generation_time_and_survives_edits(self):
        before = time.time()
        cv_id = self.new_cv()
        after = time.time()
        folder = self.applications / cv_id
        os.utime(folder, (self.OLD, self.OLD))          # date du dossier = date du template copié
        created, updated = self.dates(cv_id)
        self.assertTrue(before - 1 <= created <= after + 1)
        self.assertNotEqual(created, folder.stat().st_mtime)
        detail = self.client.get(f"/api/cvs/{cv_id}").json()["cv"]
        self.assertEqual((detail["created_at"], detail["updated_at"]), (created, updated))

        doc = self.client.get(f"/api/cvs/{cv_id}").json()["document"]
        doc["header"]["summary"] = "Résumé modifié."
        time.sleep(0.01)
        body = self.client.put(f"/api/cvs/{cv_id}", json=doc).json()
        self.assertEqual(body["cv"]["created_at"], created)
        self.assertGreater(body["cv"]["updated_at"], updated)
        self.assertEqual(self.dates(cv_id), (created, body["cv"]["updated_at"]))

    def test_failed_recompilation_changes_no_date(self):
        cv_id = self.new_cv()
        dates = self.dates(cv_id)
        doc = self.client.get(f"/api/cvs/{cv_id}").json()["document"]
        doc["header"]["summary"] = "Résumé modifié."
        main.app.dependency_overrides[cvs.cv_rebuilder] = lambda: mock.Mock(side_effect=RuntimeError("LaTeX"))
        self.assertEqual(self.client.put(f"/api/cvs/{cv_id}", json=doc).status_code, 422)
        self.assertEqual(self.dates(cv_id), dates)

    def test_legacy_cv_has_no_invented_date_and_stays_readable(self):
        cv_id = self.legacy_cv()
        folder = self.applications / cv_id
        (folder / "offer.json").unlink()
        os.utime(folder, (self.OLD, self.OLD))
        created, updated = self.dates(cv_id)
        self.assertIsNone(created)
        self.assertIsNotNone(updated)
        self.assertEqual(self.client.get(f"/api/cvs/{cv_id}/pdf").status_code, 200)
        self.assertFalse((folder / "metadata.json").exists())   # les dossiers existants ne sont pas modifiés

    def test_list_puts_newest_creations_first_and_unknown_dates_last(self):
        legacy = self.legacy_cv()
        (self.applications / legacy / "offer.json").unlink()
        first = self.new_cv()
        time.sleep(0.01)
        second = self.new_cv()
        ids = [cv["id"] for cv in self.client.get("/api/cvs").json()]
        self.assertEqual(ids, [second, first, legacy])


class CompatibilityTest(ApiCvTestCase):

    def test_candidate_endpoints_still_work(self):
        self.assertEqual(self.client.get("/api/profile").json()["personal"]["first_name"], "John")
        self.assertEqual(self.client.post("/api/interests", json={"interest": "Chess"}).status_code, 201)
        self.assertEqual(self.client.get("/api/imports").status_code, 200)


if __name__ == "__main__":
    unittest.main()
