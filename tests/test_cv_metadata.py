"""
Tests des dates d'une candidature (cv/metadata.py) : date de création explicite écrite par write_cv,
conservée lors des recompilations, et règles prudentes pour les CV créés avant metadata.json.
Données fictives, dossiers temporaires ; la compilation réelle est ignorée sans latexmk.

Lancement :  python -m unittest discover tests
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from cv import build_cv
from cv.build_cv import rebuild_cv, write_cv
from cv.document import build_document, load_document, save_document
from cv.metadata import (METADATA_FILE, create_metadata, cv_dates, mark_updated, now_utc, read_metadata,
                         to_timestamp)
from cv_fixtures import example_profile, fake_draft

OLD = time.mktime((2001, 1, 1, 12, 0, 0, 0, 0, -1))     # date « du template » : jamais une date de génération


class MetadataTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)

    def test_timestamps_are_utc(self):
        stamp = now_utc()
        self.assertRegex(stamp, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$")
        self.assertAlmostEqual(to_timestamp(stamp), time.time(), delta=5)
        self.assertEqual(to_timestamp("2026-10-22T10:00:00Z"), 1792663200.0)
        self.assertEqual(to_timestamp("2026-10-22T12:00:00+02:00"), 1792663200.0)
        for invalid in (None, 12, "", "hier", "2026-10-22T10:00:00"):   # sans fuseau : on ne devine pas
            self.assertIsNone(to_timestamp(invalid))

    def test_created_once_then_only_updated_at_changes(self):
        create_metadata(self.folder, created_at="2026-10-22T10:00:00.000000Z")
        mark_updated(self.folder)
        data = read_metadata(self.folder)
        self.assertEqual(data["created_at"], "2026-10-22T10:00:00.000000Z")
        self.assertGreater(to_timestamp(data["updated_at"]), to_timestamp(data["created_at"]))
        self.assertEqual(cv_dates(self.folder, OLD), (1792663200.0, to_timestamp(data["updated_at"])))

    def test_legacy_cv_without_reliable_date_is_unknown(self):
        os.utime(self.folder, (OLD, OLD))
        self.assertEqual(cv_dates(self.folder, OLD), (None, OLD))
        mark_updated(self.folder)                       # un ancien CV ne reçoit pas de date inventée
        self.assertFalse((self.folder / METADATA_FILE).exists())

    def test_legacy_cv_uses_the_creation_of_offer_json_when_the_system_knows_it(self):
        (self.folder / "offer.json").write_text("{}", encoding="utf-8")
        stat = (self.folder / "offer.json").stat()
        os.utime(self.folder, (OLD, OLD))
        created, updated = cv_dates(self.folder, OLD)
        self.assertEqual(created, getattr(stat, "st_birthtime", None))   # None hors macOS : pas de st_ctime
        self.assertEqual(updated, OLD)

    def test_unreadable_metadata_falls_back_without_error(self):
        for content in ("{pas du json", "[]", json.dumps({"created_at": "hier"})):
            (self.folder / METADATA_FILE).write_text(content, encoding="utf-8")
            self.assertEqual(cv_dates(self.folder, OLD), (None, OLD))


class WriteCvDatesTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        original = build_cv.APPLICATIONS_DIR
        build_cv.APPLICATIONS_DIR = self.folder
        self.addCleanup(setattr, build_cv, "APPLICATIONS_DIR", original)
        self.doc = build_document(fake_draft(), example_profile())

    def test_write_cv_records_the_generation_time_not_the_template_date(self):
        template = build_cv.TEMPLATE_DIR
        copy = self.folder / "template"
        shutil.copytree(template, copy)
        os.utime(copy, (OLD, OLD))                      # template « ancien » : copytree recopie cette date
        original = build_cv.TEMPLATE_DIR
        build_cv.TEMPLATE_DIR = copy
        self.addCleanup(setattr, build_cv, "TEMPLATE_DIR", original)

        before = time.time()
        folder = write_cv(self.doc, {"job_title": "Stage"}).parent
        after = time.time()
        if hasattr(folder.stat(), "st_birthtime"):      # macOS : la « création » du dossier est celle du template
            self.assertLess(folder.stat().st_birthtime, before)
        data = read_metadata(folder)
        self.assertEqual(data["created_at"], data["updated_at"])
        created, _ = cv_dates(folder, OLD)
        self.assertTrue(before - 1 <= created <= after + 1, (before, created, after))

    @unittest.skipUnless(shutil.which("latexmk"), "latexmk n'est pas installé")
    def test_recompilation_keeps_the_creation_date(self):
        folder = write_cv(self.doc, {}).parent
        created = read_metadata(folder)["created_at"]
        doc = load_document(folder)
        doc["header"]["summary"] = "Résumé modifié."
        save_document(folder, doc)
        rebuild_cv(folder)
        self.assertEqual(read_metadata(folder)["created_at"], created)


if __name__ == "__main__":
    unittest.main()
