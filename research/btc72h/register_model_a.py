#!/usr/bin/env python3
"""Register immutable prospective-only model A checkpoint forecasts. Research only."""
import datetime as dt
import hashlib
import json
from pathlib import Path
from score_frozen_model import load_model, score_a
ROOT=Path(__file__).resolve().parent
HOUR=3600000
def main():
    model,sha=load_model()
    state=json.loads((ROOT/"data"/"detector_state.json").read_text())
    candles=json.loads((ROOT/"data"/"btc_spot_1h.json").read_text())
    index={r[0]:r for r in candles["candles"]}
    out=ROOT/"forecasts"
    made=0
    for ev in state["accepted"]:
        if ev["classification"]!="PROSPECTIVE_CANDIDATE":continue
        if ev["checkpoint_status"]!="72H_SURVIVOR":continue
        j=ev["low_open_ms"]
        checkpoint_ms=j+73*HOUR
        registered=ev.get("registered_at_utc")
        if not registered:raise RuntimeError("UNREGISTERED_PROSPECTIVE_CANDIDATE")
        registered_ms=int(dt.datetime.fromisoformat(registered).timestamp()*1000)
        if registered_ms>ev["signal_open_ms"]+2*HOUR:
            continue # delayed candidate; not valid prospective OOS
        observed=ev.get("checkpoint_observed_at_utc")
        if not observed:raise RuntimeError("CHECKPOINT_OBSERVATION_MISSING")
        observed_ms=int(dt.datetime.fromisoformat(observed).timestamp()*1000)
        if observed_ms<checkpoint_ms:raise RuntimeError("CHECKPOINT_FUTURE_LEAK")
        if observed_ms>checkpoint_ms+HOUR:
            continue # delayed checkpoint; never backfill as prospective OOS
        if any(j+n*HOUR not in index for n in range(1,73)):
            raise RuntimeError("CHECKPOINT_CANDLES_MISSING")
        if min(float(index[j+n*HOUR][3]) for n in range(1,73))<ev["L"]:
            raise RuntimeError("SURVIVOR_MISMATCH")
        rec=(float(index[j+72*HOUR][4])-ev["L"])/(ev["H"]-ev["L"])
        if abs(rec-ev["rec"])>1e-10:raise RuntimeError("REC_MISMATCH")
        scores=score_a(model,ev["drop"],rec)
        snapshot={"schema":"BTC72H_MODEL_A_PROSPECTIVE_FORECAST_v1",
          "event_id":ev["id"],"classification":"PROSPECTIVE_OOS",
          "candidate_registered_at_utc":registered,
          "checkpoint_known_at_utc":ev["checkpoint_known_at_utc"],
          "checkpoint_observed_at_utc":observed,
          "model_sha256":sha,"features":{"drop":ev["drop"],"rec":rec},
          "horizons":scores,"model_B":"UNKNOWN","model_C":"UNKNOWN",
          "outcome_label":"strict new low after checkpoint","status":"SHADOW_RESEARCH_ONLY_NO_TRADES"}
        path=out/(ev["id"]+".model-a.json")
        if path.exists():
            if json.loads(path.read_text())!=snapshot:raise RuntimeError("IMMUTABLE_FORECAST_CONFLICT: "+ev["id"])
            continue
        out.mkdir(exist_ok=True)
        with path.open("x") as f:json.dump(snapshot,f,indent=2);f.write("\n")
        made+=1
    print(json.dumps({"status":"SHADOW_RESEARCH_ONLY","new_forecasts":made,
      "model_sha256":sha,"trades":"NONE","notifications":"DISABLED"}))
if __name__=="__main__":main()
