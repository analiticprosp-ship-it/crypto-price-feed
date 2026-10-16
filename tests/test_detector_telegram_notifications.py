"""Telegram notification opt-in contracts: no misleading historic, stale or duplicate pings."""
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_signal_events import add_signal_events,empty_ledger
from notify_detector_telegram import prepare_events,perform,empty_receipts,message_text

NOW=1800000000000
STEP=900000
def iso(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()
def report(now,end,side="LONG",asset="SOL"):
    return {"generatedAt":iso(now),"researchOnly":True,"notTradeApproval":True,
        "dataGate":{"ok":True},
        "sourceProvenance":{"marketSummaryGeneratedAt":iso(now-30000),
                            "takerRestGeneratedAt":iso(now-15000)},
        "candidates":[{"symbol":asset,"direction":side,"eventEndMs":end,
                       "status":"EARLY_CANDIDATE_SHADOW"}]}

def fresh_event():
    first,_=add_signal_events(report(NOW,NOW-STEP),empty_ledger())
    more,new=add_signal_events(report(NOW+STEP,NOW),first)
    return more,new[0],NOW+STEP

class TestTelegramNotifier(unittest.TestCase):
    def test_first_bootstrap_never_sends_historic(self):
        first,_=add_signal_events(report(NOW,NOW-STEP),empty_ledger())
        self.assertEqual(prepare_events(first,empty_receipts(),NOW),[])

    def test_new_candidates_get_bar_and_detect_times(self):
        ledger,new,at=fresh_event()
        pending=prepare_events(ledger,empty_receipts(),at+1000)
        self.assertEqual(len(pending),1)
        self.assertEqual(pending[0]["id"],new["id"])
        text=message_text(new,at+1000)
        self.assertIn("Свеча 15m закрыта:",text)
        self.assertIn("Обнаружено GitHub:",text)
        self.assertIn("Задержка до отправки:",text)
        self.assertIn("Не торговый сигнал",text)
        self.assertIn("15.0 мин",text)

    def test_delivery_receipt_prevents_duplicate(self):
        ledger,new,at=fresh_event()
        def send(s):
            return {"telegramMessageId":23,"telegramServerTimestampUtc":iso(at+2000),"telegramChatIdStored":False}
        r,delivered=perform(ledger,empty_receipts(),now_ms=at+1000,send=send)
        self.assertEqual(delivered,[new["id"]])
        self.assertEqual(prepare_events(ledger,r,at+120000),[])
        self.assertEqual(r["receipts"][0]["telegramMessageId"],23)

    def test_expired_no_trade_alerts(self):
        ledger,new,at=fresh_event()
        self.assertEqual(prepare_events(ledger,empty_receipts(),at+16*60000),[])
        self.assertEqual(prepare_events(ledger,empty_receipts(),at-1000),[])

    def test_malformed_receipts_or_status_are_rejected(self):
        ledger,new,at=fresh_event()
        with self.assertRaises(ValueError):
            prepare_events(ledger,{"schemaVersion":"invalid","receipts":[]},at)
        ledger["events"][-1]["notTradeApproval"]=False
        self.assertEqual(prepare_events(ledger,empty_receipts(),at),[])

    def test_no_successful_ack_on_sender_failure(self):
        ledger,new,at=fresh_event()
        def fail(s):raise ConnectionError("network outage")
        with self.assertRaises(ConnectionError):
            perform(ledger,empty_receipts(),now_ms=at,send=fail)

    def test_no_direct_execution_in_message(self):
        _,ev,now=fresh_event()
        m=message_text(ev,now)
        for s in ("entry=", "STOP_LOSS", "take_profit", "купить немедленно"):
            self.assertNotIn(s,m)

if __name__=="__main__":
    unittest.main()
