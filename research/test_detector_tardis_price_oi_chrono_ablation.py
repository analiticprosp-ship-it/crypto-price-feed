#!/usr/bin/env python3
"""Offline fail-closed tests: no future labels/features or future-day training."""
import csv,datetime as dt,io,unittest
from research.detector_tardis_price_oi_chrono_ablation import (
    DAYS,SYMBOLS,BASE_FIELDS,OI_FIELD,validate_and_build,
    fit_logistic,probability,evaluate,walkforward,summarize
)

SYM="BTCUSDT"
DAY="2024-01-01"
def iso(t):return t.isoformat()
def payload(day=DAY,sym=SYM,forged_future=False,wrong_label=False):
    start=dt.datetime.fromisoformat(day+"T00:00:00+00:00")
    f=[];l=[]
    for i in range(288):
        decision=start+dt.timedelta(minutes=5*(i+1),seconds=30)
        source=decision-dt.timedelta(seconds=2)
        if i==0 and forged_future:source=decision+dt.timedelta(microseconds=1)
        f.append({
            "day":day,"symbol":sym,"decision_time_utc":iso(decision),
            "oi_vendor_receipt_utc":iso(source),
            "last_price_vendor_receipt_utc":iso(decision-dt.timedelta(seconds=1)),
            "open_interest":"1000","last_price":"50000",
            "past_last_price_return_5m":".001" if i>0 else "",
            "past_last_price_return_60m":".01" if i>=12 else "",
            "oi_delta_5m":".002" if i>0 else "",
            "price_oi_feature_quality":"OK_VENDOR_ASOF"})
        row={"day":day,"symbol":sym,"decision_time_utc":iso(decision)}
        for h in (15,60):
            target=i+h//5
            row[f"label_{h}m_available_at_utc"]=(
                iso(start+dt.timedelta(minutes=5*(target+1),seconds=30)) if target<288 else "")
            row[f"future_last_price_return_{h}m"]=(
                ".002" if target<288 else "")
        if wrong_label and i==15:
            row["label_15m_available_at_utc"]=iso(decision)
        l.append(row)
    def serialize(rows):
        out=io.StringIO(newline="")
        w=csv.DictWriter(out,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        return out.getvalue().encode()
    return serialize(f),serialize(l)

class ChronoAblationSafety(unittest.TestCase):
    def test_first_of_day_missing_past_is_excluded(self):
        f,l=payload()
        used,skips=validate_and_build(f,l,DAY,SYM)
        self.assertEqual(len(used[15]),273)
        self.assertEqual(len(used[60]),264)
        self.assertEqual(used[15][0]["minute_index"],12)
        self.assertEqual(skips[15],15)\n        self.assertEqual(skips[60],24)
    def test_future_vendor_receipt_fails_closed(self):
        f,l=payload(forged_future=True)
        with self.assertRaisesRegex(ValueError,"FUTURE_VENDOR_RECEIPT"):
            validate_and_build(f,l,DAY,SYM)
    def test_non_forward_label_fails_closed(self):
        f,l=payload(wrong_label=True)
        with self.assertRaisesRegex(ValueError,"WRONG_FORWARD_LABEL"):
            validate_and_build(f,l,DAY,SYM)
    def test_label_cannot_appear_in_feature_csv(self):
        f,l=payload()
        rows=list(csv.DictReader(io.StringIO(f.decode())))
        for r in rows:r["future_last_price_return_15m"]="0.99"
        out=io.StringIO();w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        with self.assertRaisesRegex(ValueError,"FUTURE_TARGET_IN_FEATURE_FILE"):
            validate_and_build(out.getvalue().encode(),l,DAY,SYM)
    def test_training_only_normalization_and_predictions(self):
        base=[]
        for i in range(50):
            base.append({"past_last_price_return_5m":i/40,
                "past_last_price_return_60m":(i%7)/7,
                "oi_delta_5m":i/100,"y":int(i%2==0)})
        model=fit_logistic(base,BASE_FIELDS+(OI_FIELD,))
        self.assertEqual(len(model["means"]),3)
        self.assertGreater(probability(model,base[0]),0)
        self.assertLess(probability(model,base[0]),1)
        self.assertEqual(evaluate(model,base)["n"],50)
    def test_only_prior_calendar_days_in_training(self):
        data={}
        for h in (15,60):
            entries=[]
            for day in DAYS:
                for sym in SYMBOLS:
                    for i in range(16):
                        entries.append({"day":day,"symbol":sym,"minute_index":i,
                            BASE_FIELDS[0]:i*.001,BASE_FIELDS[1]:i*.004,
                            OI_FIELD:i*.002,"y":int(i%2==0),"forward_return":.01})
            data[h]=entries
        results=walkforward(data)
        self.assertEqual(len(results),18)
        for r in results:
            self.assertNotIn(r["test_day"],r["train_days"])
            self.assertTrue(all(day<r["test_day"] for day in r["train_days"]))
        self.assertEqual(summarize(results)["15m"]["holdout_days"],3)

if __name__=="__main__":unittest.main()
