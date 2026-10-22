"""BTCI-PIT05; historical H.4.1 original release-dated source scrape, RESEARCH_ONLY.
Do not label 2026 retrieval original historic byte snapshots. No trades or model fit.
"""
import os,re,json,io,hashlib,zipfile,datetime as dt,concurrent.futures as cf,time,pathlib,requests
from bs4 import BeautifulSoup
ROOT=pathlib.Path("btci_pit05_output");ROOT.mkdir(exist_ok=True)
S=requests.Session()
S.headers.update({"User-Agent":"BTCI-academic-evidence/0.5"})
BASE="https://api.github.com/repos/analiticprosp-ship-it/crypto-price-feed/actions/artifacts/12168089066/zip"
SHA="539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091"
def sha(s):return hashlib.sha256(s).hexdigest()
def save(name,obj):
 (ROOT/name).write_text(json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
def get(url,auth=False):
 headers={"Authorization":"Bearer "+os.environ["GITHUB_TOKEN"]} if auth else {}
 for i in range(2):
  try:
   r=S.get(url,headers=headers,timeout=(4,12));r.raise_for_status()
   return r.content
  except Exception as e:
   er=str(e)
   if i==0:time.sleep(0.25)
 raise RuntimeError(er)
data=get(BASE,True)
with zipfile.ZipFile(io.BytesIO(data)) as z:parent=z.read("full_historical_rise_fall.json")
assert sha(parent)==SHA
report=json.loads(parent);days=[r["date"] for r in report["weeklyPanel"]]
assert len(days)==684 and days==sorted(set(days)) and days[0]=="2012-06-03" and days[-1]=="2025-10-12"
print("PARENT_684_PASS",flush=True)
index_url="https://www.federalreserve.gov/releases/h41/"
index=get(index_url)
# The archive index is JS-rendered; generate Thursday candidates.
# Every dated release is HTTP-checked; holidays use fallback dates.
links={}
candidate=dt.date(2012,5,1)
end_date=dt.date(2025,10,15)
while candidate<=end_date:
 if candidate.weekday()==3:
  stamp=candidate.strftime("%Y%m%d")
  links[candidate]="https://www.federalreserve.gov/releases/h41/"+stamp+"/"
 candidate+=dt.timedelta(days=1)
assert len(links)>=600,("NOT_ENOUGH_THURSDAY_CANDIDATES",len(links))
print("OFFICIAL_ARCHIVE_DATED_LINKS",len(links),flush=True)
expected={"2013-06-09":[41025,2026257],"2014-06-08":[31902,2708064],"2015-06-07":[184099,2490044],"2016-06-05":[259693,2400969],"2017-06-11":[154760,2270846],"2018-06-10":[289454,2031965],"2019-06-09":[207647,1559710],"2020-08-02":[1792434,2685376],"2021-06-06":[812087,3848262],"2022-06-05":[780575,3357395],"2023-06-11":[77500,3306154],"2024-06-09":[703314,3457738],"2024-10-06":[823412,3097210],"2025-06-08":[376160,3361938],"2025-10-12":[794054,3033855]}
pattern_tga=re.compile(r"u\.?\s*s\.?\s*treasury,\s*general account",re.I)
pattern_res=re.compile(r"reserve balances with federal reserve banks",re.I)
num=re.compile(r"(?<!\w)-?\s*\d{1,3}(?:,\d{3})+(?!\w)")
def row_numbers(text):
 xs=num.findall(text)
 return [int(a.replace(",","").replace(" ","")) for a in xs]
def parse(src):
 soup=BeautifulSoup(src,"html.parser")
 tr_rows=soup.find_all("tr")
 got={}
 for tr in tr_rows:
  cs=tr.find_all(["td","th"],recursive=False)
  if len(cs)<4:continue
  label=" ".join(cs[0].get_text(" ",strip=True).split()).strip()
  what="TGA" if pattern_tga.fullmatch(label) else ("RESERVES" if pattern_res.fullmatch(label) else None)
  if not what or what in got:continue
  # in Table 1: first column is week-average, last is Wednesday observation
  parts=[c.get_text(" ",strip=True) for c in cs[1:]]
  if len(cs)==5:
   last=parts[-1]
   vals=row_numbers(last)
   if vals:got[what]={"level_musd":vals[-1],"row_raw_sha256":sha(str(tr).encode("utf-8")),"row_text":label+" | "+" | ".join(parts)}
  elif len(cs)==4:
   # extra caution: older documents may have non-Table-1 columns; no silent mapping
   continue
 if len(got)==2:return got,"HTML_TABLE1_5_COL"
 # Legacy <pre> (older H.4.1): label in fixed-width ASCII table, Wednesday is LAST numeric token
 for line in soup.get_text("\n",strip=False).splitlines():
  label=" ".join(line.split())
  what="TGA" if pattern_tga.search(label) else ("RESERVES" if pattern_res.search(label) else None)
  if not what or what in got:continue
  if len(label)>200:continue
  label_clean=pattern_tga.sub("",label) if what=="TGA" else pattern_res.sub("",label)
  nums=row_numbers(label_clean)
  if len(nums)>=3:got[what]={"level_musd":nums[-1],"line_text":label[:210],"legacy_number_count":len(nums)}
 return got,"LEGACY_FALLBACK" if len(got)==2 else "UNPARSED"
sample_dates=["2013-06-06","2014-06-05","2018-06-07","2020-07-30","2024-10-03","2025-10-09"]
sample={}
for d in sample_dates:
 date=dt.date.fromisoformat(d)
 if date not in links:sample[d]={"status":"MISSING_INDEX_LINK"};continue
 try:
  raw=get(links[date]);parsed,method=parse(raw)
  sample[d]={"status":"OK","method":method,"values":{k:v["level_musd"] for k,v in parsed.items()},"source_sha256":sha(raw)}
  print("SAMPLE",d,method,sample[d]["values"],flush=True)
 except Exception as e:
  sample[d]={"status":"ERROR","error":repr(e)};print("SAMPLE_ERROR",d,str(e)[:120],flush=True)
save("SAMPLE_PARSING.json",sample)
all_release_dates=sorted(links)
from bisect import bisect_left
map_releases={}
for dec in days:
 day=dt.date.fromisoformat(dec);i=bisect_left(all_release_dates,day)-1
 if i<0:continue
 prior=all_release_dates[i];age=(day-prior).days
 if age<=9:map_releases[dec]=prior
print("COVERABLE_684_SUNDAYS",len(map_releases),flush=True)
unique=sorted(set(map_releases.values()))
def work(date):
 url=links[date]
 try:
  used=date
  raw=None
  for offset in (0,1,-1,-7):
   trial=date+dt.timedelta(days=offset)
   trial_url="https://www.federalreserve.gov/releases/h41/"+trial.strftime("%Y%m%d")+"/"
   try:
    raw=get(trial_url);url=trial_url;used=trial;break
   except Exception:
    continue
  if raw is None:raise RuntimeError("NO_H41_RELEASE_FOR_CALENDAR_WEEK")
  got,method=parse(raw)
  val={k:v["level_musd"] for k,v in got.items()}
  return date.isoformat(),{"release_date":used.isoformat(),"source_url":url,"source_sha256_retrieval_2026":sha(raw),"source_size":len(raw),"parse_method":method,"values":val,"row_evidence":{k:v.get("row_text",v.get("line_text","")) for k,v in got.items()},"historically_dated_archive":True,"original_bytes_in_2012_2025_not_verified":True,"strict_PIT":False}
 except Exception as e:return date.isoformat(),{"release_date":date.isoformat(),"source_url":url,"status":"ERROR","error":repr(e),"strict_PIT":False}
found={}
with cf.ThreadPoolExecutor(max_workers=5) as executor:
 futures=[executor.submit(work,d) for d in unique]
 for i,fut in enumerate(cf.as_completed(futures)):
  d,result=fut.result();found[d]=result
  if (i+1)%65==0:print("FETCHED",i+1,"of",len(unique),"parsed_both",sum(set(x.get("values",{}))=={"TGA","RESERVES"} for x in found.values()),flush=True)
  if (i+1)%100==0:save("H41_RELEASES_PARTIAL.json",found)
save("H41_RELEASES_PARSED.json",found)
mapped=[]
for decision in days:
 rel=map_releases.get(dec)
 dat=found.get(rel.isoformat(),{}) if rel else {}
 v=dat.get("values",{})
 mapped.append({"date":decision,"h41_release_date":dat.get("release_date",rel.isoformat() if rel else None),"tga_wednesday_musd":v.get("TGA"),"reserves_wednesday_musd":v.get("RESERVES"),"h41_source_sha256":dat.get("source_sha256_retrieval_2026"),"method":dat.get("parse_method"),"strict_PIT":False})
assert len(mapped)==684 and [r["date"] for r in mapped]==days
anchor_check=[]
for k,values in expected.items():
 row=next(x for x in mapped if x["date"]==k)
 ok=[row["tga_wednesday_musd"],row["reserves_wednesday_musd"]]==values
 anchor_check.append({"date":k,"expected":values,"observed":[row["tga_wednesday_musd"],row["reserves_wednesday_musd"]],"match":ok})
summary={"status":"H41_RELEASE_DATED_ARCHIVE_CURRENT_RETRIEVAL_NOT_ORIGINAL_BYTES","canonical":"BTCI v8.18d7","mode":"RESEARCH_ONLY","parent_sha256":SHA,"parent_weeks":684,"archive_index_sha256":sha(index),"archive_release_links":None,"candidate_thursdays":len(links),"index_is_dynamic_and_has_no_server_html_historical_links":True,"mapped_sundays":len(map_releases),"unique_release_urls":len(unique),"released_parsed_both":sum(set(x.get("values",{}))=={"TGA","RESERVES"} for x in found.values()),"tga_coverage":sum(r["tga_wednesday_musd"] is not None for r in mapped),"reserves_coverage":sum(r["reserves_wednesday_musd"] is not None for r in mapped),"anchor_comparison":{"match":sum(x["match"] for x in anchor_check),"n":len(anchor_check)},"strict_historical_pit":False,"trading_authority":False,"no_model_training":True,"main_branch_untouched":True,"R2_untouched":True}
save("JOIN_684_H41_SPARSE_OR_FULL.json",{"metadata":summary,"rows":mapped})
save("ANCHOR_COMPARE_15.json",anchor_check)
save("RESULT.json",summary)
print("PIT05_RESULT",json.dumps(summary,ensure_ascii=False),flush=True)
