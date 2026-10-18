#!/usr/bin/env python3
"""BTCI v8.7: verify and archive complete historical daily source; analyze
77-ish Sunday price-trend flips rather than treat overlapping weeks as independent.
Research only. No permission to modify trading/accounting/portfolio.
"""
import datetime as dt, hashlib, json, math, os, statistics, time
import urllib.parse, urllib.request, urllib.error
from collections import Counter
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG="research/btci_v87_episodic_cycles_archive_prereg_2026-10-18.json"
OLD=("research/btci/v8.6/runs/39130315439-1/extended_history.json",
     "9af82767fa8139685e784c131c075cec553298c4718ed4a40ac41412144248ca")
END=dt.date(2026,10,17)
ASSETS=("btc","eth","sol","bnb","link","xrp","ada","doge")
ALTS=("sol","bnb","link","xrp","ada","doge")
H=(4,13,26,52)

def sha(value):return hashlib.sha256(value).hexdigest()
def f6(value):return round(float(value),6) if value is not None else None
def client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def checked_get(s,b,key,digest):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=digest:raise SystemExit("V87_PARENT_OR_WRITEBACK_SHA_MISMATCH:"+key)
 return json.loads(raw)
def write(s,b,key,raw,ctype="application/json"):
 digest=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType=ctype,Metadata={"sha256":digest,"research-only":"true"})
 verify=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(verify)!=digest:raise SystemExit("V87_CLOUD_READBACK_FAIL:"+key)
 return digest
def fetch_asset(sym):
 query={"assets":sym,"metrics":"PriceUSD","frequency":"1d","start_time":"2010-01-01",
 "end_time":"2026-10-17","page_size":"10000"}
 url="https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?"+urllib.parse.urlencode(query)
 blobs=[];prices={}
 pages=0
 while url:
  if pages>=8:raise SystemExit("V87_TOO_MANY_COINMETRICS_PAGES:"+sym)
  req=urllib.request.Request(url,headers={"User-Agent":"BTCI historical source archive v8.7",
    "Accept":"application/json"})
  with urllib.request.urlopen(req,timeout=40) as r:
   body=r.read(3_500_001)
  if len(body)>3_500_000:raise SystemExit("V87_HTTP_RESPONSE_TOO_LARGE:"+sym)
  info=json.loads(body)
  for item in info.get("data",[]):
   day=dt.date.fromisoformat(item["time"][:10])
   val=item.get("PriceUSD")
   if day>END or val is None:continue
   x=float(val)
   if not math.isfinite(x) or x<=0:raise SystemExit("V87_INVALID_PRICE:"+sym)
   if day in prices:raise SystemExit("V87_DUPLICATE_DAY:"+sym)
   prices[day]=x
  blobs.append(body)
  url=info.get("next_page_url")
  if url and urllib.parse.urlparse(url).hostname not in ("community-api.coinmetrics.io","api.coinmetrics.io"):
   raise SystemExit("V87_UNSAFE_PAGINATION_HOST")
  pages+=1
  time.sleep(0.5)
 dates=sorted(prices)
 if not dates or any(y-x!=dt.timedelta(days=1) for x,y in zip(dates,dates[1:])):
  raise SystemExit("V87_MISSING_SOURCE_DAY:"+sym)
 return prices,blobs

def group(events):
 ret={"n":len(events),"closedEpisodes":sum(not x["durationCensored"] for x in events),
  "rightCensoredEpisodes":sum(x["durationCensored"] for x in events)}
 closed=[e["durationWeeks"] for e in events if not e["durationCensored"]]
 ret["medianClosedDurationWeeks"]=f6(statistics.median(closed)) if closed else None
 for h in H:
  allresults=[e["future"][str(h)] for e in events]
  valid=[x for x in allresults if x["status"]=="OBSERVED"]
  returns=[x["returnPct"] for x in valid]
  adverse=[x["worstDailyClosePct"] for x in valid]
  persistent=[e["survivedWithoutOppositeByWeek"][str(h)] for e in events
              if e["survivedWithoutOppositeByWeek"][str(h)] is not None]
  ret[str(h)]={"observed":len(valid),"rightCensored":len(allresults)-len(valid),
   "medianFutureCloseReturnPct":f6(statistics.median(returns)) if returns else None,
   "positiveFutureReturns":sum(x>0 for x in returns),
   "medianWorstDailyCloseDrawdownPct":f6(statistics.median(adverse)) if adverse else None,
   "persistedCount":sum(persistent),"persistenceEvaluableN":len(persistent),
   "sampleWarning":"LOW_INDEPENDENT_EPISODE_COUNT" if len(events)<20 else "DESCRIPTIVE_RETROSPECTIVE_ONLY"}
 return ret

def broadening(weeks,index):
 # Competing outcomes within 13 weeks only. Missing prelisting alt data is UNKNOWN, not 0.
 end=index+13
 if end>=len(weeks):return {"status":"RIGHT_CENSORED"}
 unknown=False
 for lag in range(1,14):
  row=weeks[index+lag]
  breadth=row["altBreadth"]
  is_broad=breadth["status"]=="AVAILABLE" and breadth.get("broadParticipation") is True
  if breadth["status"]!="AVAILABLE":unknown=True
  if is_broad or not row["weeklyTrendConfirmed"]:
   if unknown:
    return {"status":"DATA_CENSORED_BREADTH","firstKnownEvent":"BROAD" if is_broad else "LOST_TREND",
      "weeksFromEntry":lag}
   return {"status":"BROAD_FIRST" if is_broad else "LOST_TREND_FIRST","weeksFromEntry":lag}
 if unknown:return {"status":"DATA_CENSORED_BREADTH"}
 return {"status":"NEITHER_WITHIN_13W"}

def main():
 prereg=(ROOT/PREREG).read_bytes()
 pp=json.loads(prereg)
 if (pp["version"]!="8.7" or
  pp["frozenSource"]!={"key":OLD[0],"sha256":OLD[1]} or
  pp["sourceArchive"]["assets"]!=list(ASSETS)):
  raise SystemExit("V87_PREREG_NOT_FROZEN")
 s=client();bucket=os.environ["R2_BUCKET"]
 parent=checked_get(s,bucket,*OLD)
 w=parent["weeklyRows"]
 if parent["version"]!="8.6" or len(w)!=814 or w[0]["date"]!="2011-03-13" or w[-1]["date"]!="2026-10-11":
  raise SystemExit("V87_FROZEN_WEEKLY_PARENT_CHANGED")
 all_weeks=[dt.date.fromisoformat(z["date"]) for z in w]
 if any(q-p!=dt.timedelta(days=7) for p,q in zip(all_weeks,all_weeks[1:])):
  raise SystemExit("V87_WEEKLY_NOT_GAPLESS")
 prices={};rawpages={};audit={}
 for sym in ASSETS:
  daily, pages=fetch_asset(sym)
  provenance=parent["coinMetricsSource"][sym]
  dates=sorted(daily)
  if (len(daily)!=provenance["days"] or
      dates[0].isoformat()!=provenance["first"] or
      dates[-1].isoformat()!=provenance["last"] or
      provenance["missingIntervals"]!=0):
   raise SystemExit("V87_COINMETRICS_COVERAGE_CHANGED:"+sym)
  prices[sym]=daily;rawpages[sym]=pages
  audit[sym]={"days":len(daily),"first":dates[0].isoformat(),
              "last":dates[-1].isoformat(),"rawPages":len(pages)}
  print("V87_ARCHIVE_SOURCE_OK",sym,len(daily),flush=True)
 # All 814 weekly price levels and all available 30d breadth definitions must replay exactly.
 for rec in w:
  day=dt.date.fromisoformat(rec["date"])
  value=prices["btc"].get(day)
  if value is None or abs(value-rec["btcFixingPriceUSD"])>0.00001:
   raise SystemExit("V87_BTC_WEEKLY_PRICE_MISMATCH:"+rec["date"])
  breadth=rec["altBreadth"]
  prev=day-dt.timedelta(days=30)
  eligible=all(day in prices[sym] and prev in prices[sym] for sym in ASSETS)
  if eligible!=(breadth["status"]=="AVAILABLE"):
   raise SystemExit("V87_BREADTH_COVERAGE_CHANGED:"+rec["date"])
  if eligible:
   base=prices["btc"][day]/prices["btc"][prev]
   rel={a:((prices[a][day]/prices[a][prev])/base-1)*100 for a in ASSETS if a!="btc"}
   count=sum(rel[sym]>0 for sym in ALTS)
   broad=rel["eth"]>0 and count>=4
   if count!=breadth["outperformingAlts"] or broad!=breadth["broadParticipation"]:
    raise SystemExit("V87_BREADTH_REPLAY_MISMATCH:"+rec["date"])
 # Compute independent-entry-like events from frozen weekly labels only. No future label is
 # used to define an event. The duration and future outcomes are displayed AFTER the event.
 change_indices=[i for i in range(1,len(w)) if w[i]["weeklyTrendConfirmed"]!=w[i-1]["weeklyTrendConfirmed"]]
 if len(change_indices)!=77:raise SystemExit("V87_WEEKLY_TRANSITION_COUNT_CHANGED")
 events=[]
 for j,i in enumerate(change_indices):
  rec=w[i];trend=rec["weeklyTrendConfirmed"]
  next_index=change_indices[j+1] if j+1<len(change_indices) else None
  duration=next_index-i if next_index is not None else len(w)-i
  e={"date":rec["date"],"index":i,
      "event":"TREND_ENTER" if trend else "TREND_EXIT",
      "previousConfirmedTrend":not trend,"confirmedTrend":trend,
      "sourceReferenceCloseUSD":rec["btcFixingPriceUSD"],
      "durationWeeks":duration,
      "durationCensored":next_index is None,
      "nextTransitionDate":w[next_index]["date"] if next_index is not None else None,
      "future":{str(h):rec["future"][str(h)] for h in H},
      "survivedWithoutOppositeByWeek":{str(h):(
         (duration>h) if i+h<len(w) else None) for h in H},
      "btcPhaseInterpretation":"weekly price trend flag, not macro bull/bear cycle"}
  if trend:e["altBroadeningNext13Weeks"]=broadening(w,i)
  events.append(e)
 entries=[e for e in events if e["event"]=="TREND_ENTER"]
 exits=[e for e in events if e["event"]=="TREND_EXIT"]
 era_ranges=[("2011-2012","2011-01-01","2013-01-01"),
 ("2013-2016","2013-01-01","2017-01-01"),
 ("2017-2019","2017-01-01","2020-01-01"),
 ("2020-2023","2020-01-01","2024-01-01"),
 ("2024-2026","2024-01-01","2027-01-01")]
 er={}
 for name,lo,hi in era_ranges:
  er[name]={"entries":group([e for e in entries if lo<=e["date"]<hi]),
   "exits":group([e for e in exits if lo<=e["date"]<hi])}
 # 13-week fixed greedy spacing anchored to earliest trend-entry event.
 spaced=[];last=-999
 for e in entries:
  if e["index"]-last>=13:spaced.append(e);last=e["index"]
 from collections import Counter
 result={"version":"8.7","status":"LONG_HISTORY_TREND_EPISODES_AND_NORMALIZED_DAILY_ARCHIVE",
  "researchOnly":True,"noTradingAuthority":True,"cutoffBTCWeeklyUTC":"2026-10-11",
  "preregistration":{"path":PREREG,"sha256":sha(prereg)},
  "input":{"key":OLD[0],"sha256":OLD[1]},
  "rawDailyArchiveSource":"Coin Metrics public Community API PriceUSD; current retrospective reference rate, NOT a point-in-time version",
  "totalWeeks":len(w),"trendTransitions":len(events),
  "trendEntries":group(entries),"trendExits":group(exits),
  "byEra":er,"trendEntry13WeekSpaced":group(spaced),
  "breadthAfterEntries13w":dict(Counter(e["altBroadeningNext13Weeks"]["status"] for e in entries)),
  "recentEvents":events[-18:],"allEvents":events,
  "sourceCoverage":audit,
  "current":{"lastSunday":w[-1]["date"],"weeklyTrend":w[-1]["weeklyTrendConfirmed"],
   "lastTransition":events[-1]["date"],"lastTransitionType":events[-1]["event"],
   "lastBreadth":w[-1]["altBreadth"]},
  "knownLimitations":[
   "77 historical transitions from 16 years are NOT 77 independent market cycles",
   "CoinMetrics backfilled daily fixings are not true historical release vintages nor executable spot prices",
   "Source raw and normalized files archived now. Original Binance monthly ZIP samples and macro PIT observations are not copied by this step",
   "Only complete universe breadth dates eligible: no silent before-listing zero for altcoins",
   "Trends use 30-week SMA and four-week close extrema, NOT weekly wick highs/lows",
   "4/13/26/52-week return windows overlap between events and depend on same historical market",
   "Withheld no independent out-of-sample period: diagnostic, not calibrated signal or trade approval",
   "No modifications to runtime Detector, Spot, Futures, NAV, P&L, reserve, capital or risk limits"]}
 root=f"research/btci/v8.7/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 archive_manifest={"version":"8.7","status":"DAILY_SOURCE_ARCHIVE_PASS_READBACK",
   "source":"Coin Metrics Community API PriceUSD","originalSourceVintagesVerified":False,
   "capturedAtUTC":dt.datetime.now(dt.timezone.utc).isoformat(),
   "asOfUTC":"2026-10-17","assets":{}}
 for sym in ASSETS:
  rawobjects=[]
  for k,body in enumerate(rawpages[sym],start=1):
   key=root+f"source/{sym}/raw_api_page_{k}.json"
   dig=write(s,bucket,key,body)
   rawobjects.append({"r2Key":key,"sha256":dig,"bytes":len(body)})
  norm=json.dumps([{"day":d.isoformat(),"priceUSD":x}
    for d,x in sorted(prices[sym].items())],ensure_ascii=False,separators=(",",":")).encode()
  key=root+f"source/{sym}/normalized_daily_priceusd.json"
  dig=write(s,bucket,key,norm)
  archive_manifest["assets"][sym]={
   **audit[sym],"normalized":{"r2Key":key,"sha256":dig,"bytes":len(norm)},
   "rawPages":rawobjects}
 akey=root+"archive_manifest.json"
 ama=write(s,bucket,akey,json.dumps(archive_manifest,ensure_ascii=False,indent=2).encode())
 result["sourceArchiveManifest"]={"r2Key":akey,"sha256":ama}
 rjson=json.dumps(result,ensure_ascii=False,indent=2).encode()
 directory=Path("btci_v87_reports");directory.mkdir(exist_ok=True)
 (directory/"episode_report.json").write_bytes(rjson)
 (directory/"archive_manifest.json").write_text(json.dumps(archive_manifest,ensure_ascii=False,indent=2))
 report_digest=write(s,bucket,root+"episodes.json",rjson)
 manifest={"version":"8.7","researchOnly":True,"status":"ARCHIVE_AND_EVENT_RESEARCH_PASS",
  "reportSha256":report_digest,"archiveManifestSha256":ama,
  "parentSha256":OLD[1],"prefix":root}
 msha=write(s,bucket,root+"manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2).encode())
 summary={"status":"V87_DAILY_ARCHIVE_AND_EPISODES_PASS_WRITEBACK_VERIFIED",
   "prefix":root,"reportSha256":report_digest,"archiveManifestSha256":ama,
   "manifestSha256":msha,"totalWeeks":len(w),"transitions":len(events),
   "entries":result["trendEntries"],"exits":result["trendExits"],
   "era":er,"spaced":result["trendEntry13WeekSpaced"],
   "breadth13w":result["breadthAfterEntries13w"],
   "archive":audit,"recent":result["recentEvents"][-8:],"current":result["current"]}
 (directory/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V87_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write("# BTCI 8.7 — исторические недельные переходы + исходный дневной архив\n\n"
    f"Архив 8 источников: COMPLETE READBACK, дата отсечения: 2026-10-17 UTC\n\n"
    f"Смен тренда: {len(events)}, входов: {len(entries)}, выходов: {len(exits)}\n\n"
    f"R2: {root}\n\nSHA256: {report_digest}\n")
if __name__=="__main__":main()
