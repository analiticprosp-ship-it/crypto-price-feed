#!/usr/bin/env python3
"""Fail-closed scoring of frozen BTC72H model A at 72h checkpoint.
Requires an exact byte-for-byte frozen model JSON and pinned SHA256.
No trading, no retraining, no retrospective OOS registration.
"""
import hashlib
import json
import math
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MODEL=ROOT/"frozen"/"BTC_72H_PROSPECTIVE_FROZEN_MODELS_v1_0_2026-10-13.json"
PIN=ROOT/"frozen"/"model.sha256"
def load_model():
    if not MODEL.exists() or not PIN.exists():
        raise RuntimeError("FROZEN_MODEL_MISSING: original bytes and pinned checksum required")
    raw=MODEL.read_bytes()
    expected=PIN.read_text().strip().split()[0].lower()
    actual=hashlib.sha256(raw).hexdigest()
    if actual!=expected: raise RuntimeError("FROZEN_MODEL_SHA256_MISMATCH")
    model=json.loads(raw)
    if model.get("frozen_at_utc")!="2026-10-13T00:04:40+00:00":
        raise RuntimeError("FROZEN_MODEL_IDENTITY_MISMATCH")
    return model,actual
def score_a(model,drop,rec):
    if not all(math.isfinite(x) for x in (drop,rec)):
        raise ValueError("INVALID_FEATURES")
    result={}
    for horizon in ("7","14","30"):
        entry=model["horizons"][horizon]
        a=entry["models"]["A_price"]
        if a["features"]!=["drop","rec"]: raise RuntimeError("FEATURE_SCHEMA_MISMATCH")
        if not all(len(a[k])==2 for k in ("scale_mean","scale","coef")):
            raise RuntimeError("MODEL_DIMENSIONS_MISMATCH")
        z=a["intercept"]+sum(w*(x-m)/s for x,m,s,w in zip((drop,rec),a["scale_mean"],a["scale"],a["coef"]))
        result[horizon]={"prob_break":1/(1+math.exp(-z)),"constant":entry["constant"]["p"]}
    return result
if __name__=="__main__":
    model,sha=load_model()
    print(json.dumps({"status":"MODEL_A_VALIDATED_NO_PREDICTIONS","model_sha256":sha,
                      "test":score_a(model,0.09237707785652123,0.6061577407044327),
                      "B":"UNKNOWN","C":"UNKNOWN"},indent=2))
