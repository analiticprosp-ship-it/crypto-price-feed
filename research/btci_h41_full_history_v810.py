#!/usr/bin/env python3
"""BTCI 8.10: audited date-labeled Federal Reserve H4.1 historical levels.
Independent from trading accounts. No positions, NAV or detector runtime changes.
H41 archive pages viewed today are not cryptographic original PIT vintages.
"""
import argparse,datetime as dt,hashlib,json,os,re,statistics,urllib.request,time,concurrent.futures
from collections import Counter
from pathlib import Path
from bs4 import BeautifulSoup
import boto3

ROOT=Path(__file__).resolve().parents[1]
P="research/btci_v810_macro_h41_full_prereg_2026-10-18.json"
ADD="research/btci_v810a_h41_table_versions_addendum_2026-10-18.json"
V89=("research/btci/v8.9/runs/39138844921-1/multiscale.json",
"4b8822e929aff5569fa9cd105404c02b110927a970aed33db68910925c111b73")
SAMPLES=("2011-10-20","2017-10-19","2020-10-22","2022-10-20","2024-10-17","2025-10-16")
TEST={
 "2011-10-20":(2855177,68392,80468),
 "2020-10-22":(7177265,1699497,187435),
 "2025-10-16":(6596454,851952,347901)}
INDEX="https://www.federalreserve.gov/releases/h41/"
YEARS=list(range(2011,2027))
def digest(v):return hashlib.sha256(v).hexdigest()
def r6(v):return round(float(v),6) if v is not None else None
def root():return f"research/btci/v8.10/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
def cloud():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,key,sha):
 body=s.get_object(Bucket=b,Key=key)["Body"].read()
 if digest(body)!=sha:raise SystemExit("V810_INPUT_SHA_MISMATCH:"+key)
 return json.loads(body)
def write(s,b,key,body,kind="application/json"):
 blob=body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False,indent=2).encode()
 h=digest(blob)
 s.put_object(Bucket=b,Key=key,Body=blob,ContentType=kind,
 Metadata={"sha256":h,"research-only":"true"})
 if digest(s.get_object(Bucket=b,Key=key)["Body"].read())!=h:
  raise SystemExit("V810_R2_READBACK_MISMATCH:"+key)
 return h
def spec():
 original=(ROOT/P).read_bytes();add=(ROOT/ADD).read_bytes()
 p=json.loads(original);q=json.loads(add)
 if p["version"]!="8.10" or p["parents"]["v89"]!={"key":V89[0],"sha256":V89[1]} or q["version"]!="8.10a":
  raise SystemExit("V810_REGISTRATION_CHANGED")
 return {"parentSha256":digest(original),"addendumSha256":digest(add)}
def http(url):
 last=None
 for k in range(4):
  try:
   request=urllib.request.Request(url,headers={"User-Agent":"BTCI research archive + verification/8.10",
      "Accept":"text/html"})
   with urllib.request.urlopen(request,timeout=45) as f:
    raw=f.read(2_000_001)
   if len(raw)>2_000_000:raise ValueError("HTML_LIMIT_EXCEEDED")
   return raw
  except Exception as exc:
   last=exc
   time.sleep(0.8+1.5*k)
 raise last
def releases_from_index():
 # The Federal Reserve index is JavaScript-rendered and contains no static links
 # on GitHub runners. ALFRED supplies downloadable historical H.4.1 release dates.
 url="https://alfred.stlouisfed.org/release/downloaddates?ff=txt&rid=20"
 raw=http(url)
 matches=set(re.findall(r"(?<!\\d)((?:19|20)\\d{2}-[01]\\d-[0-3]\\d)(?!\\d)",raw.decode("utf-8","replace")))
 days=sorted(dt.date.fromisoformat(s) for s in matches
  if dt.date(2011,1,1)<=dt.date.fromisoformat(s)<=dt.date(2026,10,15))
 if len(days)<740:
  raise SystemExit("V810_ALFRED_RELEASE_INDEX_INVALID count="+str(len(days))
   +" rawHead="+repr(raw[:300]))
 return days,digest(raw)
def clean(c):
 return re.sub(r"\s+"," ",c.replace("\xa0"," ").strip())
def number(c):
 v=clean(c).replace(" ","")
 if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+|-?\d+",v):return int(v.replace(",",""))
 return None
def label(c):
 v=clean(c).lower()
 v=re.sub(r"\s*\(?\d{1,2}\)?\s*$","",v)
 return v
def structured_data(soup):
 rows=[]
 for table in soup.find_all("table"):
  m={}
  for tr in table.find_all("tr"):
   cells=tr.find_all(["th","td"],recursive=False)
   if not cells:continue
   text=[clean(x.get_text(" ",strip=True)) for x in cells]
   if not text:continue
   key=label(text[0])
   if key in ("total assets","u.s. treasury, general account","reverse repurchase agreements"):
    nums=[number(x) for x in text[1:] if clean(x)!="" and not re.fullmatch(r"\(\d+\)",clean(x))]
    nums=[v for v in nums if v is not None]
    if nums:m[key]=nums[0]
  rows.append(m)
 # Prefer first actual section with total assets, then later matching liabilities.
 for idx,part in enumerate(rows):
  if "total assets" not in part:continue
  for following in rows[idx+1:idx+4]:
   if "u.s. treasury, general account" in following and "reverse repurchase agreements" in following:
    return (part["total assets"],following["u.s. treasury, general account"],following["reverse repurchase agreements"]),"HTML_TABLE"
 return None,None
def fixedwidth_data(soup):
 full=soup.get_text("\n",strip=False).replace("\xa0"," ")
 title_re=r"(?m)^\s*\d{1,2}\.\s*Consolidated Statement of Condition of All Federal Reserve Banks\s*$"
 headings=list(re.finditer(title_re,full,re.I))
 if not headings:return None,None
 # Old H41 uses table 8 instead of table 5 and exact fixed-width lines.
 chunk=full[headings[0].start():]
 other=re.search(r"(?m)^\s*\d{1,2}\.\s*Statement of Condition of Each Federal Reserve Bank",chunk,re.I)
 if other:chunk=chunk[:other.start()]
 def extract(name):
  pat=rf"(?m)^\s*{name}\s+(?:\(\d+\)\s+)?([\d,]+)\s"
  found=re.findall(pat,chunk,re.I)
  if not found:return None
  return int(found[0].replace(",",""))
 total=extract(r"Total assets")
 tga=extract(r"U\.S\.\s*Treasury,\s*General Account")
 rrp=extract(r"Reverse repurchase agreements(?:\s*\(\d+\))?")
 if None in (total,tga,rrp):return None,None
 return (total,tga,rrp),"PREFORMATTED_CONSOLIDATED"
def parse(body,date):
 soup=BeautifulSoup(body,"html.parser")
 head=clean(soup.get_text(" ",strip=True)[:5000])
 written=dt.date.fromisoformat(date).strftime("%B %d, %Y").replace(" 0"," ")
 if written.lower() not in head.lower() or "H.4.1" not in head:
  raise ValueError("H41_WRONG_RELEASE_OR_DATE")
 trio,method=structured_data(soup)
 if trio is None:trio,method=fixedwidth_data(soup)
 if trio is None:raise ValueError("H41_CONSOLIDATED_ROW_PARSE_NOT_FOUND")
 total,tga,rrp=trio
 if not 100000<total<15000000 or not 0<=tga<total or not 0<=rrp<total:
  raise ValueError("H41_OUT_OF_RANGE_VALUES")
 if date in TEST and trio!=TEST[date]:
  raise ValueError("H41_FROZEN_SAMPLE_VALUES_MISMATCH:"+repr(trio)+" expected:"+repr(TEST[date]))
 return {"releaseDate":date,"observedWednesday":(
   dt.date.fromisoformat(date)-dt.timedelta(days=(dt.date.fromisoformat(date).weekday()-2)%7)).isoformat(),
   "assetsMillionUSD":total,"tgaMillionUSD":tga,"reverseRepoMillionUSD":rrp,
   "simplifiedFedMinusTGAMinusRRP_MillionUSD":total-tga-rrp,
   "parseMethod":method,"releasePageMayHaveLaterCorrections":True}
def fetchone(date):
 d=date.replace("-","")
 url="https://www.federalreserve.gov/releases/h41/"+d+"/"
 raw=http(url)
 try:
  row=parse(raw,date)
 except Exception as exc:
  return {"date":date,"status":"PARSE_BLOCKED","error":type(exc).__name__+":"+str(exc)[:200],
          "url":url,"htmlSha256":digest(raw),"raw":raw}
 return {"date":date,"status":"PARSED","value":row,
   "url":url,"htmlSha256":digest(raw),"raw":raw}
def archive_one(s,b,res,prefix):
 date=res["date"];d=date.replace("-","")
 key=prefix+"official_pages/"+d+".html"
 hash_cloud=write(s,b,key,res["raw"],"text/html")
 if hash_cloud!=res["htmlSha256"]:raise SystemExit("V810_PAGE_DIGEST_CHANGED")
 audit={k:v for k,v in res.items() if k!="raw"}
 audit["r2Key"]=key
 return audit
def year_mode(year,pilot=False):
 cert=spec();s=cloud();b=os.environ["R2_BUCKET"]
 if pilot:
  dates=list(SAMPLES);where=root()+"pilot/"
 else:
  dates,index_hash=releases_from_index()
  dates=[x.isoformat() for x in dates if x.year==year]
  where=root()+f"years/{year}/"
 if not dates:raise SystemExit("V810_NO_RELEASE_DATES")
 # Parallel official website GETs with restrained concurrency.
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
  future=list(ex.map(fetchone,dates))
 results=[]
 # Keep all fetched evidence (even unparsed sources) in R2 to investigate errors.
 for item in future:
  results.append(archive_one(s,b,item,where))
 errors=[r for r in results if r["status"]!="PARSED"]
 if pilot and errors:raise SystemExit("V810_PILOT_FAILED:"+str(errors))
 year_report={"version":"8.10","kind":"PILOT" if pilot else "YEAR",
  "year":None if pilot else year,"status":"SOURCE_ARCHIVED",
  "registeredSpec":cert,
  "sourceIndexSha256":index_hash if not pilot else None,
  "observedReleaseCount":len(results),
  "accepted":sum(x["status"]=="PARSED" for x in results),
  "blocked":errors,"releases":results,
  "historicalVintageStatus":"DATED_PAGE_VIEWED_TODAY_NOT_VERIFIED_ORIGINAL_UNEDITED_PIT"}
 raw=json.dumps(year_report,ensure_ascii=False,indent=2).encode()
 h=write(s,b,where+"year_report.json",raw)
 file=Path("btci_v810_reports");file.mkdir(exist_ok=True)
 (file/("pilot.json" if pilot else f"{year}.json")).write_bytes(raw)
 result={"status":"V810_PILOT_PASS" if pilot else "V810_YEAR_ARCHIVED",
  "year":year,"observed":len(results),"accepted":year_report["accepted"],
  "blockedCount":len(errors),"blockedExamples":errors[:4],
  "key":where+"year_report.json","sha256":h}
 print("V810_YEAR_RESULT "+json.dumps(result,ensure_ascii=False),flush=True)
def classify_week(rows,day):
 eligible=[r for r in rows if dt.date.fromisoformat(r["releaseDate"])<=day-dt.timedelta(days=3)]
 if len(eligible)<5:return {"status":"INSUFFICIENT_LAGGED_RELEASES"}
 latest=eligible[-1];before=eligible[-5]
 last_date=dt.date.fromisoformat(latest["releaseDate"])
 if (day-last_date).days>21 or any((
   dt.date.fromisoformat(b["releaseDate"])-dt.date.fromisoformat(a["releaseDate"])).days>21
    for a,b in zip(eligible[-5:],eligible[-4:])):
  return {"status":"STALE_OR_GAPPED_RELEASES"}
 delta=latest["simplifiedFedMinusTGAMinusRRP_MillionUSD"]-before["simplifiedFedMinusTGAMinusRRP_MillionUSD"]
 return {"status":"AVAILABLE","lastReleaseDate":latest["releaseDate"],
  "lastPublicationAtOrBeforeUTC":(last_date+dt.timedelta(days=3)).isoformat(),
  "observedWednesday":latest["observedWednesday"],
  "monthsOfDataVerified":False,"levelMillionUSD":latest["simplifiedFedMinusTGAMinusRRP_MillionUSD"],
  "deltaFourReleasesMillionUSD":delta,
  "macroDirection":"UP" if delta>0 else ("DOWN" if delta<0 else "FLAT")}
def eventstat(items):
 q=[z["future"]["13"] for z in items if z["future"]["13"]["status"]=="OBSERVED"]
 x=[z["returnPct"] for z in q]
 return {"n":len(items),"next13wObserved":len(x),"next13wCensored":len(items)-len(x),
  "medianBTCFuture13wPct":r6(statistics.median(x)) if x else None,
  "positiveCount":sum(a>0 for a in x),
  "interpretation":"RETROSPECTIVE_CORRELATED_DESCRIPTIVE_NO_OUT_OF_SAMPLE"}
def combine():
 cert=spec();s=cloud();b=os.environ["R2_BUCKET"]
 parent=get(s,b,*V89)
 if parent["version"]!="8.9" or parent["switchCount"]!=29 or parent["lastEligibleWeek"]!="2026-10-11":
  raise SystemExit("V810_PARENT_CHANGED")
 rows=[];manifest=[];blocked=[]
 for year in YEARS:
  prefix=root()+f"years/{year}/"
  blob=s.get_object(Bucket=b,Key=prefix+"year_report.json")["Body"].read()
  yr=json.loads(blob)
  if yr.get("version")!="8.10" or yr.get("year")!=year or yr.get("registeredSpec")!=cert:
   raise SystemExit("V810_UNEXPECTED_YEAR_MANIFEST:"+str(year))
  if yr["accepted"]!=yr["observedReleaseCount"]-len(yr["blocked"]):
   raise SystemExit("V810_YEAR_COUNT_MISMATCH")
  for rec in yr["releases"]:
   if rec["status"]=="PARSED":rows.append(rec["value"])
   else:blocked.append({k:v for k,v in rec.items() if k!="raw"})
  manifest.append({"year":year,"key":prefix+"year_report.json","sha256":digest(blob),
     "accepted":yr["accepted"],"blocked":len(yr["blocked"])})
 dates=[a["releaseDate"] for a in rows]
 rows.sort(key=lambda x:x["releaseDate"])
 if len(rows)!=len(set(dates)) or len(rows)<600:raise SystemExit("V810_TOO_FEW_VALID_RELEASES")
 dated={a["date"]:a for a in parent["pastOnlyWeeklyContext"]}
 panel=[]
 for date,record in sorted(dated.items()):
  day=dt.date.fromisoformat(date)
  macro=classify_week(rows,day)
  panel.append({"date":date,"structural":record["confirmed"],
   "rawStructural":record["raw"],"btcWeeklyTrend":record["weeklyTrend"],
   "breadth":record["breadth"]["status"],
   "macro":macro})
 mapped={x["date"]:x for x in panel}
 sw=[]
 for e in parent["switches"]:
  today=mapped[e["date"]]
  sw.append({"date":e["date"],"from":e["from"],"to":e["to"],
    "macro":today["macro"],"future":{"13":e["future"]["13"],"26":e["future"]["26"]}})
 by={}
 for typ in ("STRUCTURAL_EXPANSION_PRICE_PROXY","STRUCTURAL_CONTRACTION_PRICE_PROXY","TRANSITION_OR_REBOUND_PRICE_PROXY"):
  all_items=[x for x in sw if x["to"]==typ]
  by[typ]={direction:eventstat([x for x in all_items if x["macro"].get("macroDirection")==direction])
     for direction in ("UP","DOWN","FLAT")}
  by[typ]["MISSING"]={"n":sum(x["macro"]["status"]!="AVAILABLE" for x in all_items)}
 byregime={}
 for typ in ("STRUCTURAL_EXPANSION_PRICE_PROXY","STRUCTURAL_CONTRACTION_PRICE_PROXY","TRANSITION_OR_REBOUND_PRICE_PROXY"):
  sub=[x for x in panel if x["structural"]==typ]
  byregime[typ]={"n":len(sub),"macroDirections":dict(Counter(x["macro"].get("macroDirection","UNAVAILABLE") for x in sub))}
 curr=panel[-1]
 study={"version":"8.10","status":"DATED_H41_HISTORICAL_MACRO_RESEARCH_ONLY",
  "researchOnly":True,"noTradingAuthority":True,
  "parentV89":{"key":V89[0],"sha256":V89[1]},
  "registeredSpec":cert,
  "releaseSource":"https://www.federalreserve.gov/releases/h41/",
  "historicalVintageStatus":"PAGES_RETRIEVED_NOW_CURRENT_VERSIONS_NOT_CERTIFIED_ORIGINAL_PUBLISHED_VINTAGE",
  "parsedRows":len(rows),"missingRows":len(blocked),"blockedExamples":blocked[:30],
  "yearlySourceManifest":manifest,"FedDatedWeeklyRecords":rows,
  "macroFormula":"Fed balance sheet assets - US Treasury General Account - all consolidated reverse repos, millions USD; simplified descriptive proxy, NOT full net liquidity",
  "macroAvailability":"Published release dated at least three days before fully closed BTC Sunday; no future values",
  "structuralWeekCoverage":{"n":len(panel),"available":sum(x["macro"]["status"]=="AVAILABLE" for x in panel),
    "missing":dict(Counter(x["macro"]["status"] for x in panel if x["macro"]["status"]!="AVAILABLE"))},
  "byStructuralState":byregime,"phaseSwitchMacroStudy":by,
  "events":sw,"panel":panel,"current":curr,
  "limits":["Dated archived release pages can be revised later: FULL contemporaneous PIT vintages unverified",
   "Sign of balance-minus-TGA-minus-RRP delta is not Fed liquidity cause or complete US net liquidity",
   "Financial conditions NFCI and official adjustment by past vintages not joined here",
   "Markets and the policy response jointly determine liquidity; correlation is not causation",
   "Up/down 4-release choice fixed before reading outcomes but was not prospectively validated",
   "Overlapping 13w futures and BTC phases are auto-correlated; no OOS probabilities",
   "TGA total and ALL reverse repos may not mean tradable capital availability",
   "No Spot/Futures/NAV/capital/P&L/reserve/MASTER/trading limit writes"]}
 folder=Path("btci_v810_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(study,ensure_ascii=False,indent=2).encode()
 (folder/"macro_study.json").write_bytes(raw)
 prefix=root()+"combined/"
 rhash=write(s,b,prefix+"macro_study.json",raw)
 mh=write(s,b,prefix+"manifest.json",{"version":"8.10","reportSha256":rhash,
  "status":"H41_DATED_ARCHIVE_RESEARCH_PASS","researchOnly":True,
  "yearManifest":manifest})
 short={"status":"V810_MACRO_REPORT_PASS_READBACK_VERIFIED",
  "reportSha256":rhash,"manifestSha256":mh,"prefix":prefix,
  "parsedRows":len(rows),"blockedRows":len(blocked),"blockedSample":blocked[:5],
  "sourceYears":manifest,"coverage":study["structuralWeekCoverage"],
  "byState":byregime,"bySwitch":by,"current":curr}
 (folder/"summary.json").write_text(json.dumps(short,ensure_ascii=False,indent=2))
 print("V810_RESULT "+json.dumps(short,ensure_ascii=False),flush=True)
if __name__=="__main__":
 a=argparse.ArgumentParser()
 a.add_argument("--pilot",action="store_true")
 a.add_argument("--year",type=int,choices=YEARS)
 a.add_argument("--combine",action="store_true")
 p=a.parse_args()
 if p.pilot:year_mode(None,True)
 elif p.year:year_mode(p.year)
 elif p.combine:combine()
 else:raise SystemExit("V810_SELECT_MODE")
