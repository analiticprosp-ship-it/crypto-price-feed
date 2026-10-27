#!/usr/bin/env python3
"""BTC72H research-only candidate detector. No orders, no predictions, no notifications.
The first run establishes a prospective watermark; earlier candidates are context only.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"/"btc_spot_1h.json"
STATE=ROOT/"data"/"detector_state.json"
HOUR=3600000
FREEZE=dt.datetime(2026,10,13,tzinfo=dt.timezone.utc).timestamp()*1000

def utc(ms):
    return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).isoformat()
def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def write_new(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x") as f: json.dump(obj,f,indent=2,ensure_ascii=False);f.write("\n")

def main():
    payload=json.loads(DATA.read_text())
    assert payload["source"]=="https://data-api.binance.vision" and payload["symbol"]=="BTCUSDT"
    rows=payload["candles"]
    if len(rows)<70 or any(rows[k][0]-rows[k-1][0]!=HOUR for k in range(1,len(rows))):
        raise RuntimeError("DATA_UNAVAILABLE: discontinuous candle history")
    now=dt.datetime.now(dt.timezone.utc)
    if rows[-1][6]>=int(now.timestamp()*1000): raise RuntimeError("UNCLOSED_CANDLE")
    state=json.loads(STATE.read_text()) if STATE.exists() else None
    if state is None:
        state={"schema":"BTC72H_DETECTOR_STATE_v1","activated_at_utc":now.isoformat(),
               "activation_last_closed_open_ms":rows[-1][0],
               "last_scanned_open_ms":rows[0][0]+65*HOUR-HOUR,
               "accepted":[],"last_run_utc":None}
    if rows[0][0]>state["last_scanned_open_ms"]+HOUR:
        raise RuntimeError("DATA_UNAVAILABLE: missing history before scan watermark")
    index={r[0]:k for k,r in enumerate(rows)}
    start=max(66,(state["last_scanned_open_ms"]-rows[0][0])//HOUR+1)
    accepted=state["accepted"]
    for i in range(start,len(rows)):
        j=min(range(i-18,i-2),key=lambda k:float(rows[k][3]))
        low=float(rows[j][3])
        high=max(float(rows[k][2]) for k in range(j-48,j))
        close=float(rows[i][4])
        if high<=0 or (high-low)/high<.05 or (close-low)/low<.02: continue
        if (close-low)/(high-low)>=.8: continue
        if any(float(rows[k][3])<low for k in range(j+1,i+1)): continue
        if sum(float(rows[k][4])>float(rows[k][1]) for k in range(j+1,i+1))<2: continue
        if accepted and rows[i][0]-accepted[-1]["signal_open_ms"]<168*HOUR: continue
        cluster_first=next((e for e in accepted if 0<=rows[j][0]-e["low_open_ms"]<30*24*HOUR),None)
        retrospective=rows[i][0]<=state["activation_last_closed_open_ms"] or rows[i][0]<FREEZE
        ev={"id":"btc72h-"+str(rows[i][0]),"signal_open_ms":rows[i][0],
            "signal_close_known_utc":utc(rows[i][0]+HOUR),
            "low_open_ms":rows[j][0],"low_open_utc":utc(rows[j][0]),
            "H":high,"L":low,"signal_close":close,
            "drop":(high-low)/high,
            "signal_recovery":(close-low)/(high-low),
            "first_in_30d_cluster":cluster_first is None,
            "cluster_first_id":cluster_first["id"] if cluster_first else None,
            "classification":"RETROSPECTIVE_CONTEXT_NOT_OOS" if retrospective else "PROSPECTIVE_CANDIDATE",
            "registered_at_utc":now.isoformat() if not retrospective else None,
            "source":payload["source"],"source_candle_hash":payload["sha256_candles"],
            "checkpoint_status":"PENDING","outcomes":{}}
        accepted.append(ev)
        if not retrospective:
            write_new(ROOT/"events"/(ev["id"]+".candidate.json"),ev)
    for ev in accepted:
        j=ev["low_open_ms"]
        if ev["checkpoint_status"]=="PENDING" and j+72*HOUR in index:
            k=index[j+72*HOUR]
            if all(j+n*HOUR in index for n in range(1,73)):
                lows=[float(rows[index[j+n*HOUR]][3]) for n in range(1,73)]
                survivor=min(lows)>=ev["L"]
                ev["checkpoint_status"]="72H_SURVIVOR" if survivor else "NOT_72H_SURVIVOR"
                ev["checkpoint_known_at_utc"]=utc(j+73*HOUR)
                ev["checkpoint_close"]=float(rows[k][4])
                ev["rec"]=(ev["checkpoint_close"]-ev["L"])/(ev["H"]-ev["L"])
                ev["checkpoint_observed_at_utc"]=now.isoformat()
                if ev["classification"]=="PROSPECTIVE_CANDIDATE":
                    write_new(ROOT/"events"/(ev["id"]+".72h.json"),
                              {**ev,"model_A":"NOT_SCORED","model_B":"UNKNOWN","model_C":"UNKNOWN",
                               "timeliness":"ON_TIME" if now.timestamp()*1000<=j+74*HOUR else "DELAYED",
                               "status":"SHADOW_RESEARCH_ONLY"})
        if ev["checkpoint_status"]!="72H_SURVIVOR": continue
        for days in (7,14,30):
            key=str(days)
            if key in ev["outcomes"]: continue
            start_ms=j+73*HOUR
            end_ms=start_ms+days*24*HOUR
            if rows[-1][0]+HOUR<end_ms: continue
            future=[rows[index[t]] for t in range(start_ms,end_ms,HOUR) if t in index]
            if len(future)!=days*24: continue
            result={"horizon_days":days,"low_broken":min(float(r[3]) for r in future)<ev["L"],
                    "checked_at_utc":now.isoformat(),"window_start_utc":utc(start_ms),
                    "window_end_utc":utc(end_ms)}
            ev["outcomes"][key]=result
            if ev["classification"]=="PROSPECTIVE_CANDIDATE":
                write_new(ROOT/"events"/(ev["id"]+"."+key+"d.json"),result)
    state["accepted"]=accepted
    state["last_scanned_open_ms"]=rows[-1][0]
    state["last_run_utc"]=now.isoformat()
    STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"status":"SHADOW_RESEARCH_ONLY","last_scanned":utc(rows[-1][0]),
       "accepted_total":len(accepted),"prospective_candidates":sum(e["classification"]=="PROSPECTIVE_CANDIDATE" for e in accepted),
       "72h_survivors":sum(e["checkpoint_status"]=="72H_SURVIVOR" for e in accepted),
       "notifications":"DISABLED_PENDING_AUDIT"},indent=2))
if __name__=="__main__": main()
