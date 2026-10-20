"""Offline proof tests: no self-disable PASS from deadline/config/disabled state alone."""
import unittest
from research.detector_h1h10_okx_pilot_expiry_audit import (
    CONFIGS, DURATION_MS, classify, validate_config
)
T = 1792480000000

def cfg(spec):
    return {"schema": spec["schema"], "research_only": True,
            "start_ms": T, "end_ms": T + DURATION_MS}


class IndependentExpiryTests(unittest.TestCase):
    def test_not_due_even_if_cron_happens_to_stop(self):
        for spec in CONFIGS.values():
            state=classify(T+1000, cfg(spec), "active")
            self.assertEqual(state["status"],"NOT_YET_DUE")
            self.assertFalse(state["self_disable_approved_as_actual"])

    def test_expired_active_remains_unverified(self):
        spec=CONFIGS["oi_only"]
        state=classify(T+DURATION_MS+1, cfg(spec), "active")
        self.assertEqual(state["status"],"EXPIRED_BUT_GITHUB_WORKFLOW_ACTIVE")
        self.assertFalse(state["self_disable_approved_as_actual"])

    def test_disabled_alone_cannot_claim_automatic_shutdown(self):
        spec=CONFIGS["oi_only"]
        state=classify(T+DURATION_MS+1, cfg(spec), "disabled_manually")
        self.assertEqual(state["status"],"DISABLED_OBSERVED_SELF_DISABLE_CAUSE_UNVERIFIED")
        self.assertFalse(state["self_disable_approved_as_actual"])

    def test_only_exact_stopped_log_plus_disabled_after_due_qualifies(self):
        spec=CONFIGS["oi_only"]
        state=classify(T+DURATION_MS+1, cfg(spec), "disabled_manually", True)
        self.assertEqual(state["status"],"SELF_DISABLE_VERIFIED_STOP_LOG_AND_DISABLED_STATE")
        self.assertTrue(state["self_disable_approved_as_actual"])
        self.assertEqual(state["causal_h1h10_rows_authorized"],0)

    def test_before_expiry_disabled_with_log_is_not_pass(self):
        spec=CONFIGS["oi_only"]
        state=classify(T+1000, cfg(spec), "disabled_manually", True)
        self.assertEqual(state["status"],"DISABLED_BEFORE_EXPIRY_UNEXPLAINED")
        self.assertFalse(state["self_disable_approved_as_actual"])

    def test_unknown_workflow_state_rejected(self):
        spec=CONFIGS["oi_price_flow"]
        with self.assertRaisesRegex(ValueError,"GITHUB_WORKFLOW_STATE_UNKNOWN"):
            classify(T+DURATION_MS+1,cfg(spec),"deleted")

    def test_wrong_duration_or_future_config_rejected(self):
        x=cfg(CONFIGS["oi_only"])
        x["end_ms"]+=1000
        with self.assertRaisesRegex(ValueError,"PILOT_EXPIRY_DURATION_OR_CLOCK_INVALID"):
            validate_config(x,CONFIGS["oi_only"]["schema"],T+DURATION_MS+1)
        x=cfg(CONFIGS["oi_only"])
        with self.assertRaisesRegex(ValueError,"PILOT_EXPIRY_DURATION_OR_CLOCK_INVALID"):
            validate_config(x,CONFIGS["oi_only"]["schema"],T-1000)

    def test_foreign_schema_or_non_research_rejected(self):
        x=cfg(CONFIGS["oi_price_flow"])
        with self.assertRaisesRegex(ValueError,"PILOT_EXPIRY_CONFIG_NOT_TRUSTED"):
            validate_config(x,CONFIGS["oi_only"]["schema"],T+DURATION_MS+1)
        x["research_only"]=False
        with self.assertRaisesRegex(ValueError,"PILOT_EXPIRY_CONFIG_NOT_TRUSTED"):
            validate_config(x,CONFIGS["oi_price_flow"]["schema"],T+DURATION_MS+1)

    def test_disabled_inactivity_not_equal_self_disable(self):
        s=classify(T+DURATION_MS+1,cfg(CONFIGS["oi_price_flow"]),"disabled_inactivity",True)
        self.assertFalse(s["self_disable_approved_as_actual"])
        self.assertEqual(s["status"],"DISABLED_OBSERVED_SELF_DISABLE_CAUSE_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
