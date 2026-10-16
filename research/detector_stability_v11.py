#!/usr/bin/env python3
"""SHADOW stability report on paired real detector events. No synthetic event timestamps."""
import argparse,csv,json,math,subprocess,sys
from collections import defaultdict
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--input",default="detector_unified_v10_results/paired_trials.csv");p.add_argument("--out",default="detector_stability_v11_results");a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
with open(a.input,newline="") as f: data=list(csv.DictReader(f))
def write(name,rows):
    if not rows:return
    keys=sorted(set().union(*(r.keys() for r in rows)))
    with (out/name).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def wilson(w,n):
    if not n:return (None,None)
    z=1.96;v=w/n;d=1+z*z/n;c=(v+z*z/(2*n))/d;h=z*math.sqrt(v*(1-v)/n+z*z/(4*n*n))/d
    return round(max(0,c-h),4),round(min(1,c+h),4)
# Original unified trials duplicate NO_ENTRY for target/stop combinations; deduplicate by event.
all_events={(r["event_id"],r["symbol"],r["direction"]) for r in data}
rows=[r for r in data if r.get("horizon_min")=="240" and r.get("fully_observed")=="True"]
event_keys={(r["event_id"],r["symbol"],r["direction"]) for r in rows}
strategies=[("IMMEDIATE","0"),("DELAY","60"),("PULLBACK_CLOSE","0.5")]
paired=[];groups=defaultdict(list)
for eid,sym,direction in sorted(event_keys):
    for strategy,param in strategies:
        matching=[r for r in rows if r["event_id"]==eid and r["strategy"]==strategy and float(r["parameter"])==float(param)]
        matches=[r for r in matching if r.get("target_pct")=="1" and r.get("stop_pct")=="1"]
        r=matches[0] if matches else (matching[0] if matching else None)
        if r is None:status="MISSING";outcome="NO_ENTRY"
        else:status=r["status"];outcome=r.get("outcome","NO_ENTRY")
        item={"event_id":eid,"symbol":sym,"direction":direction,"strategy":strategy,"parameter":param,"status":status,"outcome":outcome,
              "target_first":int(outcome=="TARGET_FIRST"),"stop_first":int(outcome=="STOP_FIRST"),"entered":int(status=="COMPLETE")}
        paired.append(item);groups[(sym,direction,strategy)].append(item);groups[(sym,"ALL",strategy)].append(item)
summary=[]
for (sym,direction,strategy),items in sorted(groups.items()):
    n=len(items);w=sum(x["target_first"] for x in items);lo,hi=wilson(w,n)
    summary.append({"symbol":sym,"direction":direction,"strategy":strategy,"events":n,"entries":sum(x["entered"] for x in items),
       "target_first":w,"stop_first":sum(x["stop_first"] for x in items),
       "no_entry":sum(x["status"] in ("NO_ENTRY","ENTRY_TOO_LATE") for x in items),
       "ambiguous":sum(x["outcome"]=="AMBIGUOUS" for x in items),
       "no_touch":sum(x["outcome"]=="NO_TOUCH" for x in items),
       "target_first_per_event":round(w/n,4),"wilson95_low":lo,"wilson95_high":hi})
write("coin_direction_strategy.csv",summary);write("paired_events.csv",paired)
# Paired discordances measure actual added value without independent-sample fiction.
lookup={(x["event_id"],x["strategy"]):x for x in paired}
comparison=[]
for sym in sorted({x["symbol"] for x in paired}):
    ids=sorted({x["event_id"] for x in paired if x["symbol"]==sym})
    pairs=[(lookup.get((eid,"IMMEDIATE")),lookup.get((eid,"PULLBACK_CLOSE"))) for eid in ids]
    pairs=[(i,p) for i,p in pairs if i and p]
    comparison.append({"symbol":sym,"events":len(pairs),
      "both_win":sum(i["target_first"] and p["target_first"] for i,p in pairs),
      "pullback_only_win":sum(not i["target_first"] and p["target_first"] for i,p in pairs),
      "immediate_only_win":sum(i["target_first"] and not p["target_first"] for i,p in pairs),
      "neither_win":sum(not i["target_first"] and not p["target_first"] for i,p in pairs)})
write("paired_coin_comparison.csv",comparison)
manifest={"status":"SHADOW_RESEARCH_ONLY","source":a.input,"input_rows":len(data),"all_events":len(all_events),"complete_240m_events":len(event_keys),
"methods":["Exact same real event IDs and fixed deadline after first detection","No-entry counts in per-event denominator","Wilson 95% descriptive intervals; not independent event confidence guarantees","Paired discordant outcomes compare immediate vs pullback"],
"limitations":["Only one observed event date: cannot establish day-to-day stability","Repeated alerts, symbols and shared BTC regime correlate outcomes","No historic Swing join: event universes and first-detection times differ","No fees/slippage, real alert delivery, OI or funding","No live trading modifications"]}
(out/"manifest.json").write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))
