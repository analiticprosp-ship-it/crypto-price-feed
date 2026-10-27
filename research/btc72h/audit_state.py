#!/usr/bin/env python3
"""Fail-closed audit of BTC72H research state; never changes canonical books."""
import datetime as dt
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
H=3600000
def audit():
    data=json.loads((ROOT/"data/btc_spot_1h.json").read_text())
    state=json.loads((ROOT/"data/detector_state.json").read_text())
    rows=data["candles"]
    assert data["source"]=="https://data-api.binance.vision" and data["symbol"]=="BTCUSDT"
    assert len(rows)==data["count"] and len(rows)>=100
    assert all(rows[k][0]-rows[k-1][0]==H for k in range(1,len(rows)))
    assert all(r[6]==r[0]+H-1 and r[0]%H==0 for r in rows)
    assert rows[-1][0]==state["last_scanned_open_ms"]
    ids=set()
    last_signal=None
    last_cluster_low=None
    retrospective=0
    for ev in state["accepted"]:
        assert ev["id"] not in ids
        ids.add(ev["id"])
        assert ev["signal_open_ms"]>=ev["low_open_ms"]+3*H
        assert ev["signal_open_ms"]<=ev["low_open_ms"]+18*H
        if last_signal is not None:
            assert ev["signal_open_ms"]-last_signal>=168*H
        last_signal=ev["signal_open_ms"]
        expected_first=last_cluster_low is None or ev["low_open_ms"]-last_cluster_low>=30*24*H
        assert ev["first_in_30d_cluster"]==expected_first
        if expected_first: last_cluster_low=ev["low_open_ms"]
        if ev["classification"]=="RETROSPECTIVE_CONTEXT_NOT_OOS":
            retrospective+=1
            assert ev["registered_at_utc"] is None
        else:
            assert ev["classification"]=="PROSPECTIVE_CANDIDATE"
            assert ev["registered_at_utc"] and (ROOT/"events"/(ev["id"]+".candidate.json")).exists()
        if ev["checkpoint_status"]!="PENDING":
            assert ev["checkpoint_known_at_utc"]==dt.datetime.fromtimestamp((ev["low_open_ms"]+73*H)/1000,dt.timezone.utc).isoformat()
        for d,v in ev["outcomes"].items():
            assert d in ("7","14","30")
            assert v["horizon_days"]==int(d)
            assert v["window_start_utc"]==ev["checkpoint_known_at_utc"]
    print(json.dumps({"status":"AUDIT_PASS","candles":len(rows),"accepted":len(ids),"retrospective":retrospective,"prospective":len(ids)-retrospective,"notifications":"DISABLED"},indent=2))
if __name__=="__main__":audit()
