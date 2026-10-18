#!/usr/bin/env python3
"""BTCI v8.12b honest public ALFRED download-form pilot, max 4 vintage samples."""
import datetime as dt,hashlib,http.cookiejar,io,json,os,re,urllib.request,urllib.parse,zipfile
from pathlib import Path
import boto3
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
SPEC="research/btci_v812b_alfred_public_form_pilot_prereg_2026-10-18.json"
PRIOR=("research/btci/v8.12a/runs/39148594636-1/source_audit.json",
"68fc78f3ea98a1d6167db954ff4ad8ecbffb09f3e8af260c60d3cf4b9569987d")
def sha(b):return hashlib.sha256(b).hexdigest()
def cli():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def checkedget(s,b,key,dig):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=dig:raise SystemExit("V812B_PARENT_CHANGED")
 return json.loads(raw)
def write(s,b,key,raw,typ="application/json"):
 h=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType=typ,Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=h:
  raise SystemExit("V812B_R2_READBACK_FAILED")
 return h
def choose(sel,keyword,prefer=None):
 if sel is None:raise ValueError("FORM_SELECT_FIELD_MISSING")
 entries=[(opt.get("value",""),opt.get_text(" ",strip=True)) for opt in sel.find_all("option")]
 matches=[(val,txt) for val,txt in entries if keyword.lower() in txt.lower()]
 if not matches:raise ValueError("FORM_OPTION_MISSING_"+keyword+":"+repr(entries[:10]))
 if prefer:
  m=[x for x in matches if prefer.lower() in x[1].lower()]
  if m:matches=m
 return matches[0],entries
def probe(symbol,vintage):
 url=f"https://alfred.stlouisfed.org/series/downloaddata?seid={symbol}"
 cj=http.cookiejar.CookieJar()
 op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
 headers={"User-Agent":"BTCI public economic research/8.12b","Accept":"text/html,application/zip,*/*"}
 with op.open(urllib.request.Request(url,headers=headers),timeout=30) as r:html=r.read(1000001)
 soup=BeautifulSoup(html,"html.parser")
 forms=[f for f in soup.find_all("form") if f.find(attrs={"name":"form[entered_vintage_dates]"})]
 if len(forms)!=1:raise ValueError("FORM_NOT_UNIQUE_OR_NOT_FOUND")
 form=forms[0]
 if form.get("method","GET").lower()!="post":raise ValueError("FORM_METHOD_NOT_POST")
 units_info,uoptions=choose(form.find("select",attrs={"name":"form[units]"}),"Index")
 if units_info[0]!="lin":raise ValueError("V812C_UNIT_NOT_RAW_INDEX")
 type_info,toptions=choose(form.find("select",attrs={"name":"form[file_type]"}),"Observations by Vintage Date","All Observations")
 file_info,foptions=choose(form.find("select",attrs={"name":"form[file_format]"}),"Zipped Tab Delimited Text")
 params={
 "form[units]":units_info[0],
 "form[obs_start_date]":"2017-01-01",
 "form[obs_end_date]":vintage,
 "form[entered_vintage_dates]":vintage,
 "form[file_type]":type_info[0],
 "form[file_format]":file_info[0],
 }
 for inp in form.find_all("input",attrs={"type":"hidden"}):
  if inp.get("name"):params[inp["name"]]=inp.get("value","")
 target=urllib.parse.urljoin(url,form.get("action") or url)
 if urllib.parse.urlparse(target).hostname!="alfred.stlouisfed.org":
  raise ValueError("FORM_CROSS_DOMAIN_UNTRUSTED")
 meta={"series":symbol,"vintage":vintage,
  "formChoices":{"units":units_info,"type":type_info,"fileFormat":file_info},
  "optionLabels":{"units":uoptions[:12],"type":toptions[:15],"format":foptions[:12]},
  "submittedFields":list(params),
  "downloadFormURL":url,"submitTarget":target}
 request=urllib.request.Request(target,data=urllib.parse.urlencode(params).encode(),
  headers={**headers,"Content-Type":"application/x-www-form-urlencoded"},method="POST")
 try:
  with op.open(request,timeout=40) as resp:
   data=resp.read(5_000_001)
   ctype=resp.headers.get("Content-Type","")
 except Exception as exc:
  return {**meta,"status":"PUBLIC_FORM_POST_BLOCKED",
    "error":type(exc).__name__+":"+str(exc)[:200]},None
 if len(data)>5_000_000:raise ValueError("FORM_RESPONSE_OVER_5MB")
 if not zipfile.is_zipfile(io.BytesIO(data)):
  return {**meta,"status":"PUBLIC_FORM_NO_ZIP_VINTAGE",
   "contentType":ctype,"responseBytes":len(data),
   "responseHead":BeautifulSoup(data[:20000],"html.parser").get_text(" ",strip=True)[:180]},None
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  if z.testzip() is not None:raise ValueError("VINTAGE_ZIP_CRC_FAILED")
  names=z.namelist()
  subset=[]
  for name in names:
   if z.getinfo(name).file_size>15000000:raise ValueError("VINTAGE_FILE_DECOMPRESS_TOO_LARGE")
   if name.lower().endswith((".txt",".csv",".tsv")):
    chunk=z.read(name)
    subset.append({"file":name,"bytes":len(chunk),"containsAsOfDate":vintage.encode() in chunk,
     "sampleFirstLine":chunk[:120].decode("utf-8","replace").splitlines()[0][:120] if chunk else ""})
  if not any(y["containsAsOfDate"] for y in subset):
   return {**meta,"status":"ZIP_VINTAGE_NOT_PROVEN","files":subset},None
 return {**meta,"status":"VINTAGE_ZIP_RECEIVED_DATE_PRESENT",
  "files":subset,"contentType":ctype,"responseBytes":len(data)},data

def main():
 r=(ROOT/SPEC).read_bytes();spec=json.loads(r)
 if spec["version"]!="8.12b" or spec["parent"]!={"key":PRIOR[0],"sha256":PRIOR[1]}:
  raise SystemExit("V812B_PREREG_CHANGED")
 s=cli();bucket=os.environ["R2_BUCKET"]
 parent=checkedget(s,bucket,*PRIOR)
 if parent["version"]!="8.12a" or parent["vintageSampleSuccess"]!=0:
  raise SystemExit("V812B_OLD_PILOT_CHANGED")
 prefix=f"research/btci/v8.12b/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 outcomes=[]
 for symbol in spec["sampleSeries"]:
  for asof in spec["testVintages"]:
   try:meta,data=probe(symbol,asof)
   except Exception as exc:meta={"series":symbol,"vintage":asof,"status":"FORM_OR_SOURCE_UNSUPPORTED",
      "error":type(exc).__name__+":"+str(exc)[:200]};data=None
   if data is not None:
    key=prefix+f"sources/{symbol}_vintage_{asof}.zip"
    meta["sha256"]=write(s,bucket,key,data,"application/zip");meta["r2Key"]=key
   outcomes.append(meta)
 result={"version":"8.12b","researchOnly":True,
  "status":"FOUR_ZIP_VINTAGES_AVAILABLE" if sum(x["status"]=="VINTAGE_ZIP_RECEIVED_DATE_PRESENT" for x in outcomes)==4 else "PUBLIC_FORM_VINTAGES_NOT_FULLY_VERIFIED",
  "parent":{"key":PRIOR[0],"sha256":PRIOR[1]},"preregSha256":sha(r),
  "samples":outcomes,
  "caution":"A returned ZIP containing a date still needs full observation-level, publication-time and revision-integrity parsing before use as NFCI historical point-in-time factor.",
  "macroModelScored":False,"changedTradingOrPortfolio":False}
 folder=Path("btci_v812b_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(result,ensure_ascii=False,indent=2).encode()
 (folder/"public_form_pilot.json").write_bytes(raw)
 d=write(s,bucket,prefix+"pilot.json",raw)
 m=write(s,bucket,prefix+"manifest.json",json.dumps({"version":"8.12b","status":result["status"],
  "reportSha256":d,"researchOnly":True},ensure_ascii=False,indent=2).encode())
 summary={"status":"V812B_FORM_PILOT_WRITEBACK_VERIFIED","research":result["status"],
  "prefix":prefix,"sha256":d,"manifestSha256":m,"samples":outcomes}
 (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V812B_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
