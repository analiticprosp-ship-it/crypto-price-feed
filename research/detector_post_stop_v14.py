#!/usr/bin/env python3
"""SHADOW LONG limit-entry and post-stop audit; no live trading."""
import csv,json,datetime as dt,requests
from pathlib import Path
from collections import defaultdict
from detector_entry_window_v01 import getbars,ms,iso
out=Path("detector_post_stop_v14_results");out.mkdir(exist_ok=True)
events=[e for e in json.loads(Path("detector-signal-events.json").read_text())["events"] if e.get("direction")=="LONG" and e.get("status")=="EARLY_CANDIDATE_SHADOW"]
now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
s=requests.Session();s.headers["User-Agent"]="shadow-post-stop-v14"
bars_by={};errors={}
for sym in sorted({e["symbol"] for e in events}):
 try:
  bars_by[sym]=getbars(s,sym,min(ms(e["firstDetectedAtUtc"]) for e in events if e["symbol"]==sym)-600000,now)
 except Exception as ex:bars_by[sym]=[];errors[sym]=str(ex)
rows=[];stops=[]
def first_touch(bb,price,target,stop):
 for b in bb:
  up=b[2]>=price*(1+target/100);down=b[3]<=price*(1-stop/100)
  if up and down:return "AMBIGUOUS",b[0]
  if down:return "STOP_FIRST",b[0]
  if up:return "TARGET_FIRST",b[0]
 return "NO_TOUCH",None
for e in events:
 bars=bars_by[e["symbol"]];det=ms(e["firstDetectedAtUtc"])
 first=next((i for i,b in enumerate(bars) if b[0]>=det and b[0]+300000<=now),None)
 if first is None:continue
 # Stop of immediate-entry model, then observe whether original +0.5/+1 target is revisited.
 ref=bars[first][1];end=det+240*60000
 if now>=end:
  sample=[b for b in bars[first:] if b[0]+300000<=end]
  stop_at=next((j for j,b in enumerate(sample) if b[3]<=ref*.99),None)
  if stop_at is not None:
   sb=sample[stop_at]
   for target in (.5,1):
    after=sample[stop_at+1:]
    first_up=next((b for b in after if b[2]>=ref*(1+target/100)),None)
    first_down=next((b for b in after if b[3]<=ref*.98),None)
    stops.append({"event_id":e["id"],"symbol":e["symbol"],"target_above_signal_pct":target,
      "stop_bar_utc":iso(sb[0]),"after_stop_target_seen":bool(first_up),
      "after_stop_further_minus_2_seen":bool(first_down),
      "first_recovery_bar_utc":iso(first_up[0]) if first_up else "",
      "first_minus_2_bar_utc":iso(first_down[0]) if first_down else "",
      "post_stop_min_low_pct_from_signal":round(100*(min(b[3] for b in after)/ref-1),4) if after else "",
      "same_stop_bar_order_unknown":True})
 # Baselines at initial observed open or at 30min later; buy limit can only fill AFTER anchor.
 for delay in (0,30):
  anchor=next((j for j,b in enumerate(bars) if b[0]>=det+delay*60000),None)
  if anchor is None:continue
  anchor_price=bars[anchor][1]
  for discount in (.5,.75,1,1.5):
   limit=anchor_price*(1-discount/100)
   # 4h deadline from first detection; no retrospective fill in anchor bar.
   future=[b for b in bars[anchor+1:] if b[0]+300000<=min(now,end)]
   fill=next((k for k,b in enumerate(future) if b[3]<=limit),None)
   for target in (.5,1,2):
    base={"event_id":e["id"],"symbol":e["symbol"],"detected_utc":e["firstDetectedAtUtc"],
      "anchor_delay_min":delay,"discount_pct":discount,"target_from_fill_pct":target,
      "complete_4h":now>=end,"anchor_price":anchor_price,"limit_price":round(limit,8)}
    if fill is None:rows.append(dict(base,outcome="NO_FILL"));continue
    # Do not award target from same bar as limit fill; ordering unknown.
    fb=future[fill];later=future[fill+1:]
    outcome,t=first_touch(later,limit,target,1)
    samebar_target=fb[2]>=limit*(1+target/100)
    samebar_stop=fb[3]<=limit*.99
    if samebar_target or samebar_stop:outcome="FILL_BAR_AMBIGUOUS"
    rows.append(dict(base,outcome=outcome,fill_bar_utc=iso(fb[0]),
      fill_delay_min=round((fb[0]-det)/60000,2),
      later_max_drawdown_pct=round(100*(min(b[3] for b in later)/limit-1),4) if later else "",
      first_outcome_bar_utc=iso(t) if t else ""))
def save(name,items):
 if not items:return
 with (out/name).open("w",newline="") as f:
  fields=sorted(set().union(*(r.keys() for r in items)));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(items)
save("limit_entry_trials.csv",rows);save("post_stop_recovery.csv",stops)
summary=[]
groups=defaultdict(list)
for r in rows:
 if r["complete_4h"]:groups[(r["anchor_delay_min"],r["discount_pct"],r["target_from_fill_pct"])].append(r)
for (delay,discount,target),rr in sorted(groups.items()):
 summary.append({"anchor_delay_min":delay,"discount_pct":discount,"target_pct":target,"events":len(rr),
  **{k:sum(x["outcome"]==k for x in rr) for k in ("TARGET_FIRST","STOP_FIRST","NO_TOUCH","NO_FILL","AMBIGUOUS","FILL_BAR_AMBIGUOUS")}})
save("limit_entry_summary.csv",summary)
manifest={"status":"SHADOW_RESEARCH_ONLY","long_events":len(events),"complete_4h_events":len({r["event_id"] for r in rows if r["complete_4h"]}),
 "errors":errors,"rules":["LONG only; SHORT retained unchanged in original Detector for market-bias research",
 "Original stop recovery uses initial entry price and 4h deadline","Limit anchor: first 5m open at or after detection or +30m",
 "Limit fill checked only in bars AFTER anchor bar to prevent same-bar lookahead",
 "Fill bar target/stop ordering is unknown and always flagged ambiguous",
 "Target and stop in same later bar ambiguous, never a win",
 "5m OKX SWAP OHLC proxy, not spot execution or guaranteed fills",
 "No commissions, slippage, order-book queue, independent-day validation or trading actions",
 "No 24h/7d conclusions before elapsed full observation"] }
(out/"manifest.json").write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
