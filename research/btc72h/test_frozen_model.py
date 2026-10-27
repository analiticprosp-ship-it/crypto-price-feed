#!/usr/bin/env python3
"""Isolated read-only frozen model A validation. No writes, no alerts."""
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from score_frozen_model import load_model,score_a
def close(a,b):
    assert math.isclose(a,b,rel_tol=0,abs_tol=1e-12),(a,b)
model,sha=load_model()
assert sha=="4fafcda54970c6d5d8dcc3d67c20a66da68fa0781095b742aefea44d5e6b66ee"
assert model["status"]=="SHADOW_RESEARCH_ONLY_NO_TRADES"
assert model["frozen_at_utc"]=="2026-10-13T00:04:40+00:00"
mean=[0.09237707785652123,0.6061577407044327]
result=score_a(model,*mean)
for horizon in ("7","14","30"):
    a=model["horizons"][horizon]["models"]["A_price"]
    expected=1/(1+math.exp(-a["intercept"]))
    close(result[horizon]["prob_break"],expected)
    close(result[horizon]["constant"],model["horizons"][horizon]["constant"]["p"])
assert all(0<r["prob_break"]<1 for r in result.values())
for invalid in (float("nan"),float("inf")):
    try: score_a(model,invalid,mean[1])
    except ValueError: pass
    else: raise AssertionError("INVALID_FEATURE_ACCEPTED")
with patch("score_frozen_model.PIN",ROOT/"nonexistent_pin.sha256"):
    try:load_model()
    except RuntimeError as exc:assert "FROZEN_MODEL_MISSING" in str(exc)
    else:raise AssertionError("MISSING_PIN_ACCEPTED")
state_path=ROOT/"data"/"detector_state.json"
if state_path.exists():
    state=json.loads(state_path.read_text())
    for event in state["accepted"]:
        if event["classification"]=="RETROSPECTIVE_CONTEXT_NOT_OOS":
            assert event["registered_at_utc"] is None
    assert not any(e["classification"]=="PROSPECTIVE_CANDIDATE" and not e.get("registered_at_utc") for e in state["accepted"])
print(json.dumps({"status":"MODEL_A_READ_ONLY_TEST_PASS","model_sha256":sha,
"reference_probabilities":{k:round(v["prob_break"],10) for k,v in result.items()},
"retrospective_oos_separation":"CHECKED","alerts":"DISABLED","trades":"NONE"},indent=2))
