#!/usr/bin/env python3
"""BTCI 8.18g: sixteen global macro policy, pandemic, war announcements.
Past-only BTC fixing & macro, date-level descriptive response not causal news forecast.
"""
import datetime as dt,hashlib,json,math,os,statistics
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818g_global_macro_shock_prereg_2026-10-19.json"
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
 if sha(raw)!=h:raise SystemExit("V818G_ORIGINAL_SHA_CHANGED:"+k)
 return json.loads(raw)
def save(s,b,k,raw):
 blob=raw if isinstance(raw,bytes) else json.dumps(raw,ensure_ascii=False,indent=2).encode()
 h=sha(blob)
 s.put_object(Bucket=b,Key=k,Body=blob,ContentType="application/json",Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=k)["Body"].read())!=h:raise SystemExit("V818G_SHA_REREAD_MISMATCH:"+k)
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
 expect={"daily":{"key":DAILY[0],"sha256":DAILY[1]},
  "macro":{"key":MACRO[0],"sha256":MACRO[1]},
  "crypto":{"key":"research/btci/v8.18e/runs/39215131167-1/crypto_crisis_events.json",
  "sha256":"78608d81f46d52b520a51377068b7221d7bb957fc6d6cba689afcf41ae230bff"}}
 if pr["version"]!="8.18g" or pr["parents"]!=expect:raise SystemExit("V818G_PREREG_CHANGED")
 s=r2();bucket=os.environ["R2_BUCKET"]
 archive=checked(s,bucket,*DAILY);macro=checked(s,bucket,*MACRO)
 if archive["version"]!="8.7" or macro["version"]!="8.17.1" or len(macro["weeklyPanel"])!=684:
  raise SystemExit("V818G_PARENT_UNEXPECTED")
 archived=archive["assets"]["btc"]["normalized"]
 rawbtc=s.get_object(Bucket=bucket,Key=archived["r2Key"])["Body"].read()
 if sha(rawbtc)!=archived["sha256"]:raise SystemExit("V818G_BTC_DAILY_SOURCE_CHANGED")
 prices={day(x["day"]):float(x["priceUSD"]) for x in json.loads(rawbtc)}
 if len(prices)<5900 or max(prices)<day("2026-10-17"):raise SystemExit("V818G_PRICE_HISTORY_INCOMPLETE")
 rows=macro["weeklyPanel"]
 if [x["date"] for x in rows]!=sorted(x["date"] for x in rows):
  raise SystemExit("V818G_MACRO_ROWS_NOT_SORTED")
 events=[{**x,"episode":x["cluster"]} for x in pr["events"]]
 if len(events)!=16 or len({x["id"] for x in events})!=16:raise SystemExit("V818G_EVENT_REGISTRATION_CHANGED")
 horizons=(1,3,7,14,30,90)
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
  print("V818G_EVENT",e["id"],"btcDay0",obj["dayZeroReturnVsPrevDayPct"],
    "worstNext7d",obj["post"]["7"]["minDailyCloseFromPreEventPct"],
    "macro",obj["pastOnlyRiskContext"].get("strictAllPositive"),flush=True)
 grouping={}
 for episode in sorted({x["episode"] for x in events}):
  cohort=[x for x in item if x["episode"]==episode]
  earliest=cohort[0];latest=cohort[-1]
  firstday=day(earliest["date"]);lastday=day(latest["date"])
  grouping[episode]={
    "events":[x["id"] for x in cohort],
    "firstDatedOfficialPublicationInRegisteredCluster":earliest["date"],"lastDatedOfficialPublicationInRegisteredCluster":latest["date"],
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
 for year in (2018,2019,2020,2022,2023,2024,2025):
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
   "warning":"NON_EVENT_SAME_YEAR_REFERENCE_NOT_CAUSAL"
 result={
  "version":"8.18g","status":"GLOBAL_MACRO_SHOCK_DATE_STUDY_RESEARCH_ONLY",
  "researchOnly":True,"noTradingApproval":True,
  "parents":{"daily":{"key":DAILY[0],"sha256":DAILY[1]},
             "macro":{"key":MACRO[0],"sha256":MACRO[1]}},
  "preregistration":{"path":PRE,"sha256":sha(raw)},
  "dailyPriceSource":{"key":archived["r2Key"],"sha256":archived["sha256"],
     "nDaily":len(prices),"notExecutableVolumeData":True},
  "sample":{"events":len(events),"independentEconomicCrisisClusters":len(grouping),
   "warning":"selected known crisis events only, not full news sample or predictive hit rate"},
  "dateLevel":item,"crisisClusters":grouping,"nonEventYearOnlyReference":baselines,
  "volumeVerification":"GLOBAL_NEWS_TURNOVER_NOT_MEASURED",
  "untested":["Exact event publication hour for most announcements","Intraday BTC repricing", 
   "S&P500 Treasury gold oil cross-market reaction", "All global headlines for false alarm rate",
   "Original vintage market surprise consensus", "Causal decomposition of tariff war pandemic and military stress"],
  "interpretation":[
   "Global risk shocks and Fed policy responses are different economic mechanisms and can overlap; no causal attribution from date windows.",
   "BTC reference price fixing 24/7, daily UTC and event official publication time mostly unknown; weekend events have unique stock market timing.",
   "WHO March11 pandemic status was known after weeks of COVID spread, not an unprecedented first market warning.",
   "Fed March3, March15 and March23 eased policy REACTING TO pandemic, not independent randomized bullish events.",
   "April9 2025 included partial tariff suspension AND escalation versus China, cannot classify as purely positive shock.",
   "Multiple events in same macro crisis block are not independent samples.",
   "Historical headline dates selected with hindsight; rates do not measure news prediction skill."],
  "changes":{"Spot":False,"Futures":False,"NAV":False,"Pnl":False,"capital":False,
   "reserve":False,"MASTER":False,"Detector":False,"tradeLimits":False}
 }
 folder=Path("btci_v818e_reports");folder.mkdir(exist_ok=True)
 blob=json.dumps(result,ensure_ascii=False,indent=2).encode()
 (folder/"global_macro_shocks.json").write_bytes(blob)
 prefix=f"research/btci/v8.18g/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 out_sha=save(s,bucket,prefix+"global_macro_shocks.json",blob)
 man_sha=save(s,bucket,prefix+"manifest.json",{
  "version":"8.18g","status":"GLOBAL_MACRO_EVENT_RESEARCH_COMPLETED",
  "reportSha256":out_sha,"preregSha256":sha(raw),"btcSourceSha256":archived["sha256"]})
 brief={"status":"V818G_EVENT_RESEARCH_PASS_R2_READBACK_VERIFIED",
  "prefix":prefix,"reportSha256":out_sha,"manifestSha256":man_sha,
  "clusters":grouping,"events":[{
   "id":x["id"],"date":x["date"],"prior7":x["preEvent"]["prior7dReturnPct"],
   "prior30":x["preEvent"]["prior30dReturnPct"],"day0":x["dayZeroReturnVsPrevDayPct"],
   "after7Worst":x["post"]["7"]["minDailyCloseFromPreEventPct"],
   "after30Worst":x["post"]["30"]["minDailyCloseFromPreEventPct"],
   "priorMacro":x["pastOnlyRiskContext"]} for x in item],
  "reference":baselines}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V818G_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
