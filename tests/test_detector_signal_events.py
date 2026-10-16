"""Historical event clocks: never call bar close GitHub detection or notification time."""
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_signal_events import empty_ledger,add_signal_events

NOW=1800000000000
P15=900000
def dt(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()
def report(now=NOW,end=None,symbol="SOL",direction="LONG",gate=True):
    end=now-P15 if end is None else end
    return {
        "generatedAt":dt(now),
        "researchOnly":True,"notTradeApproval":True,
        "dataGate":{"ok":gate},
        "sourceProvenance":{"marketSummaryGeneratedAt":dt(now-30000),
                            "takerRestGeneratedAt":dt(now-20000)},
        "candidates":[{"symbol":symbol,"direction":direction,
                       "eventEndMs":end,"status":"EARLY_CANDIDATE_SHADOW"}]
    }

class SignalEventClock(unittest.TestCase):
    def test_bootstrap_marks_preexisting_not_an_alert(self):
        old,new=add_signal_events(report(),empty_ledger())
        self.assertEqual(new,[])
        self.assertEqual(old["eventCount"],1)
        item=old["events"][0]
        self.assertEqual(item["notificationStatus"],"PREEXISTING_AT_FIRST_LEDGER_RUN")
        self.assertFalse(item["alertEligible"])
        self.assertEqual(item["barClosedAtUtc"],dt(NOW-P15)+".000" if False else datetime.fromtimestamp((NOW-P15)/1000,timezone.utc).isoformat(timespec="milliseconds"))
        self.assertEqual(item["firstDetectedAtUtc"],datetime.fromtimestamp(NOW/1000,timezone.utc).isoformat(timespec="milliseconds"))
        self.assertEqual(item["lagBarCloseToDetectionSeconds"],900)
        self.assertIn("+",item["firstDetectedAtMadrid"])
    def test_new_bar_alert_and_identity_dedup(self):
        baseline,_=add_signal_events(report(),empty_ledger())
        nxt=NOW+P15
        latest=report(now=nxt,end=NOW)
        saved,events=add_signal_events(latest,baseline)
        self.assertEqual(len(events),1)
        self.assertTrue(events[0]["alertEligible"])
        self.assertEqual(events[0]["lagBarCloseToDetectionSeconds"],900)
        self.assertEqual(saved["eventCount"],2)
        nxt2=report(now=nxt+30000,end=NOW)
        nxt2["sourceProvenance"]["marketSummaryGeneratedAt"]=dt(nxt+10000)
        nxt2["sourceProvenance"]["takerRestGeneratedAt"]=dt(nxt+20000)
        repeat,new=add_signal_events(nxt2,saved)
        self.assertEqual(new,[])
        self.assertEqual(repeat["events"],saved["events"])
        self.assertEqual(repeat["eventCount"],2)
    def test_not_marking_intra_bar_time_as_known(self):
        ledger,_=add_signal_events(report(),empty_ledger())
        item=ledger["events"][0]
        self.assertEqual(item["eventTimeResolution"],"CLOSED_15M_NOT_INTRABAR_TICK")
        self.assertEqual(item["publicationLagAfterDetection"],
                         "GITHUB_COMMIT_AND_ALERT_DELIVERY_NOT_OBSERVED")
        self.assertIsNone(item.get("deliveredAtUtc"))
    def test_signal_never_published_before_source(self):
        out=report()
        out["sourceProvenance"]["takerRestGeneratedAt"]=dt(NOW+20000)
        with self.assertRaises(ValueError):
            add_signal_events(out,empty_ledger())
        out=report()
        out["candidates"][0]["eventEndMs"]=NOW+P15
        result,new=add_signal_events(out,empty_ledger())
        self.assertFalse(result["events"])
        self.assertFalse(new)
    def test_stale_or_invalid_gate_no_events(self):
        v=report(gate=False)
        out,new=add_signal_events(v,empty_ledger())
        self.assertEqual(out["eventCount"],0)
        self.assertEqual(new,[])
        self.assertTrue(out["initialized"])
        n=report(now=NOW+P15,end=NOW)
        n["sourceProvenance"]={"marketSummaryGeneratedAt":dt(NOW+P15-30000),
                               "takerRestGeneratedAt":dt(NOW+P15-20000)}
        out,new=add_signal_events(n,out)
        self.assertEqual(len(new),1)
        self.assertTrue(new[0]["alertEligible"])
    def test_bad_or_rewritten_history_is_rejected(self):
        with self.assertRaises(ValueError):
            add_signal_events(report(),{"schemaVersion":"wrong","events":[]})
        ok,_=add_signal_events(report(),empty_ledger())
        ok["events"].append(dict(ok["events"][0]))
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            add_signal_events(report(),ok)
    def test_market_close_utc_and_madrid_distinct(self):
        from detector_signal_events import madrid,iso
        t=int(datetime(2026,10,16,4,15,tzinfo=timezone.utc).timestamp()*1000)
        self.assertEqual(iso(t),"2026-10-16T04:15:00.000+00:00")
        self.assertEqual(madrid(t),"2026-10-16T06:15:00.000+02:00")
        t=int(datetime(2026,11,16,4,15,tzinfo=timezone.utc).timestamp()*1000)
        self.assertEqual(madrid(t),"2026-11-16T05:15:00.000+01:00")

if __name__=="__main__":
    unittest.main()
