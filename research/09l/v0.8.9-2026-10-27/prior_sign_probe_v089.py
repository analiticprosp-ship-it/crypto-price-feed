#!/usr/bin/env python3
"""09L v089 descriptive probe: frozen past-side momentum and aggressor-flow signs.
No model training; selection was not blind; no claim of cascade probabilities.
"""
import collections,hashlib,json,math,pathlib
ROOT=pathlib.Path(__file__).resolve().parent.parent
DIR=ROOT/"v0.8.8-2026-10-23"/"derived"/"liquidation_event_proxies"
OUT=ROOT/"v0.8.9-2026-10-27"/"derived"/"diagnostics"
VENUES=("bybit","okex-swap")
DAYS=("2025-01-01","2025-04-01","2025-07-01","2025-10-01","2026-01-01")
DECISIVE={"CONTINUATION_PROXY":True,"OPPOSITE_REVERSAL_PROXY":False}
def main():
 files=[];events=[];excluded=collections.Counter()
 for day in DAYS:
  for venue in VENUES:
   p=DIR/venue/(day+"_first_message_behaviour.json")
   raw=p.read_bytes();j=json.loads(raw)
   if (j.get("source_day_utc"),j.get("venue"),j.get("status"),j.get("trading_canon_unchanged"))!=(day,venue,"EVENT_PROXIES_EXPLORATORY",True):
    raise RuntimeError("DATA_SOURCE_GATE_FAILED")
   if j["trade_sources"]["status"]!="OK" or j["liquidation_source"]["status"]!="OK":raise RuntimeError("GZIP_AUDIT_NOT_OK")
   files.append({"date":day,"venue":venue,"sha256":hashlib.sha256(raw).hexdigest(),
                 "trades_sha256":j["trade_sources"]["gzip_sha256"],
                 "liquidations_sha256":j["liquidation_source"]["gzip_sha256"]})
   for e in j["selected_session_events"]:
    label=e.get("price_behaviour_label",e["status"])
    if label not in DECISIVE:
     excluded[label]+=1
     continue
    side=e["event"]["side"];sign=1 if side=="buy" else -1
    f=e["pre_liquidation_features_only"]
    mom=f["momentum_pre_30s_bps"];flow=f["flow_imbalance_pre_30s"]
    if mom is None or flow is None or not(math.isfinite(mom) and math.isfinite(flow)):
     excluded["MISSING_PRE_EVENT_FEATURE"]+=1;continue
    y=DECISIVE[label]
    events.append({"date":day,"venue":venue,"bucket_utc":e["session_utc"],"liquidation_side":side,
                   "true_continuation_proxy":y,
                   "signed_past_momentum_bps":round(sign*mom,6),
                   "signed_flow_imbalance":round(sign*flow,6),
                   "rules":{"constant_continuation":True,
                            "positive_signed_momentum":sign*mom>0,
                            "positive_signed_flow":sign*flow>0}})
 models=("constant_continuation","positive_signed_momentum","positive_signed_flow")
 audit={}
 for name in models:
  wrong=[];correct=[];by_day={};by_venue={}
  cm=collections.Counter()
  for x in events:
   y=x["true_continuation_proxy"];p=x["rules"][name]
   cm[("TP" if p else "FN") if y else ("FP" if p else "TN")]+=1
   (correct if y==p else wrong).append(x)
  for date in DAYS:
   this=[e for e in events if e["date"]==date]
   by_day[date]={"n":len(this),"correct":sum(e["rules"][name]==e["true_continuation_proxy"] for e in this),
                 "accuracy":(round(sum(e["rules"][name]==e["true_continuation_proxy"] for e in this)/len(this),4) if this else None)}
  for venue in VENUES:
   this=[e for e in events if e["venue"]==venue]
   by_venue[venue]={"n":len(this),"correct":sum(e["rules"][name]==e["true_continuation_proxy"] for e in this),
                 "accuracy":(round(sum(e["rules"][name]==e["true_continuation_proxy"] for e in this)/len(this),4) if this else None)}
  audit[name]={"n":len(events),"correct":len(correct),"accuracy":round(len(correct)/len(events),6) if events else None,
               "confusion":{k:cm.get(k,0) for k in ("TP","TN","FP","FN")},
               "by_day":by_day,"by_venue":by_venue}
 out={"study":"09L v089 retrospective simple sign feasibility on observed liquidation message",
      "prereg":"PREREG_2025_QTR_2026_JAN_LOCKED.md",
      "status":"RETROSPECTIVE_EVENT_SIGN_PROBE_NONPREDICTIVE",
      "distinct_calendar_days":len(DAYS),"source_files":files,
      "total_source_events":len(DAYS)*len(VENUES)*3,"eligible_decisive_events":len(events),
      "excluded_reason":dict(excluded),"model_free_fixed_sign_diagnostics":audit,
      "eligible_events":events,
      "limitations":["No real Model2 PIT clusters, so NO first-hit predictions.",
         "First observed liquidation event per fixed session is not typical of large liquidations.",
         "Two exchanges share underlying BTC paths, so these cases are NOT independent trials.",
         "The source outcomes were already visible before this probe; retrospective, no truly blind OOS.",
         "These fixed signs do not identify market-maker absorption, cancellations, position closure causes, or calibrated cascade odds."],
      "coinglass_model2_first_hit":"NOT_RUN_PIT_MISSING",
      "trading_canon_unchanged":True}
 OUT.mkdir(parents=True,exist_ok=True)
 p=OUT/"09L_v089_sign_probe_first_liquidations.json"
 with p.open("x",encoding="utf8") as f:json.dump(out,f,ensure_ascii=False,indent=2,sort_keys=True);f.write("\n")
 print(json.dumps({"status":out["status"],"n_decisive":len(events),"excluded":dict(excluded),
     "accuracy":{k:[v["correct"],v["n"],v["accuracy"]] for k,v in audit.items()},
     "source_dates":len(DAYS),"files":len(files)},sort_keys=True))
if __name__=="__main__":main()
