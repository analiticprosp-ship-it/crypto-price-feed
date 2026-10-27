#!/usr/bin/env python3
"""09L v089B fixed sign rule on 8 DAILY Binance BTC price/aggflow cases per date.
Not a liquidation-event test. Not a calibrated forecast or sealed prospective OOS.
"""
import collections,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parent
DATES=[f"2026-10-{n:02d}" for n in range(19,27)]
RULES=("always_up","always_down","past_30s_momentum_sign","past_30s_aggflow_sign")
def main():
 source=[];daily={};all_rows=[]
 for day in DATES:
  p=ROOT/"derived"/"daily_binance"/(day+".json")
  d=json.loads(p.read_text())
  if d["status"]!="DAILY_PRICE_ONLY_EXPLORATORY" or d["source"]["status"]!="OK" or len(d["eight_fixed_utc_windows"])!=8:raise ValueError("NOT_A_VALID_DAILY_SOURCE")
  source.append({"date":day,"source_zip_sha256":d["source"]["downloaded_zip_sha256"],
                 "sha256_publisher":d["source"]["publisher_sha256"],"n_aggtrade_records":d["source"]["total_aggtrade_rows"]})
  cases=[];excluded=collections.Counter()
  for r in d["eight_fixed_utc_windows"]:
   fx=r["past_only"];out=r["forward_outcomes_not_features"]["300"]["return_bps"]
   if r["status"]!="LABEL_READY" or out is None or fx["momentum_bps"] is None or fx["raw_agg_flow_imbalance"] is None:
    excluded["MISSING_ASOF_OR_PAST"]+=1;continue
   if out==0:excluded["FLAT_TARGET"]+=1;continue
   y=out>0
   preds={"always_up":True,"always_down":False,
          "past_30s_momentum_sign":fx["momentum_bps"]>0,
          "past_30s_aggflow_sign":fx["raw_agg_flow_imbalance"]>0}
   cases.append({"clock_utc":r["clock_utc"],"target_up":y,"five_min_return_bps":out,
                 "rules":{k:{"predict_up":v,"correct":int(v==y)} for k,v in preds.items()}})
  daily[day]={"n_eligible":len(cases),"excluded":dict(excluded),
              "up_fraction":sum(x["target_up"] for x in cases)/len(cases) if cases else None,
              "fixed_sign_rule_accuracy":{name:{"correct":sum(x["rules"][name]["correct"] for x in cases),
                       "n":len(cases),"accuracy":round(sum(x["rules"][name]["correct"] for x in cases)/len(cases),5) if cases else None}
                  for name in RULES}}
  all_rows.extend(cases)
 total={name:{"correct":sum(c["rules"][name]["correct"] for c in all_rows),
              "n":len(all_rows),"accuracy":round(sum(c["rules"][name]["correct"] for c in all_rows)/len(all_rows),5) if all_rows else None}
         for name in RULES}
 out={"study":"09L v089B 8 non-first-of-month Binance USD-M price-only fixed-sign diagnostics",
      "status":"RETROSPECTIVE_PRICE_ONLY_BENCHMARK_NO_LIQUIDATION_MECHANISM",
      "source_daily":source,"eight_predeclared_dates":DATES,
      "calendar_dates":len(daily),"fixed_clock_opportunities":64,
      "eligible_labels_5m":len(all_rows),"per_date":daily,
      "overall_pseudopooled_descriptive":total,
      "science_note":["Binance aggTrades compressed aggregates cannot be compared raw-count-wise to Tardis individual message data.",
       "Exchange trade timestamps, not measured live point-in-time publication latency.",
       "Eight consecutive calendar dates share temporal dependence, 64 windows are not 64 independent trials.",
       "NOT an observed liquidation study, cascade test or CoinGlass model-2 heatmap first-hit; true PIT missing.",
       "These historic dates were picked after they occurred; not prospective blinded OOS.",
       "No optimization, calibration, trading signal or ROI computed."],
      "trading_canon_unchanged":True}
 path=ROOT/"derived"/"binance_daily_fixed_sign_summary.json"
 with path.open("x") as f:json.dump(out,f,indent=2,ensure_ascii=False)
 print(json.dumps({"status":out["status"],"distinct_days":out["calendar_dates"],"eligible":len(all_rows),
                   "opportunities":64,"models":total,"per_day_eligible":{d:x["n_eligible"] for d,x in daily.items()}},sort_keys=True))
if __name__=="__main__":main()
