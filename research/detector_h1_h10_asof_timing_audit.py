#!/usr/bin/env python3
"""Audit event-time causality and availability limits. No predictive tests."""
import csv,datetime as dt,json,pathlib,collections
SRC=pathlib.Path("joined");OUT=pathlib.Path("detector_h1_h10_asof_audit");OUT.mkdir(exist_ok=True)
report={"audit":"event-time and causal-feature audit, not actual vendor publication latency validation","market_data_semantics":{"aggTrades":"row timestamp is 5m bucket START; full 5m buy/sell/delta only available at or after bucket END","oi":"source metrics create_time is unverified as publication time; a 10m event-time lag is provisional, not proven safe","hourly":"prices from masked source labelled last closed 1h, but source candle boundaries need independent audit"},"source_r2_provenance":json.loads((SRC/"_r2_provenance.json").read_text()),"symbols":{}}
for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
 p=SRC/f"{sym}_flow_oi_asof_5m.csv";counts=collections.Counter();examples=[];previous=None;rows=0
 with p.open(newline="") as f:
  for r in csv.DictReader(f):
   rows+=1
   t=dt.datetime.fromisoformat(r["timestamp_utc"]);end=t+dt.timedelta(minutes=5)
   if previous and t-previous!=dt.timedelta(minutes=5):counts["nonconsecutive_5m"]+=1
   previous=t
   mt=dt.datetime.fromisoformat(r["metrics_timestamp_utc"]) if r["metrics_timestamp_utc"] else None
   if mt is None:counts["missing_metrics_time"]+=1
   else:
    lag=(t-mt).total_seconds()/60
    if lag<10:counts["metrics_earlier_than_required_lag"]+=1
    if lag>40:counts["metrics_stale_over_40m"]+=1
    if len(examples)<3:examples.append({"flow_bucket_start":t.isoformat(),"flow_bucket_end":end.isoformat(),"metrics_event_timestamp":mt.isoformat(),"event_lag_minutes":lag,"earliest_complete_flow_time":end.isoformat()})
   if r["join_quality"]!="OK_PROVISIONAL":counts["non_ok_join"]+=1
   for field in ("spot_buy_quote","spot_sell_quote","perp_buy_quote","perp_sell_quote","spot_1h_close","perp_1h_close"):
    if not r[field]:counts["missing_"+field]+=1
   if r["spot_1h_valid"]!="1" or r["perp_1h_valid"]!="1":counts["invalid_hourly_prices"]+=1
 report["symbols"][sym]={"rows":rows,"checks":dict(counts),"examples":examples,"coverage_start":(dt.datetime.fromisoformat(examples[0]["flow_bucket_start"]).isoformat() if examples else None)}
 print("AUDIT",sym,json.dumps(report["symbols"][sym]),flush=True)
report["decision"]="ASOF_PUBLICATION_UNVERIFIED: cannot assert historical realtime availability or run a leak-free predictive backtest until OI publication lag and hourly candle boundary semantics are validated. Features using completed flow at t can only predict outcomes after t+5m."
(OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
