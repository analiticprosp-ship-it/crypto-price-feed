#!/usr/bin/env python3
"""Quality-only as-of join. Never interpret this dataset as a validated predictive backtest."""
import csv,datetime as dt,json,pathlib,collections
FLOW=pathlib.Path("flow");METRICS=pathlib.Path("metrics");OUT=pathlib.Path("detector_h1_h10_join_audit");OUT.mkdir(exist_ok=True)
def stamp(s):return dt.datetime.fromisoformat(s.replace("Z","+00:00"))
manifest={"method":"Join 5m spot/perp taker flow at bucket start t to last metrics observation timestamp <= t-10 minutes; hourly prices are already last closed hour. This is a conservative provisional lag, NOT proven publication-time availability.","warning":"metrics timestamp semantics and source publication delay not verified; do not run predictive backtests from this join","source_r2_provenance":{"flow":json.loads((FLOW/"_r2_provenance.json").read_text()),"metrics":json.loads((METRICS/"_r2_provenance.json").read_text())},"symbols":{}}
for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
 def loadflow(market):
  p=FLOW/f"{market}_{sym}_2026-09-01_to_03_5m.csv"
  with p.open(newline="") as f:return {stamp(r["timestamp_utc"]):r for r in csv.DictReader(f)}
 spot=loadflow("spot");perp=loadflow("perp")
 mp=METRICS/f"{sym}_research_5m.csv"
 # only keep window 2026-08-31 to 2026-09-04, no large memory usage
 m={}
 with mp.open(newline="") as f:
  for r in csv.DictReader(f):
   t=stamp(r["timestamp_utc"])
   if dt.datetime(2026,8,31,tzinfo=dt.timezone.utc)<=t<dt.datetime(2026,9,4,tzinfo=dt.timezone.utc):m[t]=r
 path=OUT/f"{sym}_flow_oi_asof_5m.csv"
 n=0;miss=collections.Counter();gaps=0
 with path.open("w",newline="") as f:
  fields=["timestamp_utc","spot_buy_quote","spot_sell_quote","spot_delta_quote","perp_buy_quote","perp_sell_quote","perp_delta_quote","metrics_timestamp_utc","metrics_lag_minutes","sum_open_interest","sum_open_interest_valid","sum_open_interest_value","sum_open_interest_value_valid","spot_1h_close","spot_1h_valid","perp_1h_close","perp_1h_valid","join_quality"]
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for t in sorted(set(spot)|set(perp)):
   cutoff=t-dt.timedelta(minutes=10)
   candidates=[cutoff-dt.timedelta(minutes=5*k) for k in range(0,7)]
   mt=next((x for x in candidates if x in m),None)
   s=spot.get(t);p=perp.get(t);r=m.get(mt) if mt else None
   flags=[]
   if not s:flags.append("MISSING_SPOT_FLOW")
   if not p:flags.append("MISSING_PERP_FLOW")
   if not r:flags.append("MISSING_LAGGED_METRICS")
   if r and (r.get("sum_open_interest_valid")!="1" or r.get("sum_open_interest_value_valid")!="1"):flags.append("INVALID_OI")
   if r and (r.get("spot_1h_valid")!="1" or r.get("perp_1h_valid")!="1"):flags.append("INVALID_HOURLY_PRICE")
   for flag in flags:miss[flag]+=1
   if mt and (t-mt).total_seconds()<600:raise AssertionError("as-of violation")
   row={"timestamp_utc":t.isoformat(),"spot_buy_quote":s["taker_buy_quote"] if s else "","spot_sell_quote":s["taker_sell_quote"] if s else "","spot_delta_quote":s["delta_quote"] if s else "","perp_buy_quote":p["taker_buy_quote"] if p else "","perp_sell_quote":p["taker_sell_quote"] if p else "","perp_delta_quote":p["delta_quote"] if p else "","metrics_timestamp_utc":mt.isoformat() if mt else "","metrics_lag_minutes":int((t-mt).total_seconds()/60) if mt else "", "sum_open_interest":r.get("sum_open_interest","") if r else "","sum_open_interest_valid":r.get("sum_open_interest_valid","") if r else "","sum_open_interest_value":r.get("sum_open_interest_value","") if r else "","sum_open_interest_value_valid":r.get("sum_open_interest_value_valid","") if r else "","spot_1h_close":r.get("spot_1h_close","") if r else "","spot_1h_valid":r.get("spot_1h_valid","") if r else "","perp_1h_close":r.get("perp_1h_close","") if r else "","perp_1h_valid":r.get("perp_1h_valid","") if r else "","join_quality":"OK_PROVISIONAL" if not flags else ";".join(flags)}
   w.writerow(row);n+=1
 manifest["symbols"][sym]={"joined_rows":n,"expected_rows":864,"missing_or_invalid":dict(miss),"output":path.name,"lag_policy_minutes":10}
 print("JOIN",sym,json.dumps(manifest["symbols"][sym]),flush=True)
(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
