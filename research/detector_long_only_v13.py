#!/usr/bin/env python3
"""LONG-only SHADOW validation; independent of live Detector/Futures. No short strategies."""
import argparse,csv,json,datetime as dt
from pathlib import Path
from collections import defaultdict
from detector_entry_window_v01 import getbars,ms,iso
import requests
p=argparse.ArgumentParser();p.add_argument("--out",default="detector_long_only_v13_results");a=p.parse_args()
out=Path(a.out);out.mkdir(exist_ok=True)
raw=json.loads(Path("detector-signal-events.json").read_text())
events=[e for e in raw["events"] if e.get("status")=="EARLY_CANDIDATE_SHADOW" and e.get("direction")=="LONG"]
now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
session=requests.Session();session.headers["User-Agent"]="detector-long-only-shadow/1.0"
cache={};errors={}
for sym in sorted({e["symbol"] for e in events}):
    try:cache[sym]=getbars(session,sym,min(ms(e["firstDetectedAtUtc"]) for e in events if e["symbol"]==sym)-300000,now)
    except Exception as ex:cache[sym]=[];errors[sym]=str(ex)
trials=[];hold=[]
for e in events:
    bars=cache[e["symbol"]];det=ms(e["firstDetectedAtUtc"])
    i=next((j for j,b in enumerate(bars) if b[0]>=det and b[0]+300000<=now),None)
    if i is None:continue
    reference=bars[i][1]
    for method,param in [("IMMEDIATE",0),("DELAY_60",60),("PULLBACK_CLOSE_0_5",.5)]:
        entry=None
        if method=="IMMEDIATE":entry=i
        elif method=="DELAY_60":entry=next((j for j,b in enumerate(bars) if b[0]>=det+3600000),None)
        else:
            for j in range(i,len(bars)-1):
                b=bars[j]
                if b[0]+300000>det+240*60000:break
                if 100*(b[4]/reference-1)<=-.5:
                    if bars[j+1][0]==b[0]+300000:entry=j+1
                    break
        for horizon in (60,120,240):
            base={"event_id":e["id"],"symbol":e["symbol"],"direction":"LONG","detected_utc":e["firstDetectedAtUtc"],
                  "method":method,"horizon_min":horizon,"target_pct":1,"stop_pct":1,
                  "full_window":now>=det+horizon*60000}
            if entry is None or bars[entry][0]+300000>min(now,det+horizon*60000):
                trials.append(dict(base,status="NO_ENTRY"));continue
            ep=bars[entry][1];end=det+horizon*60000
            follow=[b for b in bars[entry:] if b[0]+300000<=min(end,now)]
            outcome="NO_TOUCH"
            for b in follow:
                t=b[2]>=ep*1.01;s=b[3]<=ep*.99
                if t and s:outcome="AMBIGUOUS";break
                if s:outcome="STOP_FIRST";break
                if t:outcome="TARGET_FIRST";break
            trials.append(dict(base,status="COMPLETE" if now>=end else "RIGHT_CENSORED",outcome=outcome,
                               entry_utc=iso(bars[entry][0]),entry_delay_min=round((bars[entry][0]-det)/60000,2)))
    # Descriptive spot buy-and-hold recovery from first observed open, not a trading guarantee.
    for horizon in (4,24,168,720):
        end=bars[i][0]+horizon*3600000
        observed=[b for b in bars[i:] if b[0]+300000<=min(end,now)]
        if not observed:continue
        full=now>=end
        last=observed[-1]
        hold.append({"event_id":e["id"],"symbol":e["symbol"],"hours":horizon,"complete":full,
          "end_return_pct":round(100*(last[4]/reference-1),4),
          "max_drawdown_pct":round(100*(min(b[3] for b in observed)/reference-1),4),
          "ever_up_1pct":any(b[2]>=reference*1.01 for b in observed),
          "ever_up_2pct":any(b[2]>=reference*1.02 for b in observed)})
def write(name,rows):
    if not rows:return
    fields=sorted(set().union(*(r.keys() for r in rows)))
    with (out/name).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
write("long_entry_trials.csv",trials);write("long_hold_descriptive.csv",hold)
groups=defaultdict(list)
for r in trials:
    if r["full_window"]:groups[(r["symbol"],r["method"],r["horizon_min"])].append(r)
summary=[]
for (sym,method,h),rr in sorted(groups.items()):
    summary.append({"symbol":sym,"method":method,"horizon_min":h,"events":len(rr),
      "entered":sum(r["status"]=="COMPLETE" for r in rr),
      "target_first":sum(r.get("outcome")=="TARGET_FIRST" for r in rr),
      "stop_first":sum(r.get("outcome")=="STOP_FIRST" for r in rr),
      "no_entry":sum(r["status"]=="NO_ENTRY" for r in rr)})
write("long_coin_summary.csv",summary)
manifest={"status":"SHADOW_RESEARCH_ONLY","policy":"LONG_ONLY_SPOT_NO_LEVERAGE","real_long_events":len(events),
 "unique_dates":sorted({e["firstDetectedAtUtc"][:10] for e in events}),"errors":errors,
 "limitations":["Only existing real GitHub LONG events, no reconstructed detection","5m SWAP OHLC used as market movement proxy, not spot execution prices","Long hold 7d/30d requires elapsed time; incomplete periods must never be scored as full","No claim of guaranteed recovery or profit","No commissions, slippage or actual alert delivery","No short trades or changes to live Detector/Futures"]}
(out/"manifest.json").write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
