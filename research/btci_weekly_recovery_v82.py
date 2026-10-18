#!/usr/bin/env python3
"""BTCI v8.2: weekly phase + breadth recovery checkpoint research.
No trading approval, no edits to detector/Master/Futures/NAV or other assets.
"""
import datetime as dt
import hashlib,json,os,statistics
from collections import Counter
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG="research/btci_v82_weekly_recovery_prereg_2026-10-18.json"
V80_KEY="research/detector/v8.0/runs/39124773092-1/combined/phase_transitions.json"
V80_SHA="b4fb7e7bb0640e052c9c95dc405da8f406d3b051b476f56226abb7a813e86f10"
V81_KEY="research/detector/v8.1/runs/39125649306-1/comparison.json"
V81_SHA="5748d90333c350f8de41376084791bc64e4920e28c4f701e9447cd08badaacbf"
V80_ROOT="research/detector/v8.0/runs/39124773092-1/assets/"
ASSETS=("BTC","ETH","SOL","BNB","LINK","XRP","ADA","DOGE")
ALTS=("SOL","BNB","LINK","XRP","ADA","DOGE")
CATEGORIES=("BTC_WEEKLY_CONFIRMED_PLUS_BROAD_PARTICIPATION",
"BTC_WEEKLY_CONFIRMED_NARROW","BTC_WEEKLY_NOT_CONFIRMED",
"INSUFFICIENT_DATA")
def sha(blob):return hashlib.sha256(blob).hexdigest()
def six(value):return round(float(value),6) if value is not None else None
def client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def checked_get(s,b,key,digest):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=digest:raise SystemExit("V82_SOURCE_SHA_CHANGED:"+key)
 return json.loads(raw)
def checked_write(s,b,key,obj):
 raw=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False,indent=2).encode()
 digest=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
  Metadata={"sha256":digest,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=digest:
  raise SystemExit("V82_R2_READBACK_MISMATCH:"+key)
 return digest

def sma_week(weekly,j):
 if j<29:return None
 return sum(weekly[j-k][1] for k in range(30))/30.0
def weekly_at(prices,day):
 # A Sunday bar is complete ONLY once that Sunday's UTC candle has closed.
 # The original daily observation is always made after its UTC day close.
 weekly=sorted((d,v) for d,v in prices.items() if d.weekday()==6 and d<=day)
 if len(weekly)<34:
  return {"status":"NOT_ENOUGH_HISTORY","weeklyBars":len(weekly)}
 j=len(weekly)-1
 ma=sma_week(weekly,j);prior_ma=sma_week(weekly,j-4)
 assert ma and prior_ma
 close=weekly[-1][1]
 values=[x[1] for x in weekly]
 higherhigh=max(values[-4:])>max(values[-8:-4])
 higherlow=min(values[-4:])>min(values[-8:-4])
 above=close>ma
 slope=100*(ma/prior_ma-1)
 positive_slope=slope>0
 confirmed=above and positive_slope and higherhigh and higherlow
 return {"status":"AVAILABLE",
  "weekEndingUTC":weekly[-1][0].isoformat(),
  "weekCloseFuturesNonExecutable":six(close),
  "sma30Week":six(ma),"sma30WeekSlope4WeekPct":six(slope),
  "aboveSma30Week":above,
  "last4WeeklyCloseHigherHigh":higherhigh,
  "last4WeeklyCloseHigherLow":higherlow,
  "weeklyTrendConfirmed":bool(confirmed),
  "weeklyBars":len(weekly)}

def breadth_at(prices,day):
 prior=day-dt.timedelta(days=30)
 if any(day not in prices[sym] or prior not in prices[sym] for sym in ASSETS):
  return {"status":"UNKNOWN_BREADTH","missingPairs":
    [sym for sym in ASSETS if day not in prices[sym] or prior not in prices[sym]]}
 btc_factor=prices["BTC"][day]/prices["BTC"][prior]
 rel={sym:100*((prices[sym][day]/prices[sym][prior])/btc_factor-1)
  for sym in ASSETS if sym!="BTC"}
 usd={sym:100*(prices[sym][day]/prices[sym][prior]-1) for sym in ASSETS if sym!="BTC"}
 n=sum(rel[sym]>0 for sym in ALTS)
 rising=sum(usd[sym]>0 for sym in ALTS)
 return {"status":"AVAILABLE",
  "btc30dPct":six(100*(btc_factor-1)),
  "ethVsBtc30dPct":six(rel["ETH"]),
  "altsOutperformBTC30d":n,"altsPositiveUSD30d":rising,
  "relative30dPct":{sym:six(v) for sym,v in rel.items()},
  "broadParticipation":bool(rel["ETH"]>0 and n>=4)}

def classify(week,breadth):
 if week["status"]!="AVAILABLE" or breadth["status"]!="AVAILABLE":
  return "INSUFFICIENT_DATA"
 if not week["weeklyTrendConfirmed"]:return "BTC_WEEKLY_NOT_CONFIRMED"
 return ("BTC_WEEKLY_CONFIRMED_PLUS_BROAD_PARTICIPATION"
         if breadth["broadParticipation"]
         else "BTC_WEEKLY_CONFIRMED_NARROW")

def main():
 prereg_raw=(ROOT/PREREG).read_bytes();p=json.loads(prereg_raw)
 if (p.get("version")!="8.2" or
     p["inputs"]["v80"]!={"key":V80_KEY,"sha256":V80_SHA} or
     p["inputs"]["v81"]!={"key":V81_KEY,"sha256":V81_SHA}):
  raise SystemExit("V82_PREREG_CHANGED")
 s=client();b=os.environ["R2_BUCKET"]
 v80=checked_get(s,b,V80_KEY,V80_SHA)
 v81=checked_get(s,b,V81_KEY,V81_SHA)
 if (v80.get("version"),v81.get("version"))!=("8.0","8.1"):
  raise SystemExit("V82_PARENT_VERSION_CHANGED")
 if (len(v81["cases"])!=9 or v81["historicalCompletedCheckpoints"]!=8 or
  v80["latest"]["date"]!="2026-10-17"):
  raise SystemExit("V82_PARENT_COHORT_CHANGED")
 prices={};lineage={}
 for sym in ASSETS:
  root=V80_ROOT+sym+"/"
  claimed=v80["sources"]["assets"][sym]["sourceDailySha256"]
  records=checked_get(s,b,root+"daily.json",claimed)
  rows={dt.date.fromisoformat(x["day"]):x["close"] for x in records}
  if len(rows)!=len(records):raise SystemExit("V82_DUPLICATE_DATE:"+sym)
  prices[sym]=rows
  lineage[sym]={"dailySha256":claimed,"days":len(records)}
 cases=[]
 for old in v81["cases"]:
  day=dt.date.fromisoformat(old["checkpointUTC"])
  entry=dt.date.fromisoformat(old["recoveryConfirmed"])
  if (day-entry).days!=31:raise SystemExit("V82_INVALID_31D_COHORT")
  btc=prices["BTC"].get(day)
  if btc is None or abs(btc-old["btcCheckpointPriceFuturesNonExecutable"])>1e-8:
   raise SystemExit("V82_CHECKPOINT_PRICE_CHANGED")
  weekly=weekly_at(prices["BTC"],day)
  breadth=breadth_at(prices,day)
  category=classify(weekly,breadth)
  if day==dt.date(2026,10,17) and (breadth.get("altsOutperformBTC30d")!=v80["latest"]["outperformingAlts"] or
                                  breadth.get("altsPositiveUSD30d")!=v80["latest"]["positiveAlts"]):
   raise SystemExit("V82_CURRENT_BREADTH_PARITY_FAILED")
  cases.append({"recoveryConfirmed":old["recoveryConfirmed"],
   "checkpointUTC":old["checkpointUTC"],
   "priceFuturesNonExecutable":btc,
   "btcReturnFirst31DaysPct":old["btcCheckpointReturnSinceConfirmationPct"],
   "phaseAtCheckpoint":old["stateAtCheckpoint"],
   "riskAtCheckpoint":old["riskAtCheckpoint"],
   "weekly":weekly,"breadth":breadth,"category":category,
   "frozenOutcome":old["future"],
   "bearInNext90d":old["bearConfirmationInNext90d"],
   "bullInNext180d":old["bullConfirmationInNext180d"]})
 if [x["checkpointUTC"] for x in cases]!=[x["checkpointUTC"] for x in v81["cases"]]:
  raise SystemExit("V82_COHORT_ORDER_CHANGED")
 def summarize(sub):
  f90=[x["frozenOutcome"]["90"]["returnPct"] for x in sub if x["frozenOutcome"]["90"]["status"]=="OBSERVED"]
  return {"n":len(sub),"observedNext90d":len(f90),
    "rightCensoredNext90d":len(sub)-len(f90),
    "next90dMedianPct":six(statistics.median(f90)) if f90 else None,
    "next90dPositiveCount":sum(v>0 for v in f90),
    "confirmedBearInNext90d":sum(x["bearInNext90d"]["status"]=="EVENT_OBSERVED" for x in sub),
    "confirmedBullInNext180d":sum(x["bullInNext180d"]["status"]=="EVENT_OBSERVED" for x in sub),
    "censoredNext180dBull":sum(x["bullInNext180d"]["status"]=="RIGHT_CENSORED" for x in sub),
    "inferenceStatus":"LOW_SAMPLE" if len(sub)<20 else "RETROSPECTIVE_ONLY"}
 historical=cases[:-1];current=cases[-1]
 if current["checkpointUTC"]!="2026-10-17":
  raise SystemExit("V82_CURRENT_NOT_LAST")
 summaries={cat:summarize([x for x in historical if x["category"]==cat]) for cat in CATEGORIES}
 result={"version":"8.2","status":"EXPLORATORY_WEEKLY_BREADTH_RECOVERY_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,"asOfUTC":"2026-10-17",
  "source":{"v80":{"key":V80_KEY,"sha256":V80_SHA},
            "v81":{"key":V81_KEY,"sha256":V81_SHA},"assets":lineage},
  "preregistration":{"path":PREREG,"sha256":sha(prereg_raw)},
  "selection":"All 9 recovery-confirmation events observed in v8.1; fixed 31d checkpoint, first 8 have future 90d, current censored",
  "weekMethod":"Only fully completed Sunday close >= 30wk sample, last 4 weekly close extrema versus prior 4, SMA30wk slope 4 weeks",
  "breadthMethod":"30-day ETH/BTC relative >0 and >=4/6 fixed major alt USD-M assets outperform BTC on same days",
  "historicalCases":len(historical),"byCategory":summaries,
  "cases":cases,"current":current,
  "conclusionGate":{"validatedSignal":False,
    "reason":"All categories have <20 independent historical recovery checkpoints and thresholds chosen after earlier market research; no prior uninspected holdout.",
    "nextStudy":"Historical weekly all-regime time series and pre-registered prospective closed-week review; do not optimize on nine events."},
  "limitations":[
    "2020-2026 retrospective, not prospective; classification heuristic and 31d checkpoint hypothesis posthoc",
    "A weekly CLOSE is not intraweek BTC high/low; full OHLC not claimed",
    "Reusing a few overlapping recovery episodes for outcomes violates independent-sample assumptions",
    "Future 30/90/180 outcomes are untouched frozen v8.1 observations and right-censored",
    "ETF institutional flow and macro liquidity not in historical classifier due to unverified point-in-time source vintages",
    "Single futures venue prices cannot substitute for live multi-source executable Spot",
    "No advice to change any holdings, positions, limits, NAV, P&L, reserve, capital or trading rules"]}
 root=f"research/btci/v8.2/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 folder=Path("btci_v82_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(result,ensure_ascii=False,indent=2).encode()
 (folder/"comparison.json").write_bytes(raw)
 digest=checked_write(s,b,root+"comparison.json",raw)
 manifest={"version":"8.2","status":"WEEKLY_BREADTH_RESEARCH_PASS",
   "researchOnly":True,"reportSha256":digest,
   "preregSha256":sha(prereg_raw),"prefix":root}
 ms=checked_write(s,b,root+"manifest.json",manifest)
 brief={"status":"V82_WEEKLY_BREADTH_PASS_WRITEBACK_VERIFIED",
  "current":current,"historicalCategories":summaries,
  "cases":[{"date":x["checkpointUTC"],"phase":x["phaseAtCheckpoint"],
    "weeklyConfirmed":x["weekly"].get("weeklyTrendConfirmed"),
    "breadth":x["breadth"].get("altsOutperformBTC30d"),
    "category":x["category"],"next90d":x["frozenOutcome"]["90"]}
    for x in cases],
  "reportSha256":digest,"manifestSha256":ms,"prefix":root}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V82_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write("# BTCI 8.2 — исторические восстановительные эпизоды\n\n"
   "Только исследование, без торгового права.\n\n"
   f"Текущая категория: {current['category']}\n\n"
   f"R2: {root}\n\n"
   f"SHA-256: {digest}\n")
if __name__=="__main__":main()
