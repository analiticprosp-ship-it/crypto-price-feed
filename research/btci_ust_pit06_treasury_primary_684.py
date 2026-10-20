"""BTCI PIT06 | Treasury primary nominal & real curve CSV 2012–2025, no PIT promotion or trading."""
import os,io,csv,re,json,time,hashlib,zipfile,datetime,pathlib
import requests
ROOT=pathlib.Path("btci_pit06_treasury");ROOT.mkdir(exist_ok=True)
PARENT_SHA="539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091"
BASE="https://home.treasury.gov/resource-center/data-chart-center/interest-rates"
ARCHIVE=BASE+"/daily-treasury-rate-archives/"
SERIES={"nominal":("par-yield-curve-rates-1990-2023.csv","daily_treasury_yield_curve"),"real":("par-real-yield-curve-rates-2003-2023.csv","daily_treasury_real_yield_curve")}
REQ=requests.Session();REQ.headers.update({"User-Agent":"BTCI-academic-research-primary-US-Treasury/2026-10-20"})
def digest(b):return hashlib.sha256(b).hexdigest()
def fetch(url,auth=False):
 try:
  h={"Authorization":"Bearer "+os.environ["GITHUB_TOKEN"],"Accept":"application/vnd.github+json"} if auth else {}
  r=REQ.get(url,headers=h,timeout=(6,20));r.raise_for_status()
  return r.content,{"url":url,"sha256":digest(r.content),"http_status":r.status_code,"bytes":len(r.content),"source_format":r.headers.get("Content-Type")}
 except Exception as e:return None,{"url":url,"error":str(e)[:380]}
raw,meta=fetch("https://api.github.com/repos/analiticprosp-ship-it/crypto-price-feed/actions/artifacts/12168089066/zip",True)
assert raw,"PINNED_PARENT_GITHUB_NOT_ACCESSIBLE"
with zipfile.ZipFile(io.BytesIO(raw)) as z:base=z.read("full_historical_rise_fall.json")
panel=json.loads(base);assert digest(base)==PARENT_SHA and panel["researchOnly"] and not panel["tradeApproval"]
dates=[r["date"] for r in panel["weeklyPanel"]]
assert len(dates)==684 and dates==sorted(set(dates)) and dates[0]=="2012-06-03" and dates[-1]=="2025-10-12"
errors=[];meta_files=[];observed={"nominal":{},"real":{}};file_archive=ROOT/"treasury_official_csv_bytes_as_retrieved_2026.zip"
def norm(k):return re.sub(r"[^a-z0-9]","",k.lower())
def dateparse(text):
 for fmt in ("%m/%d/%Y","%Y-%m-%d","%m/%d/%y"):
  try:return datetime.datetime.strptime(text.strip(),fmt).date().isoformat()
  except ValueError:pass
 return None
def parse(raw,typ):
 val=raw.decode("utf-8-sig",errors="strict");rdr=csv.DictReader(io.StringIO(val))
 keys=rdr.fieldnames or [];n={norm(k):k for k in keys if k}
 datekey=n.get("date")
 tenkey=n.get("10yr") or n.get("10year")
 twokey=n.get("2yr") or n.get("2year")
 if not datekey or not tenkey:raise ValueError("MISSING_REQUIRED_COLUMNS "+str(keys)[:180])
 if typ=="nominal" and not twokey:raise ValueError("NO_2Y_COLUMN "+str(keys)[:180])
 tmp={}
 for row in rdr:
  d=dateparse(row.get(datekey,"") or "")
  if not d or not ("2012-01-01"<=d<="2025-10-12"):continue
  try:
   v=float(row.get(tenkey) or "")
   t=float(row.get(twokey) or "") if typ=="nominal" else None
   if not (-10<v<30 and (t is None or -10<t<30)):continue
   tmp[d]={"10y":v,"2y":t} if typ=="nominal" else {"real10y":v}
  except (ValueError,TypeError):continue
 return tmp,{"header":keys,"points":len(tmp)}
with zipfile.ZipFile(file_archive,"w",compression=zipfile.ZIP_DEFLATED) as z:
 for typ,(fname,querytype) in SERIES.items():
  links=[("archive_"+fname,ARCHIVE+fname)]
  for y in (2024,2025):
   for m in range(1,13):
    if y==2025 and m>10:continue
    month=str(y)+f"{m:02d}"
    u=BASE+"/daily-treasury-rates.csv/all/"+month+"?type="+querytype+"&field_tdr_date_value_month="+month+"&page=&_format=csv"
    links.append((typ+"_"+month+".csv",u))
  for name,url in links:
   b,met=fetch(url)
   entry={"kind":typ,"name":name,**met}
   if b:
    try:
     chunk,parsemeta=parse(b,typ)
     if chunk:
      observed[typ].update(chunk)
      z.writestr(name,b)
     entry.update(parsemeta)
    except Exception as e:entry["parse_error"]=str(e)[:280]
   if "error" in entry or "parse_error" in entry:errors.append(entry)
   meta_files.append(entry)
   if name.startswith("archive") or name.endswith("01.csv"):print("SOURCE",name,entry.get("points"),entry.get("error"),flush=True)
   time.sleep(0.14)
rows=[]
for d in dates:
 dt=datetime.date.fromisoformat(d)
 # All observations selected no later than Friday before the Sunday decision.
 limit=(dt-datetime.timedelta(days=2)).isoformat()
 row={"date":d,"decision_utc_assumption":d+"T00:00:00Z","source_status":"CURRENT_OFFICIAL_TREASURY_ARCHIVE_NO_INITIAL_RELEASE_TIMESTAMP_PROOF","strict_pit_approved":False}
 for typ in ("nominal","real"):
  candidates=[x for x in observed[typ] if x<=limit and (dt-datetime.date.fromisoformat(x)).days<=10]
  if candidates:
   last=max(candidates)
   row[typ]={"observation_date":last,**observed[typ][last]}
  else:row[typ]=None
 if row["nominal"]:
  row["UST10y_minus_2y_pct_points"]=round(row["nominal"]["10y"]-row["nominal"]["2y"],8)
 else:row["UST10y_minus_2y_pct_points"]=None
 rows.append(row)
pin={"2025-10-10":(3.52,4.05),"2024-10-04":(3.93,3.98)}
pin_results={}
for d,expected in pin.items():
 n=observed["nominal"].get(d)
 pin_results[d]=({"found":True,"matched":abs(n["2y"]-expected[0])<0.01 and abs(n["10y"]-expected[1])<0.01,"value":n} if n else {"found":False})
summ={"research_version":"BTCI UST PIT06","mode":"RESEARCH_ONLY","source":"US_TREASURY_DIRECT_OFFICIAL_AS_RETRIEVED_2026","canonical_base_sha256":PARENT_SHA,"original_sundays":len(rows),"observations_nominal_daily":len(observed["nominal"]),"observations_real_daily":len(observed["real"]),"nominal_2y10y_weekly_coverage":sum(r["nominal"] is not None for r in rows),"real10y_weekly_coverage":sum(r["real"] is not None for r in rows),"both_weekly_coverage":sum(r["nominal"] is not None and r["real"] is not None for r in rows),"anchor_crosschecks":pin_results,"strict_original_vintage_approved":0,"original_publication_clock_verified":False,"model_fit":False,"forecast_edge_proven":False,"main_writeback":False,"R2_writeback":False,"portfolio_writeback":False,"raw_official_archives_sha256":digest(file_archive.read_bytes()),"errors_count":len(errors)}
(ROOT/"treasury_684_join_candidate_only.json").write_text(json.dumps({"summary":summ,"rows":rows},ensure_ascii=False,indent=2)+"\n")
(ROOT/"treasury_source_sha_ledger.json").write_text(json.dumps(meta_files,ensure_ascii=False,indent=2)+"\n")
(ROOT/"treasury_failed_or_parsing_sources.json").write_text(json.dumps(errors,ensure_ascii=False,indent=2)+"\n")
(ROOT/"treasury_result.json").write_text(json.dumps(summ,ensure_ascii=False,indent=2)+"\n")
print("BTCI_PIT06_RESULT",json.dumps(summ),flush=True)
