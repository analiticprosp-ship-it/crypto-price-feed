#!/usr/bin/env python3
"""Research-only feature-level quality masks and conservative hourly as-of price joins."""
import collections,csv,datetime as dt,json,math,pathlib
SRC=pathlib.Path("detector_h1_h10_metrics_history")
PRICES=pathlib.Path("detector_h1_h10_monthly")
OUT=pathlib.Path("detector_h1_h10_masked_dataset");OUT.mkdir(exist_ok=True)
FEATURES=("sum_open_interest","sum_open_interest_value","sum_toptrader_long_short_ratio","count_toptrader_long_short_ratio","count_long_short_ratio","sum_taker_long_short_vol_ratio")
def num(x):
 try:
  v=float(x)
  return v if math.isfinite(v) else None
 except (TypeError,ValueError):return None
def ts(x):
 d=dt.datetime.fromisoformat(x.replace("Z","+00:00"))
 return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d.astimezone(dt.timezone.utc)
def prices(symbol,market):
 candles={}
 for p in sorted(PRICES.glob(f"{market}_{symbol}_????-??_1h.csv")):
  with p.open(newline="") as f:
   for r in csv.DictReader(f):
    start=int(r["open_time_ms"]);close=start+3600000
    candles[close]=r
 return candles
report={"policy":"Only 1h candles fully closed at or before metrics timestamp. Exact timestamp alignment; never forward-fill metrics, missing fields remain blank and mask=0.","source_metrics_run":json.loads((SRC/"_r2_provenance.json").read_text())["run_id"],"source_prices_run":json.loads((PRICES/"_r2_provenance.json").read_text())["run_id"],"symbols":{}}
for symbol in ("BTCUSDT","ETHUSDT","SOLUSDT"):
 spot=prices(symbol,"spot");perp=prices(symbol,"perp")
 stat=collections.Counter();seen=set();previous=None
 target=OUT/f"{symbol}_research_5m.csv"
 with (SRC/f"{symbol}_metrics_5m.csv").open(newline="") as inp,target.open("w",newline="") as outf:
  reader=csv.DictReader(inp)
  fields=["timestamp_utc","symbol","timestamp_unique","continuity_5m","spot_1h_close","perp_1h_close","spot_1h_valid","perp_1h_valid"]
  for feature in FEATURES:fields.extend((feature,feature+"_valid"))
  writer=csv.DictWriter(outf,fieldnames=fields);writer.writeheader()
  for r in reader:
   try:t=ts(r["create_time"])
   except (ValueError,KeyError):stat["bad_timestamp"]+=1;continue
   stamp=int(t.timestamp()*1000);hour_close=stamp//3600000*3600000
   # An hourly candle is known only after the full hour has elapsed.
   sp=spot.get(hour_close);pp=perp.get(hour_close)
   unique=stamp not in seen;continuity=previous is None or stamp-previous==300000
   row={"timestamp_utc":t.isoformat(),"symbol":symbol,"timestamp_unique":int(unique),"continuity_5m":int(continuity),"spot_1h_close":sp["close"] if sp else "","perp_1h_close":pp["close"] if pp else "","spot_1h_valid":int(bool(sp)),"perp_1h_valid":int(bool(pp))}
   for feature in FEATURES:
    v=num(r.get(feature));row[feature]=r.get(feature,"") if v is not None else "";row[feature+"_valid"]=int(v is not None)
    if v is None:stat["missing_"+feature]+=1
   if not unique:stat["duplicates"]+=1
   if not continuity:stat["gap_boundary_rows"]+=1
   if sp and pp:stat["both_prices_available"]+=1
   stat["rows"]+=1;writer.writerow(row)
   seen.add(stamp);previous=stamp
 report["symbols"][symbol]=dict(stat)
 print("MASKED",json.dumps({"symbol":symbol,**dict(stat)}),flush=True)
(OUT/"manifest.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
print("SUMMARY",json.dumps({"rows":sum(v.get("rows",0) for v in report["symbols"].values()),"both_prices_available":sum(v.get("both_prices_available",0) for v in report["symbols"].values())}),flush=True)
