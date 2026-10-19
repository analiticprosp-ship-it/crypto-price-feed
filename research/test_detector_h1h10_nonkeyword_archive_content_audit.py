#!/usr/bin/env python3
"""Guarantee archive complement is exactly 17 and never upgrades labels into PIT."""
import unittest
from research.detector_h1h10_nonkeyword_archive_content_audit import (
 select_nonkeyword,EXPECTED_TOTAL,EXPECTED_OLD,EXPECTED_COMPLEMENT
)

def fake():
 all_rows=[{"archive_object_key":f"research/{390000+i}/1-a.zip",
            "artifact_name":f"artifact-{i}","archive_bytes":20,
            "run_id":390000+i,"workflow":"test","archive_expected_sha256":"a"*64}
           for i in range(EXPECTED_TOTAL)]
 return {"all_archives":all_rows,"candidate_artifacts":all_rows[:EXPECTED_OLD]}

class Complement(unittest.TestCase):
 def test_exact_17_unselected_archive_members(self):
  r=select_nonkeyword(fake())
  self.assertEqual(len(r),EXPECTED_COMPLEMENT)
  self.assertEqual(r[0]["artifact_name"],"artifact-19")
 def test_selected_archives_are_never_reaudited_as_complement(self):
  doc=fake()
  remaining=select_nonkeyword(doc)
  self.assertFalse({r["archive_object_key"] for r in remaining}.intersection(
       r["archive_object_key"] for r in doc["candidate_artifacts"]))
 def test_candidate_set_cardinality_refused(self):
  doc=fake();doc["candidate_artifacts"].pop()
  with self.assertRaisesRegex(ValueError,"PINNED_ARCHIVE_CENSUS_CARDINALITY_CHANGED"):
   select_nonkeyword(doc)
 def test_duplicate_archive_key_refused(self):
  doc=fake()
  doc["all_archives"][35]["archive_object_key"]=doc["all_archives"][34]["archive_object_key"]
  with self.assertRaisesRegex(ValueError,"PINNED_ARCHIVE_SET_NOT_UNIQUE"):
   select_nonkeyword(doc)
 def test_selected_candidate_not_in_all_refused(self):
  doc=fake()
  doc["candidate_artifacts"][0]={
    **doc["candidate_artifacts"][0],"archive_object_key":"research/999/1-phantom.zip"}
  with self.assertRaisesRegex(ValueError,"PINNED_ARCHIVE_SET_NOT_UNIQUE"):
   select_nonkeyword(doc)

if __name__=="__main__":unittest.main()
