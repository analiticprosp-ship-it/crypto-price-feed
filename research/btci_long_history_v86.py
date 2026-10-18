#!/usr/bin/env python3
"""BTCI v8.6 -- BTC long-history research with verifiable independent source families.
PriceUSD Coin Metrics reference fixing != Binance Perp or executable spot. No trading.
"""
import datetime as dt,hashlib,json,math,os,statistics,time,urllib.parse,urllib.request,urllib.error,zipfile,io,csv
from collections import Counter
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG="research/btci_v86_long_history_prereg_2026-10-18.json"
OLD=("research/btci/v8.3/runs/39126819412-1/panel.json",
"9f90e6974e43f74a3af0bdf562d5e865b56c01565cb83d9b177aae2f81cc5479")
ASSETS=("btc","eth","sol","bnb","link","xrp","ada","doge")
H=(4,13,26,52)
ASOF=dt.date(2026,10,17)
SAMPLES=("2017-08","2017-09","2018-01","2019-12","2020-01","2026-09")
def hsh(data):return hashlib.sha256(data).hexdigest()
def rnd(x):return round(float(x),6) if x is not None else None
def client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def read(s,b,key,expected):
 blob=s.get_object(Bucket=b,Key=key)["Body"].read()
 if hsh(blob)!=expected:raise SystemExit("V86_SOURCE_SHA_MISMATCH:"+key)
 return json.loads(blob)
def save(s,b,key,obj):
 raw=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False,indent=2).encode()
 sha=hsh(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
  Metadata={"sha256":sha,"research-only":"true"})
 if hsh(s.get_object(Bucket=b,Key=key)["Body"].read())!=sha:
  raise SystemExit("V86_WRITEBACK_UNVERIFIED")
 return sha
def http(url,bytes_limit=2500000):
 req=urllib.request.Request(url,headers={"User-Agent":"BTCI-2026-History-Research/8.6","Accept":"application/json,text/plain,*/*"})
 with urllib.request.urlopen(req,timeout=35) as response:
  body=response.read(bytes_limit+1)
 if len(body)>bytes_limit:raise ValueError("RESPONSE_TOO_BIG")
 return body
def coinmetrics(asset):
 query={"assets":asset,"metrics":"PriceUSD","frequency":"1d",
  "start_time":"2010-01-01","end_time":"2026-10-17","page_size":"10000"}
 url="https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?"+urllib.parse.urlencode(query)
 price={};pages=0;rawhash=[]
 while url:
  if pages>=8:raise ValueError("TOO_MANY_COINMETRICS_PAGES")
  last_exc=None
  for retry in range(3):
   try:content=http(url,3500000);break
   except urllib.error.HTTPError as exc:
    last_exc=exc
    if exc.code==429:
     time.sleep(2+retry*4);continue
    raise
  else:raise last_exc
  j=json.loads(content)
  rawhash.append(hsh(content))
  for row in j.get("data",[]):
   day=dt.date.fromisoformat(row["time"][:10])
   val=row.get("PriceUSD")
   if val is None:continue
   num=float(val)
   if not math.isfinite(num) or num<=0:raise ValueError("BAD_PRICEUSD")
   if day>ASOF:continue
   if day in price:raise ValueError("DUPLICATE_COINMETRICS_DAY")
   price[day]=num
  pages+=1
  url=j.get("next_page_url")
  if url and urllib.parse.urlparse(url).hostname not in ("community-api.coinmetrics.io","api.coinmetrics.io"):
   raise ValueError("UNTRUSTED_PAGINATION_HOST")
  time.sleep(0.8)
 dates=sorted(price)
 breaks=[(x.isoformat(),y.isoformat()) for x,y in zip(dates,dates[1:]) if (y-x).days!=1]
 return price,{"status":"AVAILABLE" if dates else "EMPTY",
  "first":dates[0].isoformat() if dates else None,
  "last":dates[-1].isoformat() if dates else None,
  "days":len(price),"missingIntervals":len(breaks),
  "firstBreaks":breaks[:10],"pages":pages,"responseSha256":rawhash,
  "dailyCloseAvailabilityRule":"Use daily fixing only AFTER following UTC midnight; no historical published vintage verification"}

def binance_sample(month):
 pair="BTCUSDT"
 fname=f"{pair}-1d-{month}.zip"
 url=f"https://data.binance.vision/data/spot/monthly/klines/{pair}/1d/{fname}"
 try:
  blob=http(url,200000)
  dig=hsh(blob)
  chk=http(url+".CHECKSUM",300).decode().split()[0].lower()
  if dig!=chk:raise ValueError("UPSTREAM_SHA256_MISMATCH")
  with zipfile.ZipFile(io.BytesIO(blob)) as z:
   if z.testzip() is not None:raise ValueError("ZIP_CRC_BAD")
   files=[x for x in z.namelist() if x.endswith(".csv")]
   if len(files)!=1:raise ValueError("ZIP_FILES_BAD")
   with z.open(files[0]) as stream:
    rows=list(csv.reader(io.TextIOWrapper(stream,encoding="utf-8-sig")))
  parsed=[]
  for row in rows:
   if not row or not row[0].isdigit():continue
   stamp=int(row[0])
   if stamp>10**15:stamp//=1000
   d=dt.datetime.fromtimestamp(stamp/1000,dt.timezone.utc).date()
   parsed.append(d)
  if len(parsed)!=len(set(parsed)):raise ValueError("DUPLICATE_SPOT_DAYS")
  return {"status":"ZIP_CRC_AND_SHA_VERIFIED","month":month,"dates":[d.isoformat() for d in parsed[:2]],
    "last":parsed[-1].isoformat() if parsed else None,
    "countDailyBars":len(parsed),"sha256":dig,
    "source":url}
 except Exception as exc:
  return {"status":"NOT_VERIFIED","month":month,"reason":type(exc).__name__+":"+str(exc)[:200],"source":url}

def available_weekly(btc):
 if not btc:return []
 first=min(btc);last=min(max(btc),ASOF)
 dates=[first+dt.timedelta(days=i) for i in range((last-first).days+1)]
 weekly=[]
 for d in dates:
  if d.weekday()!=6:continue
  prior=[d-dt.timedelta(days=i) for i in range(238)]
  if any(z not in btc for z in prior):continue
  # Sufficient uninterrupted 34 weeks (current and 33 previous Sundays).
  sundays=[btc[d-dt.timedelta(days=7*i)] for i in range(34)]
  ma=sum(sundays[0:30])/30
  prior4=sum(sundays[4:34])/30
  rising=max(sundays[0:4])>max(sundays[4:8]) and min(sundays[0:4])>min(sundays[4:8])
  trend=sundays[0]>ma and ma>prior4 and rising
  future={}
  for weeks in H:
   end=d+dt.timedelta(weeks=weeks)
   needed=[d+dt.timedelta(days=i) for i in range(1,weeks*7+1)]
   if end>last or any(x not in btc for x in needed):
    future[str(weeks)]={"status":"RIGHT_CENSORED"}
   else:
    path=[btc[x] for x in needed]
    future[str(weeks)]={"status":"OBSERVED",
      "returnPct":rnd(100*(path[-1]/btc[d]-1)),
      "worstDailyClosePct":rnd(100*(min(path)/btc[d]-1))}
  weekly.append({"date":d.isoformat(),"btcFixingPriceUSD":rnd(btc[d]),
    "weeklyTrendConfirmed":trend,"sma30w":rnd(ma),
    "sma30Slope4weekPct":rnd(100*(ma/prior4-1)),
    "future":future})
 return weekly

def describe(rows):
 z={"weeks":len(rows)}
 for weeks in H:
  s=[x["future"][str(weeks)]["returnPct"] for x in rows if x["future"][str(weeks)]["status"]=="OBSERVED"]
  z[str(weeks)]={"n":len(s),"rightCensored":len(rows)-len(s),
    "medianPct":rnd(statistics.median(s)) if s else None,
    "positiveCount":sum(x>0 for x in s)}
 return z

def main():
 pre=(ROOT/PREREG).read_bytes();p=json.loads(pre)
 if p["version"]!="8.6" or p["immutableV83"]!={"key":OLD[0],"sha256":OLD[1]}:
  raise SystemExit("V86_PREREG_CHANGED")
 s=client();b=os.environ["R2_BUCKET"]
 v83=read(s,b,*OLD)
 if v83["version"]!="8.3" or len(v83["weeklyPanel"])!=321:
  raise SystemExit("V86_V83_BASE_CHANGED")
 sources={};prices={}
 for sym in ASSETS:
  try:
   rows,meta=coinmetrics(sym)
   sources[sym]=meta;prices[sym]=rows
  except Exception as exc:
   sources[sym]={"status":"UNAVAILABLE","reason":type(exc).__name__+":"+str(exc)[:250]}
   prices[sym]={}
  print("SOURCE_AUDIT",sym,json.dumps(sources[sym]),flush=True)
 spot=[binance_sample(m) for m in SAMPLES]
 btc=prices["btc"]
 weekly=available_weekly(btc)
 if weekly:
  for q in weekly:
   d=dt.date.fromisoformat(q["date"])
   d30=d-dt.timedelta(days=30)
   if any(d not in prices[a] or d30 not in prices[a] for a in ASSETS):
    q["altBreadth"]={"status":"UNKNOWN","missing":[a for a in ASSETS if d not in prices[a] or d30 not in prices[a]]}
   else:
    bfac=prices["btc"][d]/prices["btc"][d30]
    rel={a:100*((prices[a][d]/prices[a][d30])/bfac-1) for a in ASSETS if a!="btc"}
    count=sum(rel[a]>0 for a in ("sol","bnb","link","xrp","ada","doge"))
    q["altBreadth"]={"status":"AVAILABLE","ethVsBtcPct":rnd(rel["eth"]),
        "outperformingAlts":count,"broadParticipation":rel["eth"]>0 and count>=4}
 oldpanel={q["sundayClosedUTC"]:q for q in v83["weeklyPanel"]}
 matches=[]
 for q in weekly:
  other=oldpanel.get(q["date"])
  if other:
   matches.append({"date":q["date"],"referenceBTCConfirmed":q["weeklyTrendConfirmed"],
      "futuresBTCConfirmed":other["weekly"]["weeklyTrendConfirmed"],
      "same":q["weeklyTrendConfirmed"]==other["weekly"]["weeklyTrendConfirmed"]})
 transitions=[]
 for earlier,later in zip(weekly,weekly[1:]):
  if later["weeklyTrendConfirmed"]!=earlier["weeklyTrendConfirmed"]:
   transitions.append({"date":later["date"],"from":earlier["weeklyTrendConfirmed"],
                       "to":later["weeklyTrendConfirmed"],"future":later["future"]})
 eras=[("2010-2012","2010-01-01","2013-01-01"),
 ("2013-2016","2013-01-01","2017-01-01"),
 ("2017-2019","2017-01-01","2020-01-01"),
 ("2020-2023","2020-01-01","2024-01-01"),
 ("2024-2026","2024-01-01","2027-01-01")]
 perera={}
 for name,st,en in eras:
  rs=[x for x in weekly if st<=x["date"]<en]
  perera[name]={"all":describe(rs),
   "trendConfirmed":describe([x for x in rs if x["weeklyTrendConfirmed"]]),
   "trendNotConfirmed":describe([x for x in rs if not x["weeklyTrendConfirmed"]]),
   "fullAltBreadthWeeks":sum(x["altBreadth"]["status"]=="AVAILABLE" for x in rs),
   "transitions":sum(st<=x["date"]<en for x in transitions)}
 result={"version":"8.6","status":"EXTENDED_LONG_HISTORY_RESEARCH_PASS" if weekly and weekly[0]["date"]<"2020-01-01" else "EXTENDED_HISTORY_COVERAGE_ONLY",
   "researchOnly":True,"sourceMarketFamily":"COINMETRICS_PRICEUSD_REFERENCE_NOT_TRADABLE_SPOT_OR_PERPETUAL",
   "asOfUTC":"2026-10-17","preregSha256":hsh(pre),
   "parent":{"v83":{"key":OLD[0],"sha256":OLD[1]}},
   "coinMetricsSource":sources,"binanceSpotSampleArchiveAudit":spot,
   "eligibleWeeks":len(weekly),"firstEligibleSunday":weekly[0]["date"] if weekly else None,
   "lastEligibleSunday":weekly[-1]["date"] if weekly else None,
   "byEra":perera,
   "trendTransitions":transitions,"transitionCount":len(transitions),
   "matchedWeeklyPanel":{"n":len(matches),"discordantCount":sum(not x["same"] for x in matches),
     "discordantExamples":[x for x in matches if not x["same"]][:16]},
   "weeklyRows":weekly,
   "caveats":[
      "PriceUSD is a composite reference fixing, not on-venue Spot executable mid and not Binance futures. Never merge into old v8.3 series",
      "Reference rate may have past revisions, source actual availability/vintage not proven",
      "Use daily report price on next UTC midnight only; Sundays represent completed observations",
      "Missing alt PriceUSD prelisting stays UNKNOWN; no invented full market alt breadth",
      "Full-year windows overlapping, dates correlated; exploration NOT OOS",
      "Single-current subset of surviving assets causes survivorship bias",
      "Six months of Binance spot archives tested do not prove full archive complete",
      "No historical ETF before Jan2024; release-timed ALFRED/Fed uncollected in this specific job",
      "Zero trades; no changes to Futures, Spot, NAV, P&L, reserve, capital or limits"]}
 folder=Path("btci_v86_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(result,ensure_ascii=False,indent=2).encode()
 (folder/"extended_history.json").write_bytes(raw)
 root=f"research/btci/v8.6/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 digest=save(s,b,root+"extended_history.json",raw)
 m=save(s,b,root+"manifest.json",{"version":"8.6","researchOnly":True,"status":result["status"],
  "reportSha256":digest,"prefix":root,"preregSha256":hsh(pre)})
 brief={"status":result["status"]+"_WRITEBACK_VERIFIED","prefix":root,
  "reportSha256":digest,"manifestSha256":m,"coinMetrics":sources,
  "spotSample":spot,
  "eligibleWeeks":len(weekly),"first":result["firstEligibleSunday"],"last":result["lastEligibleSunday"],
  "byEra":perera,"crossSource":result["matchedWeeklyPanel"],
  "transitionCount":len(transitions),"latestWeekly":weekly[-1] if weekly else None}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V86_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write(f"# BTCI v8.6 -- исторический горизонт\n\nСтатус: {result['status']}\n\n"
    f"Доступных недель: {len(weekly)}\n\nSHA256: {digest}\n\nR2: {root}\n\n")
if __name__=="__main__":main()
