#!/usr/bin/env python3
"""No archive filename may be upgraded into as-of/continuous OI proof."""
import json
import unittest
from research.detector_h1h10_existing_r2_archive_census import (
    classify,parse_manifest
)

class ArchiveMetadata(unittest.TestCase):
 def sample(self):
    return {"schema":"detector-research-r2-v1","run_id":39000000000,
      "workflow":"Detector H1-H10 Three-Day Real AggTrades Expansion",
      "head_sha":"a"*40,
      "artifacts":[{"key":"research/39000000000/1200-detector-flow.zip",
       "artifact_id":1200,"name":"detector-flow","bytes":6500,"sha256":"b"*64}]}
 def test_classification_only_suggests_candidate(self):
    self.assertIn("taker_flow",classify("H1-H10 aggTrades","flow"))
    self.assertIn("open_interest",classify("OI availability history","some-run"))
    self.assertIn("open_interest",classify("Detector H1-H10 OI Semantics","baseline"))
    self.assertNotIn("open_interest",classify("coin metric","BTCUSDT"))
 def test_parsed_archive_is_metadata_only(self):
    rows=parse_manifest("research/39000000000/manifest.json",json.dumps(self.sample()).encode())
    self.assertEqual(len(rows),1)
    self.assertEqual(rows[0]["candidate_5m_continuous_oi"],"NOT_PROVEN")
    self.assertEqual(rows[0]["candidate_true_first_publication"],"NOT_PROVEN")
    self.assertEqual(rows[0]["content_evidence"],"ARCHIVED_MANIFEST_METADATA_ONLY")
 def test_invalid_run_id_rejected(self):
    with self.assertRaisesRegex(ValueError,"MANIFEST_SCHEMA_OR_ID"):
      parse_manifest("research/39000000001/manifest.json",json.dumps(self.sample()).encode())
 def test_object_path_mismatch_rejected(self):
    m=self.sample()
    m["artifacts"][0]["key"]="research/999/1200-detector-flow.zip"
    with self.assertRaisesRegex(ValueError,"ARCHIVE_OBJECT_PATH_INVALID"):
      parse_manifest("research/39000000000/manifest.json",json.dumps(m).encode())
 def test_empty_archive_rejected(self):
    m=self.sample();m["artifacts"]=[]
    with self.assertRaisesRegex(ValueError,"ARCHIVE_NO_ARTIFACTS"):
      parse_manifest("research/39000000000/manifest.json",json.dumps(m).encode())

if __name__=="__main__":unittest.main()
