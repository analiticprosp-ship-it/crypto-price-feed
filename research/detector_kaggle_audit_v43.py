#!/usr/bin/env python3
"""Kaggle Data Audit v4.3 — discover, inspect and conditionally download small public datasets.
Do not assert author notebook == dataset identity. Do not promote unverified CSV to Detector.
"""
import urllib.request,urllib.parse,urllib.error,json,csv,io,zipfile,hashlib,collections,datetime as dt
from pathlib import Path
O=Path("detector_kaggle_audit_v43_results");O.mkdir(exist_ok=True)
SEARCH=["bitcoin open interest binance futures","bitcoin funding rate binance futures","bitcoin taker buy sell volume binance futures"]
MAX_DOWNLOAD=25_000_000
def get(url,max_bytes=MAX_DOWNLOAD+1):
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Detector-Research-Kaggle-v43","Accept":"application/json"}),timeout=35) as r:
  data=r.read(max_bytes+1)
  if len(data)>max_bytes:raise ValueError("SIZE_CAP_EXCEEDED")
  return data
def jsonget(url):return json.loads(get(url,3_000_000))
found={};errors=[]
for q in SEARCH:
 url="https://www.kaggle.com/api/v1/datasets/list?"+urllib.parse.urlencode({"search":q,"page":1,"pageSize":20})
 try:
  obj=jsonget(url)
  if not isinstance(obj,list):raise ValueError("NON_LIST_RESPONSE")
  for x in obj:
   ref=x.get("ref") or (str(x.get("ownerRef",""))+"/"+str(x.get("slug","")))
   if ref and "/" in ref:found[ref]=x
 except Exception as e:errors.append({"query":q,"stage":"search","error":type(e).__name__+":"+str(e)[:140]})
# Explicit author candidates from prior notebook input labels: never assume slugs exist.
candidates=[ref for ref in found if "jesusgraterol/" in ref.lower()]
for suffix in ("bitcoin-open-interest-binance-futures","bitcoin-funding-rate-binance-futures","bitcoin-taker-buy-sell-volume-binance-futures"):
 ref="jesusgraterol/"+suffix
 if ref not in candidates:candidates.append(ref)
records=[];file_records=[]
for ref in sorted(set(candidates)):
 owner,slug=ref.split("/",1)
 record={"ref":ref,"found_in_search":ref in found,"status":"NOT_CHECKED"}
 try:
  meta=jsonget(f"https://www.kaggle.com/api/v1/datasets/view/{urllib.parse.quote(owner)}/{urllib.parse.quote(slug)}")
  record.update(status="METADATA_OK",title=meta.get("title",""),lastUpdated=meta.get("lastUpdated",""),totalBytes=meta.get("totalBytes",""),license=meta.get("licenseName",""),url=meta.get("url",""))
  files=meta.get("resources") or []
  for f in files:
   file_records.append({"ref":ref,"file":f.get("path") or f.get("name",""),"size":f.get("size",""),"metadata_only":True})
  size=int(meta.get("totalBytes") or 0)
  if not size or size>MAX_DOWNLOAD:
   record["download"]="SKIPPED_UNKNOWN_OR_GT_25MB";records.append(record);continue
  try:
   raw=get(f"https://www.kaggle.com/api/v1/datasets/download/{urllib.parse.quote(owner)}/{urllib.parse.quote(slug)}")
   record["download"]="DOWNLOADED";record["download_bytes"]=len(raw);record["sha256"]=hashlib.sha256(raw).hexdigest()
   if zipfile.is_zipfile(io.BytesIO(raw)):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
     for member in z.infolist():
      if member.is_dir():continue
      fr={"ref":ref,"file":member.filename,"size":member.file_size,"metadata_only":False}
      if member.file_size<=12_000_000 and member.filename.lower().endswith(".csv"):
       with z.open(member) as f:
        text=io.TextIOWrapper(f,encoding="utf-8-sig",errors="replace",newline="")
        reader=csv.reader(text);head=next(reader,[]);count=0;first=[];last=[]
        for row in reader:
         if not row:continue
         if count==0:first=row[:5]
         last=row[:5];count+=1
        fr.update(csv_rows=count,columns="|".join(head),first_row="|".join(first),last_row="|".join(last))
      file_records.append(fr)
   else:record["download"]="DOWNLOADED_NON_ZIP_UNINSPECTED"
  except Exception as e:record["download"]="DOWNLOAD_ERROR_"+type(e).__name__;record["download_error"]=str(e)[:150]
 except Exception as e:record["status"]="METADATA_ERROR_"+type(e).__name__;record["detail"]=str(e)[:150]
 records.append(record)
def write(name,items):
 if not items:items=[{"note":"NO_ROWS"}]
 fields=list(dict.fromkeys(k for r in items for k in r))
 with (O/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(items)
write("dataset_audit.csv",records);write("file_audit.csv",file_records);write("discovery_errors.csv",errors)
(O/"manifest.json").write_text(json.dumps({"version":"4.3","queries":SEARCH,"dataset_candidates":len(records),"status_counts":dict(collections.Counter(r["status"] for r in records)),"download_limit_bytes":MAX_DOWNLOAD,"constraints":["Kaggle notebook pages are not proof of source dataset slug","CSV dates, intervals and provenance must be checked before use","Timestamp column values may need independent normalization; no assumed 5-7y coverage","Historical taker ratio parity, OI as-of and funding publication timing remain unverified","No spot substitution; no historical trading signals or live changes"],"next":"Inspect reported files, cross-check exchange source and coverage; do not merge Kaggle into replay until independently validated"},indent=2))
print(json.dumps({"candidates":len(records),"status_counts":dict(collections.Counter(r["status"] for r in records)),"errors":errors}),flush=True)
