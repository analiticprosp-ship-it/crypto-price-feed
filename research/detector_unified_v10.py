#!/usr/bin/env python3
"""SHADOW unified evaluation: exact real detector events; paired strategies; no backfilled detection."""
import argparse,csv,datetime as dt,json,math,time
from collections import defaultdict
from pathlib import Path
import requests
from detector_entry_window_v01 import getbars,ms,iso
UTC=dt.timezone.utc
p=argparse.ArgumentParser();p.add_argument("--out",default="detector_unified_v10_results");p.add_argument("--date",default="2026-10-16");a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
events=[e for e in json.loads(Path("detector-signal-events.json").read_text())["events"] if e["status"]=="EARLY_CANDIDATE_SHADOW" and e["direction"] in ("LONG","SHORT") and e["firstDetectedAtUtc"].startswith(a.date)]
cutoff=int(dt.datetime.now(UTC).timestamp()*1000)
start=min((ms(e["firstDetectedAtUtc"]) for e in events),default=cutoff)-600000
session=requests.Session();session.headers["User-Agent"]="detector-unified-shadow/1.0"
cache={};errors={}
for sym in sorted({e["symbol"] for e in events}):
    try:cache[sym]=getbars(session,sym,start,cutoff);print(sym,len(cache[sym]),flush=True)
    except Exception as exc:errors[sym]=str(exc);cache[sym]=[]
rows=[];paths=[]
for e in events:
    sym=e["symbol"];bars=cache[sym];det=ms(e["firstDetectedAtUtc"]);sgn=1 if e["direction"]=="LONG" else -1
    # The exact same post-detection deadline applies to every entry method.
    for horizon in (60,120,240):
        deadline=det+horizon*60000
        for strategy,parameter in [("IMMEDIATE",0),("DELAY",20),("DELAY",30),("DELAY",60),("PULLBACK_CLOSE",.25),("PULLBACK_CLOSE",.5),("PULLBACK_CLOSE",.75),("PULLBACK_CLOSE",1)]:
            baseline=next((i for i,b in enumerate(bars) if b[0]>=det and b[0]+300000<=cutoff),None)
            base={"event_id":e["id"],"symbol":sym,"direction":e["direction"],"first_detected_utc":e["firstDetectedAtUtc"],"signal_bar_closed_utc":e["barClosedAtUtc"],"horizon_min":horizon,"strategy":strategy,"parameter":parameter,"deadline_utc":iso(deadline),"fully_observed":cutoff>=deadline}
            if baseline is None:rows.append(dict(base,status="NO_BASELINE"));continue
            idx=None
            if strategy=="IMMEDIATE":idx=baseline
            elif strategy=="DELAY":
                idx=next((i for i,b in enumerate(bars) if b[0]>=det+parameter*60000 and b[0]+300000<=cutoff),None)
            else:
                reference=bars[baseline][1]
                # Completed bar CLOSE triggers a pullback, next 5m OPEN enters.
                for i in range(baseline,len(bars)-1):
                    b=bars[i]
                    if b[0]+300000>min(deadline,cutoff):break
                    if 100*sgn*(b[4]/reference-1)<=-parameter:
                        if bars[i+1][0]==b[0]+300000:idx=i+1
                        break
            if idx is None:rows.append(dict(base,status="NO_ENTRY"));continue
            entry=bars[idx];ep=entry[1]
            if entry[0]+300000>min(deadline,cutoff):rows.append(dict(base,status="ENTRY_TOO_LATE"));continue
            subset=[b for b in bars[idx:] if b[0]+300000<=min(deadline,cutoff)]
            if not subset:rows.append(dict(base,status="NO_POST_ENTRY_BARS"));continue
            for target,stop in ((1,.5),(1,1),(2,1)):
                outcome="NO_TOUCH";first=None
                for b in subset:
                    fav=100*sgn*((b[2] if sgn==1 else b[3])/ep-1)
                    adv=100*(-sgn)*((b[3] if sgn==1 else b[2])/ep-1)
                    if fav>=target and adv>=stop:outcome="AMBIGUOUS";first=b;break
                    if adv>=stop:outcome="STOP_FIRST";first=b;break
                    if fav>=target:outcome="TARGET_FIRST";first=b;break
                rows.append(dict(base,status="COMPLETE" if cutoff>=deadline else "RIGHT_CENSORED",
                  entry_utc=iso(entry[0]),entry_delay_min=round((entry[0]-det)/60000,2),
                  target_pct=target,stop_pct=stop,outcome=outcome,
                  first_touch_min=round((first[0]+300000-entry[0])/60000,2) if first else None,
                  max_favorable_pct=round(max(100*sgn*((b[2] if sgn==1 else b[3])/ep-1) for b in subset),5),
                  max_adverse_pct=round(max(100*(-sgn)*((b[3] if sgn==1 else b[2])/ep-1) for b in subset),5)))
    if baseline is not None:
        origin=bars[baseline][0];ref=bars[baseline][1]
        for b in bars[baseline:]:
            if b[0]+300000>min(det+240*60000,cutoff):break
            paths.append({"event_id":e["id"],"symbol":sym,"direction":e["direction"],"minute_since_first_observed_bar":int((b[0]-origin)/60000),
              "open_signed_pct":round(100*sgn*(b[1]/ref-1),5),"close_signed_pct":round(100*sgn*(b[4]/ref-1),5),
              "favorable_extreme_pct":round(100*sgn*((b[2] if sgn==1 else b[3])/ref-1),5),
              "adverse_extreme_pct":round(100*(-sgn)*((b[3] if sgn==1 else b[2])/ref-1),5)})
def write(name,data):
    if not data:return
    fields=sorted({k for x in data for k in x})
    with (out/name).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
write("paired_trials.csv",rows);write("signed_paths_5m.csv",paths)
# Summaries retain NO_ENTRY as failures to participate, and censor incomplete event horizons.
groups=defaultdict(list)
for r in rows:
    if r.get("fully_observed") and r.get("target_pct")==1 and r.get("stop_pct")==1 and r.get("status")=="COMPLETE":
        groups[(r["horizon_min"],r["strategy"],r["parameter"])].append(r)
summ=[]
for key,rr in groups.items():
    summ.append(dict(horizon_min=key[0],strategy=key[1],parameter=key[2],entries=len(rr),
      target_first=sum(x["outcome"]=="TARGET_FIRST" for x in rr),
      stop_first=sum(x["outcome"]=="STOP_FIRST" for x in rr),
      ambiguous=sum(x["outcome"]=="AMBIGUOUS" for x in rr),
      no_touch=sum(x["outcome"]=="NO_TOUCH" for x in rr)))
write("descriptive_summary.csv",summ)
(out/"manifest.json").write_text(json.dumps({"status":"SHADOW_RESEARCH_ONLY","events":len(events),"rows":len(rows),"paths":len(paths),"errors":errors,"generated_utc":iso(cutoff),
"limitations":["Same real detector events and same detection-anchored deadlines across strategies",
"Historical Swing v0.9 signals are NOT joined to detector events; different event universes",
"No historical first-detection timestamps for reconstructed Swing events",
"Entry is next 5m open after completed close for pullback, not guaranteed executable price",
"Same 5m candle stop+target = AMBIGUOUS, never credited as win",
"No entry is not a loss, but excluded entries must be reported",
"Repeated correlated events and same-day results are not independent holdout",
"No OI/funding, commissions, spread, slippage or actual notification delivery",
"No trading or limits changes"]},indent=2))
print("EVENTS",len(events),"TRIALS",len(rows),"ERRORS",errors)
