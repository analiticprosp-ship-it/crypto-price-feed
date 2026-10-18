#!/usr/bin/env python3
"""Offline validation of null baselines and immutable historical model replay."""
import copy
import json
import unittest

from research.detector_tardis_price_oi_chrono_ablation import (
    DAYS, SYMBOLS, HORIZONS, BASE_FIELDS, OI_FIELD, walkforward
)
from research.detector_tardis_price_oi_null_controls import (
    MODELS, aggregate, constant_metrics, reproduce_with_controls, train_only_prior
)


def synthetic():
    sample={}
    for horizon in HORIZONS:
        rows=[]
        for day in DAYS:
            for symbol in SYMBOLS:
                for i in range(8):
                    rows.append({
                        "day":day,"symbol":symbol,"minute_index":i,
                        BASE_FIELDS[0]:.001*i,
                        BASE_FIELDS[1]:.002*(i%5),
                        OI_FIELD:.01*(i%3),
                        "y":int((i+(0 if symbol=="BTCUSDT" else 1))%2==0),
                        "forward_return":.002 if i%2==0 else -.002
                    })
        sample[horizon]=rows
    return sample


class NullControls(unittest.TestCase):
    def test_half_has_exact_quarter_brier_even_with_class_imbalance(self):
        rows=[{"y":1},{"y":1},{"y":1},{"y":0}]
        metrics=constant_metrics(rows,.5)
        self.assertEqual(metrics["brier"],.25)
        self.assertAlmostEqual(metrics["logloss"],.69314718,places=8)

    def test_training_only_prior_laplace_fixed(self):
        train=[{"y":1},{"y":1},{"y":0}]
        self.assertEqual(train_only_prior(train),3/5)

    def test_prior_invariant_to_holdout_labels(self):
        train=[{"y":1},{"y":0},{"y":1}]
        left=[{"y":0}]*40
        right=[{"y":1}]*40
        p=train_only_prior(train)
        self.assertEqual(p,train_only_prior(train))
        self.assertNotEqual(constant_metrics(left,p)["brier"],
                            constant_metrics(right,p)["brier"])

    def test_empty_training_or_invalid_forecast_refused(self):
        with self.assertRaisesRegex(ValueError,"EMPTY_TRAIN"):
            train_only_prior([])
        with self.assertRaisesRegex(ValueError,"INVALID_FORECAST"):
            constant_metrics([{"y":0}],1)
        with self.assertRaisesRegex(ValueError,"INVALID_TEST_BINARY"):
            constant_metrics([{"y":2}],.5)

    def test_replay_does_not_change_old_models_or_splits(self):
        samples=synthetic()
        old=walkforward(samples)
        blocks=reproduce_with_controls(samples,json.loads(json.dumps(old)))
        self.assertEqual(len(blocks),18)
        for block in blocks:
            self.assertNotIn(block["test_day"],block["train_days"])
            self.assertEqual(block["models"]["fixed_half"]["brier"],.25)
            self.assertEqual(block["train_n"],len(block["train_days"])*len(SYMBOLS)*8)

    def test_detect_any_prior_metric_change(self):
        samples=synthetic()
        old=walkforward(samples)
        old[0]["baseline"]["brier"]+=.0001
        with self.assertRaisesRegex(ValueError,"PREVIOUS_MODEL_METRIC_REPLAY_MISMATCH"):
            reproduce_with_controls(samples,old)

    def test_aggregation_preserves_independent_days(self):
        samples=synthetic()
        blocks=reproduce_with_controls(samples,walkforward(samples))
        summary=aggregate(blocks)
        for horizon in HORIZONS:
            x=summary[f"{horizon}m"]
            self.assertEqual(x["holdout_days"],3)
            self.assertEqual(x["holdout_points"],3*len(SYMBOLS)*8)
            self.assertEqual(set(x["weighted_brier"]),set(MODELS))
            self.assertEqual(x["weighted_brier"]["fixed_half"],.25)
            self.assertEqual(set(x["calendar_day_counts"]),set(DAYS[1:]))

if __name__=="__main__":
    unittest.main()
