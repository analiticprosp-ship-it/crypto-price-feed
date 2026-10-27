#!/usr/bin/env python3
"""Read-only historical diagnostics and fail-closed registration tests. No production writes."""
import copy,datetime as dt,json,math,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import register_model_a as reg
from score_frozen_model import load_model,score_a
H=3600000
def expect_failure(fn,needle):
    try:fn()
    except (RuntimeError,AssertionError) as e:
        assert needle in str(e),(needle,str(e))
    else:raise AssertionError("EXPECTED_FAILURE_NOT_RAISED: "+needle)
model,sha=load_model()
state=json.loads((ROOT/"data/detector_state.json").read_text())
data=json.loads((ROOT/"data/btc_spot_1h.json").read_text())
index={r[0]:r for r in data["candles"]}
history=[]
for e in state["accepted"]:
    if e["classification"]!="RETROSPECTIVE_CONTEXT_NOT_OOS":continue
    assert e["checkpoint_status"]=="72H_SURVIVOR"
    assert e["low_open_ms"]+72*H in index
    rec=(float(index[e["low_open_ms"]+72*H][4])-e["L"])/(e["H"]-e["L"])
    assert math.isclose(rec,e["rec"],abs_tol=1e-10)
    history.append({"event_id":e["id"],"classification":"RETROSPECTIVE_DIAGNOSTIC_NOT_OOS",
      "model_a":score_a(model,e["drop"],rec)})
assert len(history)==3
with tempfile.TemporaryDirectory() as td:
    tmp=Path(td);(tmp/"data").mkdir()
    (tmp/"data/detector_state.json").write_text(json.dumps({"accepted":state["accepted"]}))
    (tmp/"data/btc_spot_1h.json").write_text(json.dumps(data))
    with patch.object(reg,"ROOT",tmp):
        reg.main()
        assert not (tmp/"forecasts").exists(),"HISTORICAL_FORECAST_WRITTEN"
        ev=copy.deepcopy(state["accepted"][-1])
        ev["classification"]="PROSPECTIVE_CANDIDATE"
        ev["registered_at_utc"]=dt.datetime.fromtimestamp((ev["signal_open_ms"]+H)/1000,dt.timezone.utc).isoformat()
        ev["checkpoint_observed_at_utc"]=ev["checkpoint_known_at_utc"]
        ev["id"]="synthetic-prospective-validation"
        (tmp/"data/detector_state.json").write_text(json.dumps({"accepted":[ev]}))
        reg.main()
        path=tmp/"forecasts"/(ev["id"]+".model-a.json")
        assert path.exists()
        snap=json.loads(path.read_text())
        assert snap["model_sha256"]==sha and len(snap["horizons"])==3
        reg.main()
        assert len(list((tmp/"forecasts").glob("*.json")))==1
        changed=copy.deepcopy(ev);changed["drop"]+=0.001
        (tmp/"data/detector_state.json").write_text(json.dumps({"accepted":[changed]}))
        expect_failure(reg.main,"IMMUTABLE_FORECAST_CONFLICT")
        path.unlink()
        bad=copy.deepcopy(ev);bad["checkpoint_observed_at_utc"]=dt.datetime.fromtimestamp((bad["low_open_ms"]+72*H)/1000,dt.timezone.utc).isoformat()
        (tmp/"data/detector_state.json").write_text(json.dumps({"accepted":[bad]}))
        expect_failure(reg.main,"CHECKPOINT_FUTURE_LEAK")
        late=copy.deepcopy(ev);late["registered_at_utc"]=dt.datetime.fromtimestamp((late["signal_open_ms"]+3*H)/1000,dt.timezone.utc).isoformat()
        (tmp/"data/detector_state.json").write_text(json.dumps({"accepted":[late]}))
        reg.main();assert not path.exists()
        gap=copy.deepcopy(data);gap["candles"]=[r for r in data["candles"] if r[0]!=ev["low_open_ms"]+36*H]
        (tmp/"data/btc_spot_1h.json").write_text(json.dumps(gap))
        (tmp/"data/detector_state.json").write_text(json.dumps({"accepted":[ev]}))
        expect_failure(reg.main,"CHECKPOINT_CANDLES_MISSING")
print(json.dumps({"status":"ISOLATED_TEST_PASS","historical_cases":history,
"tests":["retrospective_exclusion","synthetic_checkpoint","three_horizons","idempotency","immutable_conflict","future_leak","late_candidate","missing_candle"],
"production_state_changed":False,"trades":"NONE"},indent=2))
