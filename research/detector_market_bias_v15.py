#!/usr/bin/env python3
"""SHADOW-only, leakage-aware market bias versus LONG limit-entry outcomes."""
import csv,json,subprocess,sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
out=Path("detector_market_bias_v15_results");out.mkdir(exist_ok=True)
subprocess.run([sys.executable,"research/detector_post_stop_v14.py"],check=True)
def read(path):
 with open(path,newline="") as f:return list(csv.DictReader(f))
trials=read("detector_post_stop_v14_results/limit_entry_trials.csv")
events=json.loads(Path("detector-signal-events.json").read_text())["events"]
def ts(x):return datetime.fromisoformat(x.replace("Z","+00:00")).timestamp()
valid=[e for e in events if e.get("status")=="EARLY_CANDIDATE_SHADOW" and e.get("direction") in ("LONG","SHORT") and e.get("firstDetectedAtUtc")]
byid={e["id"]:e for e in valid}
bias={}
for e in valid:
 if e["direction"]!="LONG":continue
 t=ts(e["firstDetectedAtUtc"])
 # Strictly historical and excluding the current symbol to reduce mechanical self-correlation.
 past=[x for x in valid if x["id"]!=e["id"] and x["symbol"]!=e["symbol"] and 0<t-ts(x["firstDetectedAtUtc"])<=3600]
 # Deduplicate each symbol to its most recently observed direction, rather than counting repeated alerts.
 latest={}
 for x in past:
  if x["symbol"] not in latest or ts(x["firstDetectedAtUtc"])>ts(latest[x["symbol"]]["firstDetectedAtUtc"]):latest[x["symbol"]]=x
 n=len(latest);short=sum(x["direction"]=="SHORT" for x in latest.values());long=n-short
 # 3 independent symbols is a minimum coverage requirement, not statistical independence.
 regime="INSUFFICIENT" if n<3 else ("SHORT_HEAVY" if short/n>=.67 else "LONG_HEAVY" if long/n>=.67 else "MIXED")
 bias[e["id"]]={"event_id":e["id"],"symbol":e["symbol"],"detected_utc":e["firstDetectedAtUtc"],
  "prior_window_min":60,"other_symbols":n,"short_symbols":short,"long_symbols":long,
  "short_share":round(short/n,4) if n else "","regime":regime}
joined=[]
for r in trials:
 if r["event_id"] in bias:joined.append({**r,**{k:v for k,v in bias[r["event_id"]].items() if k not in ("event_id","symbol","detected_utc")}})
def save(name,rr):
 if not rr:return
 fields=sorted(set().union(*(x.keys() for x in rr)))
 with (out/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rr)
save("event_market_bias.csv",list(bias.values()))
save("bias_joined_limit_trials.csv",joined)
groups=defaultdict(list)
for r in joined:
 if r["complete_4h"]!="True" or r["target_from_fill_pct"]!="1":continue
 groups[(r["regime"],r["anchor_delay_min"],r["discount_pct"])].append(r)
summary=[]
for (regime,delay,discount),rr in sorted(groups.items()):
 summary.append({"regime":regime,"anchor_delay_min":delay,"discount_pct":discount,
 "events":len(rr),"distinct_symbols":len({r["symbol"] for r in rr}),
 **{k:sum(r["outcome"]==k for r in rr) for k in ("TARGET_FIRST","STOP_FIRST","NO_FILL","NO_TOUCH","FILL_BAR_AMBIGUOUS","AMBIGUOUS")}})
save("regime_entry_comparison.csv",summary)
# Exploratory predeclared mapping; not a deployable signal, no optimizing on this day's labels.
rules={"SHORT_HEAVY":"1","MIXED":"0.75","LONG_HEAVY":"0.5"}
mapped=[]
for e in bias.values():
 choice=rules.get(e["regime"])
 for r in joined:
  if r["event_id"]==e["event_id"] and r["anchor_delay_min"]=="0" and r["target_from_fill_pct"]=="1" and r["discount_pct"]==choice:
   mapped.append({"event_id":e["event_id"],"symbol":e["symbol"],"regime":e["regime"],"discount_pct":choice,
                  "outcome":r["outcome"],"complete_4h":r["complete_4h"]})
save("adaptive_exploratory.csv",mapped)
manifest={"status":"SHADOW_RESEARCH_ONLY","source":"Real Detector firstDetectedAtUtc, OKX 5m SWAP proxy via v1.4",
 "long_events":len(bias),"regime_counts":dict((k,sum(x["regime"]==k for x in bias.values())) for k in ("SHORT_HEAVY","MIXED","LONG_HEAVY","INSUFFICIENT")),
 "dates":sorted({e["detected_utc"][:10] for e in bias.values()}),
 "rules":["Use only other symbols' events strictly preceding LONG detection by up to 60m",
 "Last observed direction per symbol, no future events or reconstructed signals",
 "At least 3 other symbols for regime classification; otherwise INSUFFICIENT",
 "SHORT_HEAVY >=67 percent SHORT, LONG_HEAVY >=67 percent LONG, otherwise MIXED",
 "Adaptive illustrative mapping: SHORT_HEAVY->-1%, MIXED->-0.75%, LONG_HEAVY->-0.5%",
 "INSUFFICIENT has no adaptive entry; never silently assign a regime",
 "Complete 4h only for scored comparisons, 5m same-bar ambiguity not scored as win",
 "One-day and correlated events cannot establish predictive market bias",
 "No real orders, fees, slippage, spot execution or changes to Detector/Futures/limits"]}
(out/"manifest.json").write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
