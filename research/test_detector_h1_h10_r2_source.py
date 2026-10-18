#!/usr/bin/env python3
"""Offline tests: immutable source selection and safe ZIP extraction."""
import io
import unittest
import zipfile
from research.detector_h1_h10_r2_source import choose, safe_members


class R2SourceTests(unittest.TestCase):
    def test_newest_archived_source_by_workflow_and_artifact(self):
        def row(run_id, artifact):
            return {"schema": "detector-research-r2-v1", "workflow": "Detector H1-H10 sample",
                    "run_id": run_id, "artifacts": [{"name": artifact, "key": "x"}]}
        rid, _, _ = choose([row(6, "expected"), row(10, "other"), row(9, "expected")],
                           "Detector H1-H10 sample", "expected")
        self.assertEqual(rid, 9)

    def test_source_missing_is_closed(self):
        with self.assertRaisesRegex(ValueError, "ARCHIVED_SOURCE_MISSING"):
            choose([], "Detector H1-H10 sample", "expected")

    def test_duplicate_run_is_rejected(self):
        m = {"schema": "detector-research-r2-v1", "workflow": "wf", "run_id": 1,
             "artifacts": [{"name": "a"}, {"name": "a"}]}
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_ARCHIVED_SOURCE"):
            choose([m], "wf", "a")

    def test_zip_traversal_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../escape.txt", "do-not-extract")
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            with self.assertRaisesRegex(ValueError, "UNSAFE_ZIP_MEMBER"):
                safe_members(z)

    def test_normal_zip_allowed(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("BTCUSDT_research_5m.csv", "a,b\n1,2\n")
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            self.assertEqual(len(safe_members(z)), 1)


if __name__ == "__main__":
    unittest.main()
