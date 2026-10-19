#!/usr/bin/env python3
"""BTCI 8.18e: historical crypto-native crisis public-date event study.
This tests shock/contagion context, not news predictive accuracy or trade fills.
"""
import datetime as dt,hashlib,json,math,os,statistics
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818e_event_contagion_prereg_2026-10-19.json"
DAILY=("research/btci/v8.7/runs/39131902527-1/archive_manifest.json","3705a179363c9fdf50fede363fb7062481ce15c60f62dfada226e5371e674fb4")
MACRO=("research/btci/v8.17.1/runs/39212878778-1/full_historical_rise_fall.json","539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091")
def sha(x):return hashlib.sha256(x).hexdigest()
def day(x):return dt.date.fromisoformat(x)
def ds(x):return x.isoformat()
def rnd(x):return round(float(x),6) if x is not None else None
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def checked(s,b,k,h):
 raw=s.get_object(Bucket=b,Key=k)["Body"].read()
 if sha(raw)!=h:raise SystemExit("V818E_ORIGINAL_SHA_CHANGED:"+k)
 return json.loads(raw)
def save(s,b,k,raw):
 blob=raw if isinstance(raw,bytes) else json.dumps(raw,ensure_ascii=False,indent=2).encode()
 h=sha(blob)
 s.put_object(Bucket=b,Key=k,Body=blob,ContentType="application/json",Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=k)["Body"].read())!=h:raise SystemExit("V818E_SHA_REREAD_MISMATCH:"+k)
 return h
def p(prices,date):
 if date not in prices:raise ValueError("MISSING_REFERENCE_PRICE:"+ds(date))
 return prices[date]
def pct(a,b):return 100*(a/b-1)
def future_calc(prices,anchor,h):
 pre=p(prices,anchor-dt.timedelta(days=1))
 seq=[p(prices,anchor+dt.timedelta(days=z)) for z in range(h+1)]
 worst=min(seq);best=max(seq)
 peak=pre;max_draw=0
 for price in seq:
  if price>peak:peak=price
  max_draw=min(max_draw,pct(price,peak))
 return {"horizonDays":h,"lastReturnFromPreEventPct":rnd(pct(seq[-1],pre)),
  "minDailyCloseFromPreEventPct":rnd(pct(worst,pre)),
  "maxDailyCloseFromPreEventPct":rnd(pct(best,pre)),
  "worstPeakToTroughCloseDrawdownPct":rnd(max_draw),
  "firstDown10Day":next((z for z,q in enumerate(seq) if pct(q,pre)<=-10),None),
  "firstDown20Day":next((z for z,q in enumerate(seq) if pct(q,pre)<=-20),None)}
def prior(prices,date):
 pre=p(prices,date-dt.timedelta(days=1))
 week=p(prices,date-dt.timedelta(days=8))
 mon=p(prices,date-dt.timedelta(days=31))
 logs=[math.log(p(prices,date-dt.timedelta(days=30-k))/p(prices,date-dt.timedelta(days=31-k))) for k in range(30)]
 return {"baselinePriceUSD":rnd(pre),"prior7dReturnPct":rnd(pct(pre,week)),
   "prior30dReturnPct":rnd(pct(pre,mon)),
   "past30dLogReturnStdPct":rnd(100*statistics.stdev(logs)),
   "priceVsPrevious30dHighPct":rnd(pct(pre,max(p(prices,date-dt.timedelta(days=k)) for k in range(1,32))))}
def macroasof(rows,date):
 hits=[q for q in rows if day(q["date"])<date]
 if not hits:return {"status":"NO_ORIGINAL_MACRO_DATE_BEFORE_EVENT"}
 last=hits[-1];age=(date-day(last["date"])).days
 if age>21:return {"status":"MACRO_DATE_STALE","lastSunday":last["date"],"ageDays":age}
 signals=last["flags"]
 return {"status":"PAST_ONLY_ASOF_SUNDAY","lastSunday":last["date"],"ageDays":age,
 "btcWeeklyTrendUp":signals["A"],"fedLiquidityEasing":signals["F"],
 "NFCIEasing":signals["N"],"ANFCIEasing":signals["J"],
 "strictAllPositive":signals["STRICT_ALL"],"strictMacroPositive":signals["STRICT_MACRO"],
 "negativeMacroAndNoTrend":signals["NEG_ALL"],
 "btcStructural":last["startingStructural"],
 "caution":"historically archived H4.1 dated pages not proven originally unrevised"}
def main():
 raw=(ROOT/PRE).read_bytes();pr=json.loads(raw)
 if pr["version"]!="8.18e" or pr["parents"]!={"source":{"key":DAILY[0],"sha256":DAILY[1]},"macro":{"key":MACRO[0],"sha256":MACRO[1]}}:
  raise SystemExit("V818E_PREREG_CHANGED")
 s=r2();bucket=os.environ["R2_BUCKET"]
 archive=checked(s,bucket,*DAILY);macro=checked(s,bucket,*MACRO)
 if archive["version"]!="8.7" or macro["version"]!="8.17.1" or len(macro["weeklyPanel"])!=684:
  raise SystemExit("V818E_PARENT_UNEXPECTED")
 archived=archive["assets"]["btc"]["normalized"]
 rawbtc=s.get_object(Bucket=bucket,Key=archived["r2Key"])["Body"].read()
 if sha(rawbtc)!=archived["sha256"]:raise SystemExit("V818E_BTC_DAILY_SOURCE_CHANGED")
 prices={day(x["day"]):float(x["priceUSD"]) for x in json.loads(rawbtc)}
 if len(prices)<5900 or max(prices)<day("2026-10-17"):raise SystemExit("V818E_PRICE_HISTORY_INCOMPLETE")
 rows=macro["weeklyPanel"]
 if [x["date"] for x in rows]!=sorted(x["date"] for x in rows):
  raise SystemExit("V818E_MACRO_ROWS_NOT_SORTED")
 events=pr["events"]
 if len(events)!=13 or len({x["id"] for x in events})!=13:raise SystemExit("V818E_EVENT_REGISTRATION_CHANGED")
 horizons=pr["rules"]["horizons"]
 item=[]
 for e in events:
  d=day(e["date"])
  signal=macroasof(rows,d)
  obj={**e,"pastOnlyRiskContext":signal,
    "preEvent":prior(prices,d),
    "dayZeroReturnVsPrevDayPct":rnd(pct(p(prices,d),p(prices,d-dt.timedelta(days=1)))),
    "post":{str(h):future_calc(prices,d,h) for h in horizons},
    "intradayReaction":"UNKNOWN_UNDER_DAILY_PRICEUSD_REFERENCE"}
  item.append(obj)
  print("V818E_EVENT",e["id"],"btcDay0",obj["dayZeroReturnVsPrevDayPct"],
    "worstNext7d",obj["post"]["7"]["minDailyCloseFromPreEventPct"],
    "macro",obj["pastOnlyRiskContext"].get("strictAllPositive"),flush=True)
 grouping={}
 for episode in sorted({x["episode"] for x in events}):
  cohort=[x for x in item if x["episode"]==episode]
  earliest=cohort[0];latest=cohort[-1]
  firstday=day(earliest["date"]);lastday=day(latest["date"])
  grouping[episode]={
    "events":[x["id"] for x in cohort],
    "firstPublicRecordedDate":earliest["date"],"lastEventRecordedDate":latest["date"],
    "preCluster30dReturnPct":earliest["preEvent"]["prior30dReturnPct"],
    "baselineMacro":earliest["pastOnlyRiskContext"],
    "btcReturnFirstNewsToFinalNewsPct":rnd(pct(p(prices,lastday),p(prices,firstday-dt.timedelta(days=1)))),
    "initialShock7d":earliest["post"]["7"],
    "initialShock30d":earliest["post"]["30"],
    "firstToLastEventCalendarDays":(lastday-firstday).days,
    "note":"This group is ONE crisis cluster, not many independent positive examples."
  }
 # Predeclared same-year descriptive non-event daily starts excluding <=30d from ANY event
 exclusion=[day(e["date"]) for e in events]
 baselines={}
 for year in (2014,2016,2022):
  candidates=[]
  start=dt.date(year,1,31);end=dt.date(year,12,1)
  current=start
  while current<=end:
   if all(abs((current-eventdate).days)>30 for eventdate in exclusion):
    try:
     f7=future_calc(prices,current,7)
     f30=future_calc(prices,current,30)
     candidates.append({"date":ds(current),
       "down10Within7":f7["minDailyCloseFromPreEventPct"]<=-10,
       "down20Within30":f30["minDailyCloseFromPreEventPct"]<=-20,
       "worst7":f7["minDailyCloseFromPreEventPct"],
       "worst30":f30["minDailyCloseFromPreEventPct"]})
    except ValueError:pass
   current+=dt.timedelta(days=1)
  baselines[str(year)]={"dates":len(candidates),"pctDown10Within7":
   rnd(100*sum(x["down10Within7"] for x in candidates)/len(candidates)) if candidates else None,
   "pctDown20Within30":rnd(100*sum(x["down20Within30"] for x in candidates)/len(candidates)) if candidates else None,
   "medianWorst7Pct":rnd(statistics.median(x["worst7"] for x in candidates)) if candidates else None,
   "medianWorst30Pct":rnd(statistics.median(x["worst30"] for x in candidates)) if candidates else None,
   "warning":"NO_NEWS_LABELS,NOT_CAUSAL_CONTROL,ANY_EVENT_COHORT_SELECTED_EX_POST"}
 result={
  "version":"8.18e","status":"CRYPTO_EVENT_SHOCK_CONTAGION_RETROSPECTIVE_ONLY",
  "researchOnly":True,"noTradingApproval":True,
  "parents":{"daily":{"key":DAILY[0],"sha256":DAILY[1]},
             "macro":{"key":MACRO[0],"sha256":MACRO[1]}},
  "preregistration":{"path":PRE,"sha256":sha(raw)},
  "dailyPriceSource":{"key":archived["r2Key"],"sha256":archived["sha256"],
     "nDaily":len(prices),"notExecutableVolumeData":True},
  "sample":{"events":len(events),"independentEconomicCrisisClusters":len(grouping),
   "warning":"selected known crisis events only, not full news sample or predictive hit rate"},
  "dateLevel":item,"crisisClusters":grouping,"nonEventYearOnlyReference":baselines,
  "volumeVerification":"VOLUME_NOT_MEASURED",
  "untested":["Historical before-event exchange outflow volume","BTC exchange order-book trade sells",
   "Forced derivatives liquidations and actual OI contemporaneous","Public news false alarm rate","Precise publication intraday time",
   "Causal decomposition from macro or other events","Ex ante ability to predict secret FTX/Alameda insolvency"],
  "interpretation":[
   "Ex-post story explains why event risk is missing from a slow Fed/NFCI BTC model, but no evidence this model could predict an unknown insolvency before the first public headline.",
   "Event-date price USD daily fixings are non-executable and may be historically revised.",
   "FTX and mid-2022 contagion occurred during an existing bear market, not a clean healthy BTC baseline.",
   "Some registered event dates are attested in later publications; treat timing DATE_ONLY and never import ex-post size in contemporaneous features.",
   "Overlap means company events within same cluster are NOT independent samples of early crash predictability."],
  "changes":{"Spot":False,"Futures":False,"NAV":False,"Pnl":False,"capital":False,
   "reserve":False,"MASTER":False,"Detector":False,"tradeLimits":False}
 }
 folder=Path("btci_v818e_reports");folder.mkdir(exist_ok=True)
 blob=json.dumps(result,ensure_ascii=False,indent=2).encode()
 (folder/"crypto_crisis_events.json").write_bytes(blob)
 prefix=f"research/btci/v8.18e/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 out_sha=save(s,bucket,prefix+"crypto_crisis_events.json",blob)
 man_sha=save(s,bucket,prefix+"manifest.json",{
  "version":"8.18e","status":"CRISIS_EVENT_STUDY_COMPLETED_RESEARCH_ONLY",
  "reportSha256":out_sha,"preregSha256":sha(raw),"btcSourceSha256":archived["sha256"]})
 brief={"status":"V818E_EVENT_RESEARCH_PASS_R2_READBACK_VERIFIED",
  "prefix":prefix,"reportSha256":out_sha,"manifestSha256":man_sha,
  "clusters":grouping,"events":[{
   "id":x["id"],"date":x["date"],"prior7":x["preEvent"]["prior7dReturnPct"],
   "prior30":x["preEvent"]["prior30dReturnPct"],"day0":x["dayZeroReturnVsPrevDayPct"],
   "after7Worst":x["post"]["7"]["minDailyCloseFromPreEventPct"],
   "after30Worst":x["post"]["30"]["minDailyCloseFromPreEventPct"],
   "priorMacro":x["pastOnlyRiskContext"]} for x in item],
  "reference":baselines}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V818E_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
