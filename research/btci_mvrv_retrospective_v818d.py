#!/usr/bin/env python3
"""BTCI 8.18d: retrospective reconstructed MVRV vs frozen BTC 684-week
risks. NOT an authentic original-published point-in-time model.
"""
import csv,datetime as dt,hashlib,io,json,math,os,statistics,collections
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818d_mvrv_exploratory_prereg_2026-10-19.json"
BASE=("research/btci/v8.17.1/runs/39212878778-1/full_historical_rise_fall.json",
      "539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091")
PILOT=("research/btci/v8.18c1/runs/39224031916-1/onchain_official_csv_source.json",
       "2736819d515a9d94aa9a8a0afc29dec8f25bb281780448cb8450096ebbf90af3")
CMCSV=("research/btci/v8.18c1/runs/39224031916-1/source/CoinMetrics_Official_btc.csv",
       "06495ff8e643432e6948b7b4686ce44fc106217287dabdc1b38351d9ddec46c3")
MODELS=("BASE_BTC","BASE_STRICT","BASE_NEG","HIGH3","HIGH4","LOW1","LOW2","FALL30","RISE30",
        "BTC_HIGH3","BTC_LOW2","BTC_FALL30","BTC_RISE30",
        "STRICT_HIGH3","STRICT_LOW2","NEG_LOW1")
TARGETS=("UP13","UP26","UP52","DOWN13","DOWN26","DOWN52","POSITIVE13","POSITIVE26","POSITIVE52")
def sha(x):return hashlib.sha256(x).hexdigest()
def day(s):return dt.date.fromisoformat(s)
def rnd(x):return round(float(x),6) if x is not None else None
def rate(a,b):return rnd(a/b) if b else None
def med(x):return rnd(statistics.median(x)) if x else None
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def checked(s,b,key,h):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=h:raise SystemExit("V818D_FROZEN_SOURCE_SHA_CHANGED")
 return raw
def put(s,b,key,z):
 raw=z if isinstance(z,bytes) else json.dumps(z,ensure_ascii=False,indent=2).encode()
 h=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
   Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=h:raise SystemExit("V818D_R2_READBACK_FAILED")
 return h
def stats(rows):
 x={"n":len(rows),"baseTargets":{t:sum(z["targets"][t] for z in rows) for t in TARGETS},
    "models":{}}
 for model in MODELS:
  chosen=[q for q in rows if q["flags"][model]]
  n=len(chosen)
  x["models"][model]={"alarms":n,"medianMvrv":med([z["MVRV_Tminus1d"] for z in chosen]),
   "medianCloseReturn26":med([z["returns"]["26"] for z in chosen]),
   "targets":{}}
  for t in ("UP13","UP26","UP52","DOWN13","DOWN26","DOWN52","POSITIVE26"):
   tp=sum(z["targets"][t] for z in chosen)
   fp=n-tp
   total=x["baseTargets"][t]
   x["models"][model]["targets"][t]={"TP":tp,"FP":fp,"FN":total-tp,
     "TN":len(rows)-total-fp,"precision":rate(tp,n),
     "recall":rate(tp,total)}
 return x
def subset(rows,model,weeks):
 selected=[];last=None
 for r in rows:
  date=day(r["date"])
  if r["flags"][model] and (last is None or (date-last).days>=7*(weeks+1)):
   selected.append(r);last=date
 return selected
def main():
 rawpre=(ROOT/PRE).read_bytes();p=json.loads(rawpre)
 parents={"btcLong":{"key":BASE[0],"sha256":BASE[1]},
   "cmAudit":{"key":PILOT[0],"sha256":PILOT[1]},
   "cmCsv":{"key":CMCSV[0],"sha256":CMCSV[1]}}
 if p["version"]!="8.18d" or p["parents"]!=parents:
  raise SystemExit("V818D_PREREG_OR_SOURCE_CHANGED")
 s=r2();bucket=os.environ["R2_BUCKET"]
 historic=json.loads(checked(s,bucket,*BASE))
 source=json.loads(checked(s,bucket,*PILOT))
 cmraw=checked(s,bucket,*CMCSV)
 if historic["version"]!="8.17.1" or len(historic["weeklyPanel"])!=684 or source["version"]!="8.18c1":
  raise SystemExit("V818D_PARENT_NOT_VERIFIED")
 entries=list(csv.DictReader(io.StringIO(cmraw.decode("utf-8-sig"))))
 mvrv={}
 for z in entries:
  if z.get("CapMVRVCur"):
   v=float(z["CapMVRVCur"])
   if math.isfinite(v) and v>0:mvrv[z["time"][:10]]=v
 out=[];missing=[]
 for x in historic["weeklyPanel"]:
  date=day(x["date"])
  histdate=(date-dt.timedelta(days=1)).isoformat()
  before=(date-dt.timedelta(days=31)).isoformat()
  current=mvrv.get(histdate);past=mvrv.get(before)
  if current is None or past is None:
   missing.append({"date":x["date"],"tMinus1Available":current is not None,
    "tMinus31Available":past is not None});continue
  A=bool(x["flags"]["A"]);B=bool(x["flags"]["STRICT_ALL"])
  neg=bool(x["flags"]["NEG_ALL"])
  H3=current>=3;H4=current>=4;L1=current<=1;L2=current<=2
  down=current<past;up=current>past
  flags={"BASE_BTC":A,"BASE_STRICT":B,"BASE_NEG":neg,
    "HIGH3":H3,"HIGH4":H4,"LOW1":L1,"LOW2":L2,"FALL30":down,"RISE30":up,
    "BTC_HIGH3":A and H3,"BTC_LOW2":A and L2,
    "BTC_FALL30":A and down,"BTC_RISE30":A and up,
    "STRICT_HIGH3":B and H3,"STRICT_LOW2":B and L2,"NEG_LOW1":neg and L1}
  out.append({"date":x["date"],"era":x["era"],"MVRV_Tminus1d":rnd(current),
    "MVRV_Tminus31d":rnd(past),
    "MVRV_delta30":rnd(current-past),"flags":flags,
    "targets":x["outcomes"],"returns":x["returns"]})
 if len(out)<675:raise SystemExit("V818D_TOO_FEW_BACKFILLED_COIN_METRICS_MVRV")
 summary=stats(out)
 eras={e:stats([z for z in out if z["era"]==e]) for e in
    ("2012","2013-2016","2017-2019","2020-2023","2024-2025")}
 locked={str(w):{m:{"n":len(z:=subset(out,m,w)),
      "UP26":sum(q["targets"]["UP26"] for q in z),
      "DOWN26":sum(q["targets"]["DOWN26"] for q in z),
      "median26Return":med([q["returns"]["26"] for q in z]),
      "firstTenDates":[q["date"] for q in z[:10]]}
      for m in ("BASE_BTC","BASE_STRICT","HIGH3","HIGH4","BTC_HIGH3","BTC_LOW2",
                "STRICT_HIGH3","STRICT_LOW2")}
       for w in (13,26)}
 risk={m:{"n":z["alarms"],
   "UP26":z["targets"]["UP26"]["TP"],
   "DOWN13":z["targets"]["DOWN13"]["TP"],
   "DOWN26":z["targets"]["DOWN26"]["TP"],
   "medianReturn26":z["medianCloseReturn26"]}
   for m,z in summary["models"].items()}
 report={"version":"8.18d","status":"MVRV_RETROSPECTIVE_BACKFILLED_BTC_EXPLORATORY_NOT_PIT",
  "researchOnly":True,"NOT_ORIGINAL_PUBLICATION_PIT":True,
  "NOT_FOR_TRADING_OR_CALIBRATION":True,
  "source":{"btc":BASE,"CoinMetricsGitHub":CMCSV,"audit":PILOT,"metric":"CapMVRVCur",
     "sourceLicense":"CC BY-NC 4.0 for noncommercial research"},
  "preregistration":{"path":PRE,"sha256":sha(rawpre)},
  "population":{"frozenN":684,"mvrvVerifiedRows":len(out),"missing":missing,
   "first":out[0]["date"],"last":out[-1]["date"],
   "historicPreMetricEra2012_2017":sum(z["date"]<"2018-01-01" for z in out)},
  "all":summary,"eras":eras,"lockouts":locked,
  "riskGroups":risk,"weeklyPanel":out,
  "limitations":[
   "Metric originally published later and official CSV reconstructed and revised through 2026; earlier historical MVRV levels never PIT certified.",
   "MVRV numerator contains BTC price so may add little information beyond BTC price momentum. Do not call it an independent exogenous macro indicator.",
   "Thresholds 3/4/1/2 exploratory pre-registered before this run but historical market cycles already heavily viewed, not OOS.",
   "Forward 13/26/52wk targets overlapping, 14wk episode lockout reduces not eliminates dependency.",
   "Coin Metrics free CSV CC BY-NC, no large public redistribution or trading authorization.",
   "No impact on live BTCI or Spot/Futures/NAV/P&L/MASTER/reserve/capital/risk limits."],
  "operationsChanged":{"Spot":False,"Futures":False,"NAV":False,
   "capital":False,"PnL":False,"reserve":False,"MASTER":False,"Detector":False,
   "tradeLimits":False}}
 folder=Path("btci_v818d_reports");folder.mkdir(exist_ok=True)
 body=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"mvrv_exploratory.json").write_bytes(body)
 prefix=f"research/btci/v8.18d/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 dg=put(s,bucket,prefix+"mvrv_exploratory.json",body)
 md=put(s,bucket,prefix+"manifest.json",{"version":"8.18d","researchOnly":True,
  "status":"MVRV_NON_PIT_EXPLORATORY_COMPLETED","reportSha256":dg,
  "preregSha256":sha(rawpre),"inputSHA":CMCSV[1]})
 brief={"status":"V818D_MVRV_BACKFILLED_SOURCE_R2_VERIFIED_NO_PIT",
  "prefix":prefix,"reportSha256":dg,"manifestSha256":md,
  "population":report["population"],"risk":risk,"eras":{e:{
   "n":z["n"],"models":{m:{"n":z["models"][m]["alarms"],
       "UP26":z["models"][m]["targets"]["UP26"]["TP"],
       "DOWN26":z["models"][m]["targets"]["DOWN26"]["TP"]}
     for m in ("BASE_BTC","BASE_STRICT","HIGH3","HIGH4","BTC_HIGH3","BTC_LOW2")}
    } for e,z in eras.items()},
   "locks":locked}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V818D_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
