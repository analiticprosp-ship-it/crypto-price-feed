"""Verify exact market bar close is distinct from first detector observation."""
import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_signal_journal import annotate, event_id, time_iso, VERSION

END=1792125900000 # 2026-10-16 05:05:00 UTC, closed-bucket example
FIRST=END+10*60_000

def snapshot(end=END, symbol="AAVE", direction="LONG"):
    return {"generatedAt":time_iso(FIRST),"researchOnly":True,
            "notTradeApproval":True,"sourceProvenance":{"marketSummaryGeneratedAt":time_iso(FIRST)},
            "instruments":{symbol:{direction:{"status":"EARLY_CANDIDATE_SHADOW"}}},
            "candidates":[{"symbol":symbol,"direction":direction,
                           "status":"EARLY_CANDIDATE_SHADOW",
                           "eventEndMs":end,
                           "families":["PRICE_STRUCTURE","TAKER_VOLUME"],
                           "oiRole":"CONTEXT_ONLY"}]}

def empty_snapshot():
    d=snapshot()
    d["candidates"]=[]
    return d

class TestEventJournal(unittest.TestCase):
    def test_first_install_does_not_spam_preexisting_candidates(self):
        report,log=annotate(snapshot(),None,now_ms=FIRST)
        self.assertEqual(log["status"],"BOOTSTRAPPED_NO_ALERTS")
        self.assertEqual(log["newEventCount"],0)
        self.assertEqual(len(log["events"]),1)
        event=log["events"][0]
        self.assertIsNone(event["firstDetectedAtUtc"])
        self.assertFalse(event["notificationEligible"])
        self.assertTrue(event["initialSnapshotBaseline"])
        self.assertEqual(report["candidates"][0]["signalCandleClosedAtMadrid"],time_iso(END,True))

    def test_new_signal_has_distinct_exact_times_and_lag(self):
        _,base=annotate(empty_snapshot(),None,now_ms=FIRST-5*60_000)
        report,log=annotate(snapshot(),base,now_ms=FIRST)
        self.assertEqual(log["status"],"ACTIVE")
        self.assertEqual(log["newEventCount"],1)
        event=log["events"][0]
        self.assertEqual(event["signalCandleClosedAtMs"],END)
        self.assertEqual(event["firstDetectedAtUtc"],time_iso(FIRST))
        self.assertEqual(event["detectionLagSeconds"],600)
        self.assertNotEqual(event["signalCandleClosedAtUtc"],event["firstDetectedAtUtc"])
        self.assertTrue(event["notificationEligible"])
        self.assertEqual(report["candidates"][0]["detectionLagSeconds"],600)
        self.assertTrue(report["noExecutionLevels"] if "noExecutionLevels" in report else event["notExecutablePrice"])
        self.assertIn("+02:00",event["firstDetectedAtMadrid"])

    def test_repeated_run_does_not_alert_same_candle_again(self):
        _,base=annotate(empty_snapshot(),None,now_ms=FIRST-5*60_000)
        _,first=annotate(snapshot(),base,now_ms=FIRST)
        report,second=annotate(snapshot(),first,now_ms=FIRST+120000)
        self.assertEqual(second["newEventCount"],0)
        self.assertEqual(second["events"][0]["firstDetectedAtUtc"],time_iso(FIRST))
        self.assertEqual(report["candidates"][0]["firstDetectedAtUtc"],time_iso(FIRST))

    def test_new_candle_has_distinct_event_key(self):
        _,base=annotate(empty_snapshot(),None,now_ms=FIRST-5*60_000)
        _,first=annotate(snapshot(),base,now_ms=FIRST)
        nxt=END+15*60000
        _,second=annotate(snapshot(end=nxt),first,now_ms=nxt+2*60000)
        self.assertEqual(second["newEventCount"],1)
        self.assertEqual(len(second["events"]),2)
        self.assertNotEqual(second["events"][0]["eventId"],second["events"][1]["eventId"])

    def test_corrupt_existing_journal_must_never_reset(self):
        with self.assertRaisesRegex(ValueError,"INVALID_EXISTING_EVENT_JOURNAL"):
            annotate(snapshot(),{"schemaVersion":"wrong","events":[]},now_ms=FIRST)

    def test_future_or_too_old_signal_rejected(self):
        _,base=annotate(empty_snapshot(),None,now_ms=FIRST-5*60_000)
        with self.assertRaisesRegex(ValueError,"CANDIDATE_OUTSIDE_VALID_CLOSED_BAR_WINDOW"):
            annotate(snapshot(end=FIRST+60_000),base,now_ms=FIRST)
        with self.assertRaisesRegex(ValueError,"CANDIDATE_OUTSIDE_VALID_CLOSED_BAR_WINDOW"):
            annotate(snapshot(end=FIRST-40*60000),base,now_ms=FIRST)

    def test_new_signal_stays_research_only(self):
        _,base=annotate(empty_snapshot(),None,now_ms=FIRST-5*60_000)
        _,log=annotate(snapshot(),base,now_ms=FIRST)
        event=log["events"][0]
        self.assertTrue(log["researchOnly"])
        self.assertTrue(log["notTradeApproval"])
        self.assertTrue(event["notExecutablePrice"])
        self.assertTrue(event["noProvenEdge"])

if __name__=="__main__":
    unittest.main()
