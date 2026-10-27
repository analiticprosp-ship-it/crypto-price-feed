import datetime as dt,importlib.util,json,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('p1forward',Path(__file__).with_name('runner.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_no_backfill_or_early_forecast(self):
  first=dt.date(2026,11,1);UTC=dt.timezone.utc
  self.assertFalse(m.eligible_window(dt.datetime(2026,10,27,12,tzinfo=UTC),dt.date(2026,10,25),first))
  self.assertFalse(m.eligible_window(dt.datetime(2026,11,2,9,59,tzinfo=UTC),first,first))
  self.assertTrue(m.eligible_window(dt.datetime(2026,11,2,10,15,tzinfo=UTC),first,first))
  self.assertFalse(m.eligible_window(dt.datetime(2026,11,3,10,tzinfo=UTC),first,first))
 def test_latest_complete_sunday(self):
  self.assertEqual(m.last_sunday(dt.datetime(2026,11,1,22,tzinfo=dt.timezone.utc)),dt.date(2026,10,25))
  self.assertEqual(m.last_sunday(dt.datetime(2026,11,2,0,tzinfo=dt.timezone.utc)),dt.date(2026,11,1))
 def test_parent_flags_and_states_exact(self):
  root=Path(__file__).parents[1]/'p1_work/sources'
  if not root.exists():self.skipTest('local frozen parents unavailable')
  a=json.loads((root/'v86/extended_history.json').read_text());b=json.loads((root/'v89/multiscale.json').read_text());proof=m.acceptance(a,b)
  self.assertEqual(proof['BTC_fast_flags_verified'],781);self.assertEqual(proof['structural_states_verified'],750)
 def test_writes_confined_to_research(self):
  with self.assertRaisesRegex(ValueError,'OUT_OF_SCOPE_WRITE'):m.immutable(None,None,'prices.json',b'x')
 def test_missing_future_is_pending(self):
  r={'asof_sunday':'2026-11-01'}
  self.assertIsNone(m.evaluate_record(r,{}))
if __name__=='__main__':unittest.main()
