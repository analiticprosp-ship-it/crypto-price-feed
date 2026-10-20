"""Offline error taxonomy for short-window archival reconciliation."""
import datetime as dt
import unittest
from research.detector_archive_policy import (
  artifact_plan,no_artifact_classification,is_research_candidate,
  is_recent,MAX_ARTIFACT_BYTES,OPERATIONAL_WORKFLOWS,select_since_cursor
)

def art(id=1,expired=False,size=200):
    return {"id":id,"expired":expired,"size_in_bytes":size,
      "name":"r","archive_download_url":"https://api.github.com/repos/a/b/actions/artifacts/1/zip"}

class ArtifactPolicy(unittest.TestCase):
 def test_historical_expired_not_a_new_upload_failure(self):
    v,s=artifact_plan([art(expired=True)])
    self.assertEqual(v,[])
    self.assertEqual(no_artifact_classification([art(expired=True)],s),"HISTORICAL_ARTIFACTS_EXPIRED")
 def test_workflow_succeeded_without_artifact_is_not_upload_failure(self):
    self.assertEqual(no_artifact_classification([],[]),"SUCCESSFUL_WORKFLOW_WITH_NO_ARTIFACT_OUTPUT")
 def test_mixed_artifacts_preserve_all_available(self):
    v,s=artifact_plan([art(id=1,expired=True),art(id=2)])
    self.assertEqual([x["id"] for x in v],[2])
    self.assertEqual(s[0]["reason"],"EXPIRED_GITHUB_RETENTION")
 def test_oversized_bounded_not_downloaded(self):
    v,s=artifact_plan([art(size=MAX_ARTIFACT_BYTES+1)])
    self.assertEqual(v,[])
    self.assertEqual(s[0]["reason"],"ARTIFACT_EXCEEDS_SAFETY_CAP")
 def test_empty_archive_not_downloaded(self):
    v,s=artifact_plan([art(size=0)])
    self.assertEqual(len(v),0)
    self.assertEqual(s[0]["reason"],"EMPTY_ARTIFACT")
 def test_missing_artifact_size_fail_closed(self):
    with self.assertRaises(ValueError):artifact_plan([{"id":1,"expired":False}])
 def test_missing_source_url_fail_closed(self):
    v=art();v["archive_download_url"]=""
    with self.assertRaises(ValueError):artifact_plan([v])
 def test_malformed_artifact_collection_fail_closed(self):
    with self.assertRaises(ValueError):artifact_plan({"artifacts":[]})
 def test_research_main_success(self):
    x={"id":12,"name":"Detector H1-H10 Historical Dataset",
       "head_branch":"main","conclusion":"success"}
    self.assertTrue(is_research_candidate(x))
 def test_nonresearch_workflow_excluded(self):
    x={"id":12,"name":"Update critical crypto prices",
       "head_branch":"main","conclusion":"success"}
    self.assertFalse(is_research_candidate(x))
 def test_self_archiver_excluded(self):
    for name in OPERATIONAL_WORKFLOWS:
      x={"id":12,"name":name,"head_branch":"main","conclusion":"success"}
      self.assertFalse(is_research_candidate(x))
 def test_failed_workflow_excluded(self):
    x={"id":12,"name":"Detector H1-H10 Historical Dataset",
       "head_branch":"main","conclusion":"failure"}
    self.assertFalse(is_research_candidate(x))
 def test_time_filter_recent_and_old(self):
    now=dt.datetime(2026,10,20,tzinfo=dt.timezone.utc)
    self.assertTrue(is_recent("2026-10-19T23:10:00Z",now))
    self.assertFalse(is_recent("2026-10-01T00:00:00Z",now))
 def test_cursor_pagination_stops_at_previous_verified_run(self):
    fresh,stop=select_since_cursor([{"id":109},{"id":108},{"id":107},{"id":106}],107)
    self.assertEqual([x["id"] for x in fresh],[109,108])
    self.assertTrue(stop)
 def test_cursor_pagination_continue_for_all_new_runs(self):
    fresh,stop=select_since_cursor([{"id":109},{"id":108}],107)
    self.assertEqual(len(fresh),2)
    self.assertFalse(stop)
 def test_cursor_pagination_order_must_fail_closed(self):
    with self.assertRaises(ValueError):select_since_cursor([{"id":108},{"id":109}],107)
 def test_cursor_missing_id_must_fail_closed(self):
    with self.assertRaises(ValueError):select_since_cursor([{"foo":1}],107)
 def test_naive_timestamp_rejected(self):
    with self.assertRaises(ValueError):
      is_recent("2026-10-20T01:00:00",dt.datetime.now(dt.timezone.utc))
if __name__=="__main__":
 unittest.main()
