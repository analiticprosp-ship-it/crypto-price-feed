#!/usr/bin/env python3
"""BTCI 8.12a: ALFRED NFCI and ANFCI vintage availability pilot.
No use of retrospectively revised financial condition values as historic truth.
"""
import datetime as dt,hashlib,json,os,re,urllib.parse,urllib.request
from pathlib import Path
import boto3
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
P="research/btci_v812a_nfci_point_in_time_prereg_2026-10-18.json"
def sha(v):return hashlib.sha256(v).hexdigest()
def cloud():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def put(s,b,key,raw,content_type="application/json"):
 h=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType=content_type,
 Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=h:
  raise SystemExit("V812A_R2_READBACK_FAILED")
 return h
def get_html(url):
 request=urllib.request.Request(url,headers={"User-Agent":"BTCI historical macro source audit /8.12a","Accept":"text/html,text/plain"})
 with urllib.request.urlopen(request,timeout=40) as resp:
  raw=resp.read(2000001)
 if len(raw)>2000000:raise ValueError("SOURCE_HTML_TOO_LONG")
 return raw
def main():
 raw_p=(ROOT/P).read_bytes();p=json.loads(raw_p)
 if p["version"]!="8.12a" or p["series"]!=["NFCI","ANFCI"]:
  raise SystemExit("V812A_FROZEN_SPEC_CHANGED")
 s=cloud();b=os.environ["R2_BUCKET"]
 folder=Path("btci_v812a_reports");folder.mkdir(exist_ok=True)
 root=f"research/btci/v8.12a/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 sources=[];vintages=[];diagnostics=[]
 try:
  calendar=get_html(p["releaseCalendar"])
  text=calendar.decode("utf-8","replace")
  segment=text.split("Release Dates:\n")[-1]
  dates=sorted(set(re.findall(r"(?m)^(?:19|20)\d{2}-\d{2}-\d{2}$",segment)))
  if len(dates)<700 or dates[0]>"2011-05-25" or dates[-1]<"2026-09-01":
   raise ValueError("NFCI_UNVERIFIED_DATE_COVERAGE:"+str(len(dates)))
  h=put(s,b,root+"sources/ALFRED_ChicagoFed_release_dates_221.txt",calendar,"text/plain; charset=utf-8")
  sources.append({"kind":"ALFRED_RELEASE_DATE_CALENDAR","status":"VALIDATED",
   "count":len(dates),"first":dates[0],"last":dates[-1],
   "sha256":h,"r2Key":root+"sources/ALFRED_ChicagoFed_release_dates_221.txt",
   "note":"Calendar may include dates of any revised series, not necessarily both NFCI and ANFCI"})
 except Exception as exc:
  sources.append({"kind":"ALFRED_RELEASE_DATE_CALENDAR","status":"SOURCE_BLOCKED",
    "reason":type(exc).__name__+":"+str(exc)[:250]})
 for symbol,url in zip(p["series"],p["formEndpoints"]):
  try:
   original=get_html(url)
   soup=BeautifulSoup(original,"html.parser")
   forms=[]
   for form in soup.find_all("form"):
    inputs=[x.get("name") for x in form.find_all(["input","select"]) if x.get("name")]
    if any("vintage" in z.lower() for z in inputs) or any("output" in z.lower() for z in inputs):
     forms.append({"method":form.get("method","GET"),"action":form.get("action"),
      "fieldNames":inputs[:50]})
   key=root+f"sources/{symbol}_ALFRED_download_form.html"
   dig=put(s,b,key,original,"text/html; charset=utf-8")
   sources.append({"kind":"PUBLIC_ALFRED_FORM","series":symbol,
     "status":"HTML_SAVED_NO_VINTAGE_PROVEN",
     "r2Key":key,"sha256":dig,"forms":forms[:3]})
  except Exception as exc:
   sources.append({"kind":"PUBLIC_ALFRED_FORM","series":symbol,
    "status":"SOURCE_BLOCKED","reason":type(exc).__name__+":"+str(exc)[:250]})
 secret=os.getenv("FRED_API_KEY","")
 if re.fullmatch("[a-z0-9]{32}",secret):
  for symbol in p["series"]:
   for asof in p["initialAsOfVintages"]:
    params={"series_id":symbol,"api_key":secret,"file_type":"json",
     "realtime_start":asof,"realtime_end":asof,
     "observation_start":"2010-01-01","observation_end":asof,"limit":10000}
    req=urllib.request.Request("https://api.stlouisfed.org/fred/series/observations?"+
       urllib.parse.urlencode(params),headers={"User-Agent":"BTCI-8.12a","Accept":"application/json"})
    try:
     with urllib.request.urlopen(req,timeout=40) as r:raw=r.read(1000001)
     obj=json.loads(raw)
     if obj.get("realtime_start")!=asof or obj.get("realtime_end")!=asof:
      raise ValueError("REALTIME_WINDOW_NOT_CONFIRMED")
     data=[q for q in obj.get("observations",[]) if q.get("value") not in ("",None,".")]
     if not data or any(q.get("date", "9999")>asof or q.get("realtime_start")>asof for q in data):
      raise ValueError("INVALID_VINTAGE_OBSERVATION")
     filename=root+f"sources/vintages/{symbol}_{asof}.json"
     vhash=put(s,b,filename,raw)
     vintages.append({"series":symbol,"asOfDate":asof,"status":"HISTORICAL_VINTAGE_DATA_ARCHIVED",
       "r2Key":filename,"sha256":vhash,"historicObservations":len(data),
       "lastObservation":{"date":data[-1]["date"],"value":data[-1]["value"]},
       "intradayPublicationTimeVerified":False})
    except Exception as exc:
     vintages.append({"series":symbol,"asOfDate":asof,"status":"VINTAGE_FETCH_BLOCKED",
      "reason":type(exc).__name__+":"+str(exc)[:190]})
 else:
  diagnostics.append("FRED_API_KEY was not available as a valid installed repository secret; FRED/ALFRED historical values cannot be called through authenticated API in this run.")
  for symbol in p["series"]:
   vintages.append({"series":symbol,"status":"VINTAGE_DATA_ACCESS_NOT_AUTHORIZED",
    "reason":"FRED API key not configured in GitHub Actions; no revised current proxy substituted"})
 ok=sum(x["status"]=="HISTORICAL_VINTAGE_DATA_ARCHIVED" for x in vintages)
 result={"version":"8.12a","researchOnly":True,
  "status":"VINTAGE_SOURCE_PILOT_PASS" if ok==len(p["series"])*len(p["initialAsOfVintages"]) else "VINTAGE_ACCESS_INCOMPLETE",
  "capturedUTC":dt.datetime.now(dt.timezone.utc).isoformat(),
  "preregistration":{"path":P,"sha256":sha(raw_p)},
  "sources":sources,"vintageSample":vintages,
  "vintageSampleSuccess":ok,"vintageSampleExpected":8,
  "diagnostics":diagnostics,
  "nextStep":"Only after 8 verified source vintages and full release-asof history, perform BTC cycle NFCI ablation. Otherwise do not claim NFCI model tested.",
  "caution":"2011 release-history of NFCI has retrospective pre-2011 index values; never assume known before actual initial release.",
  "operations":{"marketDataUsedForTrades":False,"NAVModified":False,
   "SpotModified":False,"FuturesModified":False,"LimitsModified":False}}
 raw=json.dumps(result,ensure_ascii=False,indent=2).encode()
 (folder/"source_audit.json").write_bytes(raw)
 dg=put(s,b,root+"source_audit.json",raw)
 manifest={"version":"8.12a","reportSha256":dg,"status":result["status"],
  "researchOnly":True,"preregSha256":sha(raw_p)}
 md=put(s,b,root+"manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2).encode())
 brief={"status":"V812A_PILOT_SOURCE_MANIFEST_READBACK_VERIFIED",
  "sourceAccess":result["status"],"prefix":root,"sha256":dg,"manifestSha256":md,
  "vintageOk":ok,"vintageExpected":8,"sources":sources,"vintages":vintages,
  "diagnostics":diagnostics}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V812A_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
