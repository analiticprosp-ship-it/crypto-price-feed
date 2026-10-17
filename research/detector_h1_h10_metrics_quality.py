#!/usr/bin/env python3
"""Audit collected futures metrics; report failures, never synthesize missing observations."""
import csv,datetime as dt,json,pathlib,collections,math
root=pathlib.Path("detector_h1_h10_metrics_history")
out=pathlib.Path("detector_h1_h10_metrics_quality");out.mkdir(exist_ok=True)
manifest=json.loads((root/"manifest.json").read_text())
records=manifest["records"]
report={"source_run_id":39034387923,"source_records":len(records),"symbols":{},"limitations":["Metrics timestamp granularity and field units inferred from source CSV only; no external verification","No historical spot/perp trade join or funding analysis performed"]}
for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
 path=root/f"{sym}_metrics_5m.csv"
 with path.open(newline="") as f:
  rd=csv.DictReader(f);fields=rd.fieldnames or []
  data=list(rd)
 date_groups=collections.defaultdict(list)
 for r in data:date_groups[r["source_date"]].append(r)
 candidate=next((x for x in fields if x.lower() in ("create_time","timestamp","time","date","datetime","create time")),None)
 if not candidate:candidate=next((x for x in fields if "time" in x.lower() and x!="source_date"),None)
 def parse_ts(x):
  if not x:return None
  try:
   n=float(x)
   if n>1e14:n/=1e6
   elif n>1e11:n/=1e3
   return dt.datetime.fromtimestamp(n,dt.timezone.utc)
  except (ValueError,OverflowError,OSError):pass
  try:return dt.datetime.fromisoformat(x.strip().replace("Z","+00:00")).replace(tzinfo=dt.timezone.utc) if dt.datetime.fromisoformat(x.strip().replace("Z","+00:00")).tzinfo is None else dt.datetime.fromisoformat(x.strip().replace("Z","+00:00")).astimezone(dt.timezone.utc)
  except ValueError:return None
 problems=[];complete=0;timestamp_parsed=0;gap_days=0;duplicate_days=0;invalid_numeric=0
 numeric_fields=[x for x in fields if any(k in x.lower() for k in ("interest","ratio","taker","volume"))]
 for day,rows in sorted(date_groups.items()):
  timestamps=[parse_ts(r.get(candidate)) for r in rows] if candidate else []
  if candidate and all(x is not None for x in timestamps):timestamp_parsed+=1
  else:problems.append({"date":day,"problem":"TIMESTAMP_UNPARSEABLE","rows":len(rows)})
  if len(rows)==288:complete+=1
  else:problems.append({"date":day,"problem":"COUNT_NOT_288","rows":len(rows)})
  if timestamps and all(x is not None for x in timestamps):
   times=sorted(timestamps)
   if len(set(times))!=len(times):
    duplicate_days+=1;problems.append({"date":day,"problem":"DUPLICATE_TIMESTAMPS"})
   if any((b-a).total_seconds()!=300 for a,b in zip(times,times[1:])):
    gap_days+=1;problems.append({"date":day,"problem":"NON_5M_STEP"})
   if any(t.date().isoformat()!=day for t in times):
    problems.append({"date":day,"problem":"OUTSIDE_SOURCE_DATE"})
  for row in rows:
   for key in numeric_fields:
    val=row.get(key,"")
    try:
     if val is None or not math.isfinite(float(val)):invalid_numeric+=1
    except ValueError:invalid_numeric+=1
 report["symbols"][sym]={"rows":len(data),"days":len(date_groups),"days_with_288_rows":complete,"timestamp_field":candidate,"days_with_parseable_timestamps":timestamp_parsed,"days_with_5m_step_breaks":gap_days,"days_with_duplicates":duplicate_days,"invalid_numeric_cells":invalid_numeric,"numeric_fields":numeric_fields,"columns":fields,"problem_count":len(problems),"problem_examples":problems[:30]}
 print("AUDIT",json.dumps({"symbol":sym,"rows":len(data),"days":len(date_groups),"complete":complete,"timestamp_parsed":timestamp_parsed,"gap_days":gap_days,"duplicates":duplicate_days,"invalid_numeric":invalid_numeric,"problem_count":len(problems)}),flush=True)
(out/"quality_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("SUMMARY",json.dumps({"source_records":len(records),"total_rows":sum(x["rows"] for x in report["symbols"].values()),"total_problem_count":sum(x["problem_count"] for x in report["symbols"].values())}),flush=True)
