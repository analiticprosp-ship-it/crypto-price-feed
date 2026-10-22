#!/usr/bin/env python3
"""09L AUTO v1.1 daily derived-only health ledger for sparse samples and v087 gaps.
No trades, no "cascade probability", no speculation authorizations.
"""
import argparse,datetime as dt,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parent
DER=ROOT/"derived"
def utc():return dt.datetime.now(dt.timezone.utc)
def tparse(s):return dt.datetime.fromisoformat(s.replace("Z","+00:00"))
def health(now,write=True):
 files=sorted((DER/"live_snapshots").glob("*/*/*/*.json"))
 events=[]
 for p in files:
  try:
   r=json.loads(p.read_text())
   if r.get("study")!="09L-AUTO-v1.1 sparse public market snapshot":continue
   received=tparse(r["capture_begin_utc"])
   events.append((received,r))
  except Exception:continue
 events.sort(key=lambda x:x[0])
 last=events[-1][1] if events else None
 start=events[0][0] if events else None
 coverage={}
 if start:
  # Do not invent missed history before system was first activated.
  whole_completed_hours=[]
  h=start.replace(minute=0,second=0,microsecond=0)+dt.timedelta(hours=1)
  while h < now.replace(minute=0,second=0,microsecond=0):
   whole_completed_hours.append(h.strftime("%Y%m%d%H"));h+=dt.timedelta(hours=1)
  has=set(x[0].strftime("%Y%m%d%H") for x in events)
  coverage={"from_first_observed_utc":start.isoformat(),"completed_hours_since_activation":len(whole_completed_hours),
    "captured_completed_hours":sum(z in has for z in whole_completed_hours),
    "missing_completed_hours":[z for z in whole_completed_hours if z not in has][-48:],
    "count_samples_total":len(events),
    "note":"Github Actions scheduled UTC cron is best-effort; sparse snapshots do not cover intra-hour events."}
 source={}
 if last:
  for item in last["snapshots"]:
   key=item["venue"]+"_"+item["instrument_kind"]
   source[key]={"status":item["status"],"last_capture_utc":last["capture_end_utc"],
                "source_age_ms":item.get("source_age_ms"),
                "http_status":item.get("http_status"),
                "error_tag":item.get("error_tag")}
 studies=[]
 for f in sorted((DER/"v087_labels").glob("*/*_no_lookahead_trade_labels.json")):
  try:
   o=json.loads(f.read_text())
   studies.append({"date":o["source_date_utc"],"venue":o["venue"],"status":o["status"],
       "cases_ready":sum(x["status"]=="LABEL_READY" for x in o["eight_clock_fixed_cases"]),
       "case_count":len(o["eight_clock_fixed_cases"]),
       "source_sha256":o["source"].get("compressed_sha256")})
  except Exception as e:studies.append({"file":f.name,"status":"UNREADABLE_LABEL_DATA"})
 known=sum(x.get("cases_ready",0) for x in studies)
 eligible=sum(x.get("case_count",0) for x in studies)
 status=("BOOTSTRAP_NO_SNAPSHOTS" if last is None else
   "CAPTURE_WITH_SOURCE_GAPS" if any(x["status"]!="SOURCE_SNAPSHOT_VALID" for x in last["snapshots"])
   else "SPARSE_CAPTURE_ALL_FOUR_SOURCES_AVAILABLE")
 obj={"study":"09L AUTO v1.1 data health","report_at_utc":now.isoformat(),
      "status":status,"live_snapshot_coverage":coverage,"latest_live_source_status":source,
      "v087_historical_labels":{"observed_cases":eligible,"complete_case_labels":known,
                                "incomplete_or_missing_case_labels":eligible-known,"datasets":studies},
      "coinglass_model2_pit":"MISSING_NO_CREDENTIALS_OR_PRIVATE_PIT_COLLECTOR",
      "predictive_cascade_model_status":"NOT_VALIDATED_NO_INDEPENDENT_CHRONOLOGICAL_TEST",
      "trading_canon_changes":False}
 if write:
  p=DER/"health"/now.strftime("%Y%m%dT%H%M%S%fZ.json")
  p.parent.mkdir(parents=True,exist_ok=True)
  with p.open("x") as f:f.write(json.dumps(obj,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
  obj["artifact_path"]=str(p.relative_to(ROOT))
 return obj
def main():
 arg=argparse.ArgumentParser();arg.add_argument("--selftest",action="store_true");a=arg.parse_args()
 if a.selftest:
  z=health(dt.datetime(2026,10,22,tzinfo=dt.timezone.utc),False)
  assert z["trading_canon_changes"] is False
  assert z["predictive_cascade_model_status"].startswith("NOT_VALIDATED")
  print(json.dumps({"status":"SELFTEST_PASS"}))
 else:
  z=health(utc());print(json.dumps({"status":z["status"],"label_readiness":z["v087_historical_labels"],
   "path":z["artifact_path"],"source_status":z["latest_live_source_status"]}))
if __name__=="__main__":main()
