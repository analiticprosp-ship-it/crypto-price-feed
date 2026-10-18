#!/usr/bin/env python3
"""BTCI v8.5: backfilled Farside ETF-flow provenance and *exploratory* past-only week join.
Current historical table cannot prove data vintages. Never count as validated OOS.
Research-only; no trading, NAV, Futures, portfolio or policy writes.
"""
import datetime as dt, hashlib, io, json, os, re, statistics, urllib.request
from collections import defaultdict, Counter
from pathlib import Path
import boto3
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
P="research/btci_v85_external_factor_prereg_2026-10-18.json"
V83=("research/btci/v8.3/runs/39126819412-1/panel.json",
     "9f90e6974e43f74a3af0bdf562d5e865b56c01565cb83d9b177aae2f81cc5479")
V84=("research/btci/v8.4/runs/39127920489-1/leadlag.json",
     "d834e42dd052b30fa337aad278c0a3dd5141e663efec301e49237140414b495d")
URL="https://farside.co.uk/bitcoin-etf-flow-all-data/"
CATS=("BTC_WEEKLY_CONFIRMED_NARROW","BTC_WEEKLY_CONFIRMED_PLUS_BROAD_PARTICIPATION","BTC_WEEKLY_NOT_CONFIRMED","INSUFFICIENT_DATA")

def sha(v):return hashlib.sha256(v).hexdigest()
def f6(x):return round(float(x),6) if x is not None else None
def cli():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,key,h):
 blob=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(blob)!=h:raise SystemExit("V85_PARENT_SHA_CHANGED:"+key)
 return json.loads(blob)
def write(s,b,key,obj):
 raw=obj if isinstance(obj,bytes) else json.dumps(obj,indent=2,ensure_ascii=False).encode()
 digest=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
              Metadata={"sha256":digest,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=digest:
  raise SystemExit("V85_R2_WRITEBACK_VERIFY_FAILED")
 return digest
def prereg():
 raw=(ROOT/P).read_bytes()
 p=json.loads(raw)
 if p["version"]!="8.5" or p["parent"]!={"v83":{"key":V83[0],"sha256":V83[1]},
                                        "v84":{"key":V84[0],"sha256":V84[1]}}:
  raise SystemExit("V85_PREREG_CHANGED")
 return sha(raw)
def number(text):
 s=text.strip().replace(",","").replace("\u2212","-").replace("−","-")
 if s=="-" or not s:return None
 if s.startswith("(") and s.endswith(")"):s="-"+s[1:-1]
 return float(s)
def collect_farside():
 req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0 (research provenance check)",
  "Accept":"text/html,application/xhtml+xml"})
 with urllib.request.urlopen(req,timeout=40) as response:
  raw=response.read(5_000_001)
 if len(raw)>5_000_000:raise ValueError("HTML_TOO_LARGE")
 soup=BeautifulSoup(raw,"html.parser")
 tables=soup.find_all("table")
 collected=[]
 for table in tables:
  rows=[]
  for tr in table.find_all("tr"):
   cells=tr.find_all(["td","th"])
   if len(cells)<3:continue
   name=cells[0].get_text(" ",strip=True)
   try: day=dt.datetime.strptime(name,"%d %b %Y").date()
   except ValueError:continue
   val=number(cells[-1].get_text(" ",strip=True))
   if val is None:raise ValueError("DAILY_TOTAL_MISSING:"+name)
   rows.append({"day":day.isoformat(),"flowMillionUSD":f6(val)})
  if len(rows)>len(collected):collected=rows
 if len(collected)<450:raise ValueError("MISSING_FULL_DAILY_TABLE")
 days=[row["day"] for row in collected]
 if len(days)!=len(set(days)):raise ValueError("DUPLICATE_DATES")
 collected.sort(key=lambda x:x["day"])
 if collected[0]["day"]!="2024-01-11" or collected[-1]["day"]<"2026-10-16" or collected[-1]["day"]>"2026-10-18":
  raise ValueError("COVERAGE_OR_FUTURE_DATA_MISMATCH")
 return collected,sha(raw)

def describe(rows):
 ar4=[x["outcomes"]["4"]["closeReturnPct"] for x in rows if x["outcomes"]["4"]["status"]=="OBSERVED"]
 ar13=[x["outcomes"]["13"]["closeReturnPct"] for x in rows if x["outcomes"]["13"]["status"]=="OBSERVED"]
 def series(xs):
  return {"n":len(xs),"medianPct":f6(statistics.median(xs)) if xs else None,
    "positiveCount":sum(x>0 for x in xs)}
 return {"weeks":len(rows),"4w":series(ar4),"13w":series(ar13),
   "noPredictiveClaim":True,"PIT":"UNVERIFIED_CURRENT_BACKFILL"}
def group(rows):
 return {"eligibleBaseline":describe(rows),
  "bySign5":{"positive":describe([x for x in rows if x["sign5"]=="POSITIVE"]),
             "negative":describe([x for x in rows if x["sign5"]=="NEGATIVE"]),
             "zero":describe([x for x in rows if x["sign5"]=="ZERO"])},
  "byRegimeAndSign5":{cat:{"positive":describe([x for x in rows if x["category"]==cat and x["sign5"]=="POSITIVE"]),
   "negative":describe([x for x in rows if x["category"]==cat and x["sign5"]=="NEGATIVE"])}
    for cat in CATS}}
def main():
 psha=prereg()
 s=cli();b=os.environ["R2_BUCKET"]
 v83=get(s,b,*V83)
 v84=get(s,b,*V84)
 if v83["version"]!="8.3" or v84["version"]!="8.4" or v83["population"]["totalWeeklyRows"]!=321:
  raise SystemExit("V85_PARENT_STRUCTURE_CHANGED")
 source={"url":URL,"vintageStatus":"PIT_UNVERIFIED_CURRENT_TABLE","readStatus":"UNAVAILABLE",
  "capturedAtUTC":dt.datetime.now(dt.timezone.utc).isoformat()}
 records=[]
 try:
  records,sourcehash=collect_farside()
  source.update({"readStatus":"PASS_PARSED","htmlSha256":sourcehash,"dailyRows":len(records),
    "firstDate":records[0]["day"],"lastDate":records[-1]["day"]})
 except Exception as exc:
  source.update({"readStatus":"SOURCE_UNAVAILABLE_NO_HISTORICAL_CLAIM",
    "error":str(type(exc).__name__)+":"+str(exc)[:200]})
 # We can still persist robustly the evidence that source cannot be reconstructed; do not invent.
 current={}
 matrix={}
 if records:
  f=records
  d=dt.date(2026,10,17)
  cutoff=d.isoformat()
  recent=[x for x in f if x["day"]<=cutoff]
  current={"last5":[x["day"] for x in recent[-5:]],
    "last10":[x["day"] for x in recent[-10:]],
    "last5SumMillionUSD":f6(sum(x["flowMillionUSD"] for x in recent[-5:])),
    "last10SumMillionUSD":f6(sum(x["flowMillionUSD"] for x in recent[-10:])),
    "asOfUTC":cutoff,"publicationTimestampHistoricalVerified":False}
  if current["last5"]!=["2026-10-12","2026-10-13","2026-10-14","2026-10-15","2026-10-16"]:
   raise SystemExit("V85_UNEXPECTED_LATEST_FIVE_DAYS")
  panel=[]
  for x in v83["weeklyPanel"]:
   day=dt.date.fromisoformat(x["sundayClosedUTC"])
   if day<dt.date(2024,2,1):continue
   conservative=(day-dt.timedelta(days=9)).isoformat()
   known=[r for r in f if r["day"]<=conservative]
   if len(known)<20:continue
   tail=known[-5:]
   tail20=known[-20:]
   sm=f6(sum(z["flowMillionUSD"] for z in tail))
   sm20=f6(sum(z["flowMillionUSD"] for z in tail20))
   sign=lambda v:"POSITIVE" if v>0 else ("NEGATIVE" if v<0 else "ZERO")
   panel.append({"sunday":x["sundayClosedUTC"],"etfCutoffDate":conservative,
    "lastUsedETFDate":tail[-1]["day"],"sum5Millions":sm,
    "sum20Millions":sm20,"sign5":sign(sm),"sign20":sign(sm20),
    "category":x["category"],
    "outcomes":{"4":x["future"]["4"],"13":x["future"]["13"]},
    "dataVintage":"PIT_UNVERIFIED_CURRENT_BACKFILL"})
  matrix={"panelRows":len(panel),
   "weekly":group(panel),
   "eras":{"2024":[x for x in panel if x["sunday"]<"2025-01-01"],
           "2025-2026":[x for x in panel if x["sunday"]>="2025-01-01"]},
   "displayWarning":"Retrospective group contrast with unverified published vintages, overlapping outcomes, and pre-existing BTC prices. NOT causal and NOT a validated OOS signal."}
  matrix["eras"]={key:group(row) for key,row in matrix["eras"].items()}
 else:
  matrix={"panelRows":0,"status":"BLOCKED_EXTERNAL_DATA","groupComparisons":None}
 report={"version":"8.5","status":"EXTERNAL_FACTOR_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,
  "preregistration":{"path":P,"sha256":psha},
  "frozenParents":{"v83":V83,"v84":V84},
  "sourceETF":source,
  "sourceFed":{"name":"Federal Reserve H.4.1","releaseTime":"Thursday 16:30 America/New_York generally",
   "series":"WALCL Wednesday level","asOfWeek":"2026-10-14",
   "status":"ONLY_PUBLICATION_RULE_CURRENT_CONTEXT_NO_HISTORICAL_FED_SERIES_JOINED",
   "PIT":"RELEASE_CALENDAR_NOT_FULL_VINTAGE"},
  "currentFarside":current,
  "ETFExploratory":matrix,
  "archiveDailyRows":records,
  "scope":["Farside current table is not point-in-time vintage; does not prove when historical flows became available",
    "9-day conservative date shift does NOT prove original publication timestamps or revisions",
    "Fed WALCL total assets alone are not net liquidity; TGA and RRP/reserves separately needed",
    "ETF launched Jan 2024 so zero historical coverage during 2020-2023 ineligible: do not impute zero",
    "Historical ETF group comparisons not out of sample; all cohorts, thresholds and results exploratory",
    "Price returns are from Binance perpetual futures, not executable multi-venue Spot",
    "No model score upgrade, trading authorization, risk targets, NAV or accounting writes"]}
 folder=Path("btci_v85_reports");folder.mkdir(exist_ok=True)
 blob=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"factor_audit.json").write_bytes(blob)
 root=f"research/btci/v8.5/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 dig=write(s,b,root+"factor_audit.json",blob)
 man=write(s,b,root+"manifest.json",{"version":"8.5","researchOnly":True,
    "status":"PIT_UNVERIFIED_RESEARCH_FACTOR_AUDIT","reportSha256":dig,"prefix":root})
 brief={"status":"V85_FACTOR_SOURCE_AUDIT_WRITEBACK_VERIFIED", "ETFSource":source,
  "Farside":current, "panelRows":matrix["panelRows"],
  "exploratory":matrix.get("weekly"),"reportSha256":dig,
  "manifestSha256":man,"prefix":root}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V85_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write(f"# BTCI v8.5 — внешний ETF-фактор: PIT-аудит\n\n"
   f"Статус: {source['readStatus']}. ВИНТАЖИ: НЕ ПРОВЕРЕНЫ.\n\n"
   f"R2: {root}\n\nSHA-256: {dig}\n\n"
   "No trading authority and no OOS claims.\n")
if __name__=="__main__":main()
