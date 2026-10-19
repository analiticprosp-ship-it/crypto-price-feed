#!/usr/bin/env python3
"""Tests for OI magnitude research, fixed four-way controls and chronological splits."""
import math
import unittest

from research.detector_tardis_price_oi_chrono_ablation import DAYS,SYMBOLS,HORIZONS,BASE_FIELDS,OI_FIELD
from research.detector_tardis_oi_abs_return_magnitude import (
    MAG_FEATURES,MAG_OI_FEATURE,MODELS,magnitude_rows,fit_fixed_ridge,
    predict,measures,compare,summarize
)


def fake_input():
    rows={};references=[]
    for h in HORIZONS:
        data=[]
        for day in DAYS:
            for sym in SYMBOLS:
                for i in range(16):
                    outcome=.01 if i%4 in (0,1) else -.005
                    data.append({"day":day,"symbol":sym,"minute_index":i,
                         "forward_return":outcome,
                         BASE_FIELDS[0]:.0001*i,
                         BASE_FIELDS[1]:.0008*(i%5),
                         OI_FIELD:.0003*i})
        rows[h]=data
        for day in DAYS[1:]:
            for sym in SYMBOLS:
                references.append({"horizon_min":h,"test_day":day,
                    "symbol":sym,"n":16})
    return rows,{"holdout_blocks":references}


class MagnitudeControls(unittest.TestCase):
    def test_log_magnitude_has_no_direction_sign(self):
        rows=[{"day":"2024-01-01","symbol":"BTCUSDT","minute_index":12,
           "forward_return":-.01,BASE_FIELDS[0]:-.002,
           BASE_FIELDS[1]:.003,OI_FIELD:-.01}]
        result=magnitude_rows(rows)[0]
        self.assertAlmostEqual(result["target"],abs(math.log(.99)))
        self.assertEqual(result[MAG_OI_FEATURE],.01)
        self.assertEqual(result[MAG_FEATURES[0]],.002)
    def test_invalid_return_below_minus_100_percent_fails(self):
        rows,ref=fake_input()
        rows[15][0]["forward_return"]=-1
        with self.assertRaisesRegex(ValueError,"INVALID_FUTURE_RETURN"):
            magnitude_rows(rows[15])
    def test_negative_forecast_clipped(self):
        model={"fields":("v",),"x_mean":[0],"x_scale":[1],
          "weights":[-5],"bias":0,"y_mean":0.1,"y_scale":1}
        self.assertEqual(predict(model,{"v":100}),0)
    def test_fitted_linear_training_only(self):
        data=magnitude_rows(fake_input()[0][15][:40])
        model=fit_fixed_ridge(data,MAG_FEATURES)
        self.assertEqual(model["fields"],MAG_FEATURES)
        p=predict(model,data[0])
        self.assertGreaterEqual(p,0)
        self.assertGreaterEqual(measures(data,[p]*len(data))["mae"],0)
    def test_all_models_identical_chrono_holdout_counts(self):
        rows,ref=fake_input()
        blocks=compare(rows,ref)
        self.assertEqual(len(blocks),18)
        for record in blocks:
            self.assertNotIn(record["test_day"],record["train_days"])
            self.assertEqual(record["n"],16)
            self.assertEqual(set(record["metrics"]),set(MODELS))
            self.assertEqual(record["metrics"]["zero"]["n"],16)
        totals=summarize(blocks)
        for h in HORIZONS:
            self.assertEqual(totals[f"{h}m"]["holdout_points"],144)
            self.assertEqual(totals[f"{h}m"]["holdout_calendar_days"],3)
    def test_reference_count_change_fails_closed(self):
        rows,ref=fake_input()
        ref["holdout_blocks"][0]["n"]+=1
        with self.assertRaisesRegex(ValueError,"HOLDOUT_SET_CHANGED"):
            compare(rows,ref)
    def test_metric_empty_and_nan_predictions_rejected(self):
        with self.assertRaisesRegex(ValueError,"EVAL_EMPTY"):
            measures([],[])
        with self.assertRaisesRegex(ValueError,"INVALID_PREDICTED_MAGNITUDE"):
            measures([{"target":1}],[float("nan")])

if __name__=="__main__":unittest.main()
