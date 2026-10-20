#!/usr/bin/env python3
"""09L v0.8.6 QA addendum: verify L2 reset windows on independent venue dates. Shadow only."""
import csv,datetime,gzip,hashlib,io,json,sys,urllib.request,collections
from pathlib import Path
DIR=Path("research/09l/v0.8.6-2026-10-20/derived")
STUDIES=("bybit_sep","okx_oct")
class Tap:
 def __init__(self,s):self.s=s;self.h=hashlib.sha256();self.n=0
 def read(self,n=-1):
  b=self.s.read(n);self.h.update(b);self.n+=len(b)
  if self.n>450_000_000:raise RuntimeError("COMPRESSED_CAP")
  return b
ALL=[]
for study in STUDIES:
 obj=json.loads((DIR/f"09L_v086_{study}_fixed_clock_robustness.json").read_text())
 source=next(s for s in obj["sources"] if s["kind"]=="incremental_book_L2")
 url=source["url"]
 resets=[]
 try:
  resp=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"09L-v086-reset-QA"}),timeout=110)
  tap=Tap(resp)
  f=io.TextIOWrapper(gzip.GzipFile(fileobj=tap),encoding="utf8",newline="")
  cols=f.readline().strip().split(","); ix={v:i for i,v in enumerate(cols)}
  for name in ("symbol","is_snapshot","local_timestamp"):
   if name not in ix:raise ValueError("MISSING_COL_"+name)
  prev=False;rows=0
  for line in f:
   a=line.strip().split(",");rows+=1
   if a[ix["symbol"]]!=obj["symbol"]:continue
   snap=a[ix["is_snapshot"]].lower()=="true"
   if snap and not prev:resets.append(int(a[ix["local_timestamp"]]))
   prev=snap
  expected=source["compressed_sha256"]; sha=tap.h.hexdigest()
  status="OK" if sha==expected and len(resets)==obj["quality"]["reconstruction_snapshot_resets"] else "QA_MISMATCH"
 except Exception as err:
  status="SOURCE_UNAVAILABLE_OR_ERROR";sha=None;rows=0;error=type(err).__name__+": "+str(err)[:200]
 per=[]
 for e in obj["casebook"]:
  t0=int(datetime.datetime.fromisoformat(e["utc_anchor"]).timestamp()*1e6)
  near=[t for t in resets if t0-30_000_000<=t<t0+300_000_000]
  per.append({"case_id":e["case_id"],"group":e["group"],"reset_in_window_n":len(near),
   "reset_times_utc":[datetime.datetime.fromtimestamp(t/1e6,datetime.timezone.utc).isoformat() for t in near],
   "eligible_no_reset":not near and e["state"]=="EVALUATED"})
 old={x["case_id"]:x for x in obj["casebook"]}
 clean=[old[x["case_id"]] for x in per if x["group"]=="fixed_clock" and x["eligible_no_reset"]]
 def summarize(kind):
  den=sum(x[kind]["combined"]["total_decrement"] for x in clean)
  match=sum(x[kind]["combined"]["matched"] for x in clean)
  return {"raw_denominator":round(den,6),"raw_matched":round(match,6),
   "share_pct":round(100*match/den,4) if den else None}
 summary={"fixed_windows_total":8,"unaffected_fixed_windows":len(clean),
  "affected_fixed_windows":8-len(clean),"correct":summarize("correct"),"flipped":summarize("flipped"),
  "shift_5s":summarize("shift_5s"),
  "correct_gt_flipped_windows":sum(x["correct"]["combined"]["share_pct"]>x["flipped"]["combined"]["share_pct"] for x in clean),
  "correct_gt_shift_windows":sum(x["correct"]["combined"]["share_pct"]>x["shift_5s"]["combined"]["share_pct"] for x in clean)}
 r={"study":"09L v0.8.6 full L2 resynchronization sensitivity", "venue":obj["venue"],"date":obj["date"],"status":status,
 "downloaded_sha256":sha,"expected_sha256":source["compressed_sha256"],
 "scanned_rows":rows,"reconstructed_reset_count":len(resets),
 "reset_windows":per,"strict_no_reset_fixed_window_sensitivity":summary,
 "trade_canon_mutation":False,
 "disclaimer":"No single observed reset in a case window is not proof there are no hidden provider capture gaps; snapshot resets are vendor source restarts, not cancelled orders or market events."}
 if status!="OK":r["error"]=locals().get("error")
 out=DIR/f"09L_v086_{study}_l2_reset_window_audit.json";out.write_text(json.dumps(r,indent=2,ensure_ascii=False)+"\n")
 ALL.append({"study":study,"status":status,"n_resets":len(resets),"fixed_unaffected":len(clean),"strict":summary})
 print(json.dumps(ALL[-1]),flush=True)
(DIR/"09L_v086_resets_summary.json").write_text(json.dumps(ALL,indent=2,ensure_ascii=False)+"\n")
