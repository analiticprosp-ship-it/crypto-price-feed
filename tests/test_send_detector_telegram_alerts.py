"""Telegram transport gates: no duplicates, no prior baseline replay, no trade orders."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_signal_journal import annotate
from send_detector_telegram_alerts import fresh_events,format_message

END=1792125900000
NOW=END+600_000

def report(end=END, direction="LONG"):
    return {"researchOnly":True,"notTradeApproval":True,
            "sourceProvenance":{},
            "instruments":{"AAVE":{direction:{"status":"EARLY_CANDIDATE_SHADOW"}}},
            "candidates":[{"symbol":"AAVE","direction":direction,"status":"EARLY_CANDIDATE_SHADOW",
                           "eventEndMs":end,"families":["PRICE_STRUCTURE","TAKER_VOLUME"],"oiRole":"NO_DATA"}]}
def init_empty():
    r=report();r["candidates"]=[]
    return annotate(r,None,now_ms=NOW-1000)[1]

class TestTelegramShadowNotification(unittest.TestCase):
    def test_baseline_suppressed(self):
        _,journal=annotate(report(),None,now_ms=NOW)
        self.assertEqual(fresh_events(journal),[])
    def test_new_signal_has_explicit_both_times(self):
        _,j=annotate(report(),init_empty(),now_ms=NOW)
        alerts=fresh_events(j)
        self.assertEqual(len(alerts),1)
        msg=format_message(alerts[0])
        self.assertIn("AAVE",msg)
        self.assertIn("ранний LONG",msg)
        self.assertIn("Сигнальная свеча закрылась",msg)
        self.assertIn("Впервые обнаружено алгоритмом",msg)
        self.assertIn("Задержка обнаружения: 10.0 мин",msg)
        self.assertIn("EARLY_CANDIDATE_SHADOW",msg)
        self.assertIn("Нет подтверждения прибыли",msg)
    def test_no_repeated_delivery_after_next_run(self):
        _,j=annotate(report(),init_empty(),now_ms=NOW)
        _,repeat=annotate(report(),j,now_ms=NOW+2000)
        self.assertEqual(repeat["newEventCount"],0)
        self.assertEqual(fresh_events(repeat),[])
    def test_new_candle_with_same_direction_suppressed_one_hour(self):
        _,j=annotate(report(),init_empty(),now_ms=NOW)
        new_bar=END+900_000
        _,repeat=annotate(report(end=new_bar),j,now_ms=new_bar+60000)
        self.assertEqual(repeat["newEventCount"],1)
        self.assertEqual(repeat["events"][-1]["suppressionReason"],
                         "REPEATED_SYMBOL_DIRECTION_WITHIN_60M")
        self.assertEqual(fresh_events(repeat),[])
    def test_reversed_direction_not_blocked_by_long(self):
        _,j=annotate(report(),init_empty(),now_ms=NOW)
        _,reversed_log=annotate(report(direction="SHORT"),j,now_ms=NOW+1000)
        self.assertEqual(len(fresh_events(reversed_log)),1)
    def test_rejects_nonresearch_and_malformed_event(self):
        _,j=annotate(report(),init_empty(),now_ms=NOW)
        j["notTradeApproval"]=False
        with self.assertRaises(ValueError):fresh_events(j)
        _,j=annotate(report(),init_empty(),now_ms=NOW)
        j["events"][-1]["firstDetectedAtMadrid"]=None
        self.assertEqual(fresh_events(j),[])

if __name__=="__main__":
    unittest.main()
