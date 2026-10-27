#!/usr/bin/env python3
"""09L forward-date ledger for precommitted daily Binance price-only observations.
This is archive reconstruction, not real-time trading/PIT liquidation prediction.
"""
import collections,datetime as dt,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parent
DATA=ROOT/"derived"/"daily_binance"
START=dt.date(2026,10,27)
NAMES=("always_up","always_down","past_30s_momentum_sign","past_30s_aggflow_sign")
def main():
 now=dt.datetime.now(dt.timezone.utc)
 end=now.date()-dt.timedelta(days=1)
 eligible=[];missing=[];daily={}
 d=START
 while d<=end:
  day=d.isoformat()
  f=DATA/(day+".json")
  if not f.exists():
   missing.append({"day":day,"status":"NOT_ARCHIVED"});d+=dt.timedelta(days=1);continue
  j=json.loads(f.read_text())
  if j.get("status")!="DAILY_PRICE_ONLY_EXPLORATORY" or j.get("source",{}).get("status")!="OK":raise RuntimeError("SOURCE_PROVENANCE_OR_DATA_INVALID")
  if j.get("date")!=day or len(j.get("eight_fixed_utc_windows",[]))!=8:raise RuntimeError("CLOCKS_OR_DATE_MISMATCH")
  counters={s:[0,0] for s in NAMES};miss=collections.Counter()
  for c in j["eight_fixed_utc_windows"]:
   f0=c["past_only"];y=c["forward_outcomes_not_features"]["300"]["return_bps"]
   if c["status"]!="LABEL_READY" or y is None:miss["ASOF_OR_FEATURE_MISSING"]+=1;continue
   if y==0:miss["FLAT_TARGET"]+=1;continue
   target=y>0
   preds={"always_up":True,"always_down":False,
       "past_30s_momentum_sign":f0["momentum_bps"]>0,
       "past_30s_aggflow_sign":f0["raw_agg_flow_imbalance"]>0}
   for name,pred in preds.items():
    counters[name][1]+=1
    counters[name][0]+=int(pred==target)
  daily[day]={"n_eligible":counters[NAMES[0]][1],"excluded":dict(miss),
     "fixed_rule_correct":{k:v[0] for k,v in counters.items()},
     "fixed_rule_accuracy":{k:round(v[0]/v[1],6) if v[1] else None for k,v in counters.items()},
     "source_zip_sha256":j["source"]["publisher_sha256"]}
  eligible.append(day);d+=dt.timedelta(days=1)
 pooled={}
 for name in NAMES:
  correct=sum(x["fixed_rule_correct"][name] for x in daily.values())
  n=sum(x["n_eligible"] for x in daily.values())
  pooled[name]={"correct":correct,"n":n,"accuracy":round(correct/n,6) if n else None}
 rec={"study":"09L v0.9.0 forward-calendar-day source publication ledger",
    "created_at_utc":now.isoformat(),"forward_calendar_start_utc":START.isoformat(),
    "last_closed_day_utc":end.isoformat(),
    "status":"NO_FORWARD_SOURCE_YET" if not daily else "SHADOW_FORWARD_DAILY_LEDGER",
    "complete_days_archived":len(eligible),"missing_closed_dates":missing,
    "daily":daily,"pooled_descriptive_not_independent":pooled,
    "no_observed_liquidations":True,"no_true_heatmap_PIT":True,
    "no_signed_dealer_gamma":True,"prospective_design_locked_but_archive_acquired_after_events":True,
    "no_trading_or_Nav_mutation":True}
 p=ROOT/"derived"/"forward_ledgers"/(now.strftime("%Y%m%dT%H%M%S%fZ")+".json")
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("x") as f:json.dump(rec,f,indent=2,ensure_ascii=False)
 print(json.dumps({"status":rec["status"],"complete_dates":len(daily),"missing_days":len(missing),
                   "n_usable":sum(x["n_eligible"] for x in daily.values()),
                   "accuracy":pooled,"report":str(p.relative_to(ROOT))}))
if __name__=="__main__":main()
