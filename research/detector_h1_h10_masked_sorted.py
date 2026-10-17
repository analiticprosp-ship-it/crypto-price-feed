#!/usr/bin/env python3
"""Sort existing masked data by UTC and recompute continuity; no imputation or future joins."""
import collections,csv,datetime as dt,hashlib,json,pathlib
src=pathlib.Path("detector_h1_h10_masked_dataset")
out=pathlib.Path("detector_h1_h10_masked_sorted");out.mkdir(exist_ok=True)
report={"source_run_id":39057214956,"policy":"Stable UTC sort, no synthetic rows, no forward fill, no price recomputation; preserve all source fields except recompute continuity_5m and timestamp_unique.","symbols":{}}
for symbol in ("BTCUSDT","ETHUSDT","SOLUSDT"):
 source=src/f"{symbol}_research_5m.csv";target=out/source.name
 with source.open(newline="") as f:
  reader=csv.DictReader(f);fields=reader.fieldnames or [];rows=list(reader)
 assert "timestamp_utc" in fields and "continuity_5m" in fields and "timestamp_unique" in fields
 def stamp(row):
  d=dt.datetime.fromisoformat(row["timestamp_utc"].replace("Z","+00:00"))
  if d.tzinfo is None:raise ValueError("Timezone missing")
  return int(d.timestamp()*1000)
 before=collections.Counter()
 for i,r in enumerate(rows):
  if i and stamp(r)<stamp(rows[i-1]):before["out_of_order_transitions"]+=1
 rows.sort(key=stamp)
 prev=None;seen=set();gaps=[];duplicate_count=0
 for row in rows:
  t=stamp(row);unique=t not in seen
  row["timestamp_unique"]=str(int(unique))
  row["continuity_5m"]=str(int(prev is None or t-prev==300000))
  if prev is not None and t-prev>300000:gaps.append({"after":dt.datetime.fromtimestamp(prev/1000,dt.timezone.utc).isoformat(),"before":row["timestamp_utc"],"missing_5m_slots":(t-prev)//300000-1})
  if not unique:duplicate_count+=1
  seen.add(t);prev=t
 with target.open("w",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
 sha=hashlib.sha256(target.read_bytes()).hexdigest()
 report["symbols"][symbol]={"rows":len(rows),"unique_timestamps":len(seen),"duplicates":duplicate_count,"out_of_order_transitions_before_sort":before["out_of_order_transitions"],"true_gaps":gaps,"missing_slots_between_first_last":sum(x["missing_5m_slots"] for x in gaps),"sha256":sha,"first_timestamp":rows[0]["timestamp_utc"],"last_timestamp":rows[-1]["timestamp_utc"]}
 print("SORTED",json.dumps({"symbol":symbol,"rows":len(rows),"duplicates":duplicate_count,"out_of_order_before":before["out_of_order_transitions"],"gap_count":len(gaps),"missing_slots":sum(x["missing_5m_slots"] for x in gaps)}),flush=True)
(out/"manifest.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
print("SUMMARY",json.dumps({"rows":sum(x["rows"] for x in report["symbols"].values()),"duplicates":sum(x["duplicates"] for x in report["symbols"].values()),"missing_slots":sum(x["missing_slots_between_first_last"] for x in report["symbols"].values())}),flush=True)
