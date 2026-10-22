#!/usr/bin/env python3
"""09L v0.8.7: FROZEN retrospective two-date, no-lookahead baseline vs flow diagnostic.
DO NOT call this a predictive validation or liquidation cascade model.
Python stdlib only. Group dates rather than treating 2 same-BTC venue windows as independent.
"""
import collections,datetime as dt,hashlib,json,math,pathlib,statistics,sys
ROOT=pathlib.Path(__file__).resolve().parent
DATA=ROOT.parent/"auto"/"v1"/"derived"/"v087_labels"
OUT=ROOT/"derived"
VENUES={"bybit":["2026-06-01","2026-07-01","2026-08-01","2026-09-01","2026-10-01"],
        "okex-swap":["2026-06-01","2026-07-01","2026-08-01","2026-10-01"]}
TRAIN_DAYS={"2026-06-01","2026-07-01","2026-08-01"}
TEST_DAYS={"2026-09-01","2026-10-01"}
CLOCKS=["07:24:30","08:32:30","13:49:30","14:19:30","15:10:30","15:49:30","17:28:30","18:38:30"]
HORIZONS=(300,30,60)
LAM=2.0
def sigmoid(z):
 if z>=0:
  ex=math.exp(-z);return 1.0/(1.0+ex)
 ex=math.exp(z);return ex/(1.0+ex)
def nclip(x):return max(-5.0,min(5.0,x))
def solve(A,b):
 # deterministic partial-pivot Gaussian elimination with no external libraries
 m=len(b);A=[list(x)+[b[i]] for i,x in enumerate(A)]
 for k in range(m):
  piv=max(range(k,m),key=lambda i:abs(A[i][k]))
  if abs(A[piv][k])<1e-11:raise ValueError("HESSIAN_SINGULAR")
  A[k],A[piv]=A[piv],A[k]
  div=A[k][k]
  for j in range(k,m+1):A[k][j]/=div
  for i in range(m):
   if i==k:continue
   mult=A[i][k]
   if mult:
    for j in range(k,m+1):A[i][j]-=mult*A[k][j]
 return [A[i][m] for i in range(m)]
def xraw(row,augment):
 F=row["features"]
 a=[float(F["past_30s_price_return_bps"]),float(F["past_30s_high_low_range_bps"]),
    math.log1p(F["n_trades_past_30s"]),float(row["venue"]=="okex-swap")]
 if augment:a.append(float(F["raw_flow_imbalance"]))
 if not all(math.isfinite(v) for v in a):raise ValueError("NONFINITE_FEATURE")
 return a
def scaler(train,augment):
 mat=[xraw(x,augment) for x in train]
 means=[statistics.mean(col) for col in zip(*mat)]
 scales=[max(math.sqrt(sum((row[j]-means[j])**2 for row in mat)/len(mat)),1e-9) for j in range(len(means))]
 return means,scales
def scaled(row,augment,means,scales):
 raw=xraw(row,augment)
 return [1.0]+[nclip((raw[j]-means[j])/scales[j]) for j in range(len(raw))]
def fit(train,augment):
 means,scales=scaler(train,augment)
 x=[scaled(row,augment,means,scales) for row in train]
 y=[row["target_up"] for row in train]
 n=len(x[0]);beta=[0.0]*n
 smooth=(sum(y)+1)/(len(y)+2)
 beta[0]=math.log(smooth/(1-smooth))
 for iteration in range(60):
  grad=[0.0]*n
  H=[[0.0]*n for _ in range(n)]
  for xx,yy in zip(x,y):
   p=sigmoid(sum(v*b for v,b in zip(xx,beta)))
   w=max(p*(1-p),1e-10)
   for j in range(n):
    grad[j]+=xx[j]*(yy-p)
    for k in range(n):H[j][k]+=w*xx[j]*xx[k]
  for j in range(1,n):
   grad[j]-=LAM*beta[j];H[j][j]+=LAM
  step=solve(H,grad)
  for j in range(n):beta[j]+=step[j]
  if max(abs(z) for z in step)<1e-9:break
 return {"beta":[round(b,12) for b in beta],
         "train_mean":[round(a,12) for a in means],
         "train_scale":[round(a,12) for a in scales],
         "lambda":LAM,"irls_iteration":iteration+1,
         "train_rows":len(train),"prevalence_train":sum(y)/len(y)}
def predict(model,row,augment):
 xx=scaled(row,augment,model["train_mean"],model["train_scale"])
 return sigmoid(sum(a*b for a,b in zip(xx,model["beta"])))
def loss(p,y):
 pp=min(1-1e-12,max(1e-12,p))
 return {"brier":(pp-y)**2,"logloss":-(y*math.log(pp)+(1-y)*math.log(1-pp)),
         "correct":int((pp>=.5)==bool(y))}
def metric(vals):
 if not vals:return None
 return {k:round(sum(x[k] for x in vals)/len(vals),7) for k in ("brier","logloss","correct")}
def aggregate(preds,model):
 return metric([p["losses"][model] for p in preds])
def bygroup(preds,model,key):
 groups=collections.defaultdict(list)
 for p in preds:groups[p[key]].append(p)
 return {g:{"n":len(rows),**aggregate(rows,model)} for g,rows in sorted(groups.items())}
def load():
 sources=[];rows=[]
 for venue,days in VENUES.items():
  for day in days:
   p=DATA/venue/(day+"_no_lookahead_trade_labels.json")
   if not p.is_file():raise FileNotFoundError(str(p))
   raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest();obj=json.loads(raw)
   if (obj.get("source_date_utc"),obj.get("venue"),obj.get("source",{}).get("status"))!=(day,venue,"OK"):raise ValueError("INVALID_SOURCE_META "+p.name)
   if not obj.get("trading_canon_unchanged") or not obj.get("features_strictly_pre_anchor"):raise ValueError("FUTURE_FEATURE_OR_CANON "+p.name)
   if not obj.get("source",{}).get("compressed_sha256"):raise ValueError("NO_RAW_SOURCE_HASH "+p.name)
   cases=obj.get("eight_clock_fixed_cases") or []
   if len(cases)!=8 or [e["clock_utc"] for e in cases]!=CLOCKS:raise ValueError("EVENT_CLOCK_MUTATED "+p.name)
   sources.append({"filename":str(p.relative_to(ROOT.parent.parent.parent)),"venue":venue,"day":day,
                   "derived_json_sha256":h,"tardis_gzip_sha256":obj["source"]["compressed_sha256"],"n_cases":len(cases)})
   for c in cases:
    tm=dt.datetime.fromisoformat(c["anchor_utc"])
    if tm.date().isoformat()!=day or tm.strftime("%H:%M:%S")!=c["clock_utc"]:raise ValueError("EVENT_DATE_MISMATCH")
    ref=c.get("reference_trade")
    if ref and (ref["last_trade_us"]>int(tm.timestamp()*1_000_000) or ref["age_ms"]>2000):raise ValueError("LOOKAHEAD_REFERENCE_PRICE")
    rows.append({"venue":venue,"date":day,"clock_utc":c["clock_utc"],"status":c["status"],
                 "features":c["past_features_only"],
                 "outcomes":c["forward_outcomes_not_features"],
                 "reference_age_ms":ref["age_ms"] if ref else None})
 return sources,rows
def evaluate(rows,horizon):
 ready=[];rejected=collections.Counter()
 for row in rows:
  result=row["outcomes"].get(str(horizon),{})
  val=result.get("return_bps")
  if row["reference_age_ms"] is None or row["reference_age_ms"]>2000 or result.get("source_age_ms") is None or result["source_age_ms"]>2000:
   rejected["asof_missing_or_gt2s"]+=1;continue
  if val is None or not math.isfinite(val):
   rejected["outcome_missing_or_nonfinite"]+=1;continue
  if abs(val)<1e-10:
   rejected["exactly_flat_excluded"]+=1;continue
  try:
   xraw(row,True)
  except (TypeError,ValueError,KeyError):
   rejected["pre_anchor_feature_missing"]+=1;continue
  ready.append({**row,"target_up":int(val>0),"return_bps":val})
 train=[x for x in ready if x["date"] in TRAIN_DAYS]
 test=[x for x in ready if x["date"] in TEST_DAYS]
 if not train or not test or len({x["target_up"] for x in train})<2:raise ValueError("COHORT_TARGET_NOT_ELIGIBLE")
 if len({x["date"] for x in train})<3 or {x["date"] for x in test}!=TEST_DAYS:raise ValueError("MONTH_SPLIT_NOT_READY")
 base=fit(train,False);aug=fit(train,True)
 prevalence=(sum(x["target_up"] for x in train)+1)/(len(train)+2)
 preds=[]
 for row in test:
  ps={"prevalence":prevalence,"baseline":predict(base,row,False),
      "augmented":predict(aug,row,True)}
  losses={name:loss(prob,row["target_up"]) for name,prob in ps.items()}
  preds.append({"date":row["date"],"venue":row["venue"],"clock_utc":row["clock_utc"],
                "actual_up":row["target_up"],"observed_forward_return_bps":row["return_bps"],
                "model_probabilities_up":{k:round(v,9) for k,v in ps.items()},
                "losses":losses})
 groups={}
 for model in ("prevalence","baseline","augmented"):
  groups[model]={"n_test":len(preds),"pooled":aggregate(preds,model),
                "by_date":bygroup(preds,model,"date"),"by_venue":bygroup(preds,model,"venue"),
                "day_equal_brier":round(statistics.mean(v["brier"] for v in bygroup(preds,model,"date").values()),7),
                "day_equal_logloss":round(statistics.mean(v["logloss"] for v in bygroup(preds,model,"date").values()),7)}
 improving_days={day:groups["augmented"]["by_date"][day]["brier"]<groups["baseline"]["by_date"][day]["brier"] and
   groups["augmented"]["by_date"][day]["logloss"]<groups["baseline"]["by_date"][day]["logloss"] for day in sorted(TEST_DAYS)}
 # Calibration diagnostic: per-venue absolute difference between mean predicted probability and fraction up.
 venues=sorted({p["venue"] for p in preds});cal={}
 for v in venues:
  sample=[p for p in preds if p["venue"]==v];observed=statistics.mean(x["actual_up"] for x in sample)
  cal[v]={"n":len(sample),"fraction_up":round(observed,6)}
  for model in ("baseline","augmented"):
   mean_pred=statistics.mean(x["model_probabilities_up"][model] for x in sample)
   cal[v][model+"_abs_mean_calibration_gap"]=round(abs(mean_pred-observed),7)
 cal_ok=all(c["augmented_abs_mean_calibration_gap"]<=c["baseline_abs_mean_calibration_gap"]+1e-12 for c in cal.values())
 gain=all(improving_days.values()) and cal_ok
 return {"horizon_seconds":horizon,"n_input_rows":len(rows),"n_eligible_total":len(ready),
         "n_train":len(train),"n_holdout":len(test),
         "n_calendar_days_train":3,"n_calendar_days_holdout":2,
         "excluded_reasons":dict(rejected),
         "train_up_fraction":round(sum(x["target_up"] for x in train)/len(train),6),
         "holdout_up_fraction":round(sum(x["target_up"] for x in test)/len(test),6),
         "models":{"prevalence_laplace":round(prevalence,9),"baseline_coefficients":base,"augmented_coefficients":aug},
         "metrics":groups,
         "per_date_augmented_improves_brier_and_logloss":improving_days,
         "per_venue_mean_calibration_gap":cal,
         "calibration_nonworse_each_venue":cal_ok,
         "exploratory_gate":"EXPLORATORY_INCREMENTAL_SIGNAL_FOR_PROSPECTIVE_TEST_ONLY" if gain else "NO_REPLICATED_INCREMENTAL_GAIN",
         "holdout_predictions":preds}
def selftest():
 a=solve([[3.,1.],[1.,2.]],[5.,5.])
 assert max(abs(a[0]-1),abs(a[1]-2))<1e-10
 assert round(sigmoid(0),8)==0.5
 assert sigmoid(-900)==0.0 and sigmoid(900)==1.0  # expected IEEE754 saturation
 assert loss(.5,1)["brier"]==.25
 print(json.dumps({"status":"SELFTEST_PASS","cohort_count":9,"date_split":"2026-06..08 -> 2026-09..10"}))
def main():
 if "--selftest" in sys.argv:selftest();return
 sources,rows=load()
 assert len(sources)==9 and len(rows)==72
 out={"study":"09L v0.8.7 retrospective fixed time-split directional return baseline vs pre-anchor flow",
      "protocol":"PREDICTIVE_COMPARISON_PREREG_LOCKED_2026-10-22.md",
      "status":"RETROSPECTIVE_BASELINE_DIAGNOSTIC_COMPLETE_NOT_PROSPECTIVE_OOS",
      "source_cohorts":sources,"total_cases":len(rows),"observed_calendar_days":5,
      "primary_horizon_seconds":300,
      "method":"L2_RIDGE_LOGISTIC_LAMBDA_2_TRAIN_ONLY_STANDARDIZATION_CLIP_5_FIXED_NO_SEARCH",
      "coinglass_model2_PIT":"MISSING","source_book_asof_matched":"NOT_IN_FEATURES",
      "trade_canon_mutation":False,
      "interpretation_limits":["Nine source cohorts but only FIVE distinct market calendar dates, TWO holdout calendar dates.",
         "Venue rows on the same day and clock are not independent because BTC price evolves jointly.",
         "Selection/model design retrospective in historical data known before prereg; not unseen prospective OOS.",
         "A null result cannot exclude microstructure edge at other times/horizons; a positive result cannot establish one.",
         "No liquidation-cluster heatmap source; no cascade outcome label; no maker cancel/fill identification.",
         "No trading signals, backtest profitability, transaction costs, or risk-adjusted strategy claims."],
      "horizons":{}}
 for h in HORIZONS:
  out["horizons"][str(h)]=evaluate(rows,h)
 summary=out["horizons"]["300"]
 out["primary_exploratory_gate"]=summary["exploratory_gate"]
 OUT.mkdir(parents=True,exist_ok=True)
 p=OUT/"09L_v087_retrospective_chronological_baseline_vs_flow.json"
 with p.open("x",encoding="utf8") as f:json.dump(out,f,ensure_ascii=False,indent=2,sort_keys=True);f.write("\n")
 print(json.dumps({"status":out["status"],"primary_horizon":300,
   "train":summary["n_train"],"holdout":summary["n_holdout"],
   "excluded":summary["excluded_reasons"],
   "brier":{k:summary["metrics"][k]["day_equal_brier"] for k in ("prevalence","baseline","augmented")},
   "per_date_delta":summary["per_date_augmented_improves_brier_and_logloss"],
   "venue_calibration_nonworse":summary["calibration_nonworse_each_venue"],
   "scientific_gate":out["primary_exploratory_gate"],
   "output":str(p)}))
if __name__=="__main__":main()
