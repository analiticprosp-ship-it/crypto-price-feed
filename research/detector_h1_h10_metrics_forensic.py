#!/usr/bin/env python3
"""Forensic field-level quality audit of previously downloaded futures metrics. Research only."""
import collections,csv,datetime as dt,json,math,pathlib
src=pathlib.Path("detector_h1_h10_metrics_history")
dst=pathlib.Path("detector_h1_h10_metrics_forensic");dst.mkdir(exist_ok=True)
result={"source_run_id":39034387923,"source":"Binance futures/um/daily/metrics","symbols":{},"policy":"No imputation; keep missing/invalid observations excluded from affected features; timestamps are UTC"}
for symbol in ("BTCUSDT","ETHUSDT","SOLUSDT"):
 p=src/f"{symbol}_metrics_5m.csv"
 counts=collections.Counter();examples={};daily=collections.defaultdict(list);total=0
 with p.open(newline="") as f:
  reader=csv.DictReader(f);fields=reader.fieldnames or []
  numeric=[x for x in fields if any(k in x.lower() for k in ("interest","ratio","taker","volume"))]
  for row in reader:
   total+=1;date=row["source_date"];daily[date].append(row["create_time"])
   for field in numeric:
    v=row.get(field)
    try:
     if v is None or not math.isfinite(float(v)):raise ValueError()
    except (ValueError,TypeError):
     counts[field]+=1
     if len(examples.get(field,[]))<6:examples.setdefault(field,[]).append({"date":date,"time":row.get("create_time"),"raw":v})
 anomalies=[]
 for day,raw_times in sorted(daily.items()):
  times=[]
  for raw in raw_times:
   try:
    t=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
    if t.tzinfo is None:t=t.replace(tzinfo=dt.timezone.utc)
    times.append(t.astimezone(dt.timezone.utc))
   except ValueError:pass
  expected=dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc)
  actual=set(times)
  missing=[(expected+dt.timedelta(minutes=5*i)).isoformat() for i in range(288) if expected+dt.timedelta(minutes=5*i) not in actual]
  extras=[t.isoformat() for t in times if t.date()!=expected.date() or t.second or t.microsecond or t.minute%5]
  if len(raw_times)!=288 or missing or extras:
   anomalies.append({"date":day,"rows":len(raw_times),"missing_count":len(missing),"missing_first_30":missing[:30],"unexpected_first_10":extras[:10]})
 result["symbols"][symbol]={"rows":total,"days":len(daily),"numeric_fields":numeric,"invalid_cells_by_field":dict(counts),"invalid_examples_by_field":examples,"anomalous_days":anomalies}
 print("FORENSIC",json.dumps({"symbol":symbol,"rows":total,"invalid_by_field":dict(counts),"anomalous_days":len(anomalies),"missing_by_day":[{"date":x["date"],"missing":x["missing_count"]} for x in anomalies]}),flush=True)
(dst/"forensic_report.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
print("SUMMARY",json.dumps({"rows":sum(x["rows"] for x in result["symbols"].values()),"invalid_cells":sum(sum(x["invalid_cells_by_field"].values()) for x in result["symbols"].values()),"anomalous_symbol_days":sum(len(x["anomalous_days"]) for x in result["symbols"].values())}),flush=True)
