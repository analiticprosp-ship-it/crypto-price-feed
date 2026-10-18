#!/usr/bin/env python3
"""BTCI v8.9a vintage source pilot: R2 copies of originally dated Fed H4.1 HTML.
Not historical macro factor modeling, not P&L/trades. Each page may have revisions.
"""
import datetime as dt,hashlib,json,os,re,urllib.request
from pathlib import Path
import boto3
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
P="research/btci_v89a_h41_pit_pilot_prereg_2026-10-18.json"
def hash(x):return hashlib.sha256(x).hexdigest()
def cli():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def checked(s,b,key,blob,typ):
 dg=hash(blob)
 s.put_object(Bucket=b,Key=key,Body=blob,ContentType=typ,
  Metadata={"sha256":dg,"research-only":"true"})
 if hash(s.get_object(Bucket=b,Key=key)["Body"].read())!=dg:
  raise SystemExit("V89A_R2_READBACK_FAIL:"+key)
 return dg
def audit(raw,release):
 soup=BeautifulSoup(raw,"html.parser")
 text=soup.get_text(" ",strip=True)
 expected=dt.date.fromisoformat(release).strftime("%B %d, %Y").replace(" 0"," ")
 if expected.lower() not in text.lower():
  raise ValueError("UNVERIFIED_RELEASE_DATE:"+release)
 if "H.4.1" not in text and "H4.1" not in text:raise ValueError("H41_MARKER_MISSING")
 keywords=["Reverse repurchase agreements","U.S. Treasury, General Account",
  "Factors Affecting Reserve Balances","Reserve balances with Federal Reserve Banks"]
 found={k:k.lower() in text.lower() for k in keywords}
 if not all(found.values()):raise ValueError("KEY_H41_LINES_MISSING:"+repr(found))
 return {"releaseDate":release,"dateAppearsOnPage":expected,
  "contentType":"text/html","controls":found,
  "historicalPageMayHaveBeenRevised":True,
  "seriesValuesParsed":False,
  "firstEligibleCompletedSundayUTC":(
   dt.date.fromisoformat(release)+dt.timedelta(days=(6-dt.date.fromisoformat(release).weekday())%7)
  ).isoformat()}
def main():
 pre=(ROOT/P).read_bytes();spec=json.loads(pre)
 if spec["version"]!="8.9a" or len(spec["releaseDates"])!=6:
  raise SystemExit("V89A_PREREG_CHANGED")
 s=cli();b=os.environ["R2_BUCKET"]
 root=f"research/btci/v8.9a/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 captured=[]
 for release in spec["releaseDates"]:
  token=release.replace("-","")
  url=spec["sourceTemplate"].replace("YYYYMMDD",token)
  req=urllib.request.Request(url,headers={"User-Agent":"BTCI/8.9a historical public release archiving","Accept":"text/html"})
  with urllib.request.urlopen(req,timeout=30) as r:
   body=r.read(1_500_001)
  if len(body)>1_500_000:raise SystemExit("V89A_OVERLONG_HTML:"+release)
  record=audit(body,release)
  key=root+f"official_fed_h41/{token}/original_release_page.html"
  dg=checked(s,b,key,body,"text/html; charset=utf-8")
  record.update({"originalUrl":url,"r2Key":key,"sha256":dg,"bytes":len(body)})
  captured.append(record)
  print("V89A_ORIGINAL_ARCHIVED",release,dg,flush=True)
 report={"version":"8.9a","status":"SAMPLE_H41_ORIGINALLY_DATED_RELEASES_ARCHIVED",
  "researchOnly":True,"capturedAtUTC":dt.datetime.now(dt.timezone.utc).isoformat(),
  "preregistration":{"path":P,"sha256":hash(pre)},
  "releaseCount":len(captured),"releases":captured,
  "nextSteps":["Expand full historical releases and compare 52-week BTC context using as-of release timestamps",
   "Independently parse all unique Wednesday-level TGA/reserve balances/reverse repos versus the exact original section",
   "Source Chicago Fed NFCI historical vintages and publication-date controls",
   "Construct and test ablation BTC-only vs BTC+financial conditions on separated walk-forward eras"],
  "PITLimitation":"Dated historical release pages retrieved today may reflect later page updates; original release time is not cryptographically attested, numeric values not yet parsed. SAFE archive pilot only.",
  "validation":"Only source availability and date/line control verified; NOT an early cycle predictor, no macro coefficients.",
  "operationalChanges":False}
 folder=Path("btci_v89a_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"source_pilot.json").write_bytes(raw)
 digest=checked(s,b,root+"pilot.json",raw,"application/json")
 manifest={"version":"8.9a","status":"H41_RELEASE_SAMPLE_PILOT_PASS",
    "reportSha256":digest,"prefix":root,"researchOnly":True}
 msha=checked(s,b,root+"manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2).encode(),"application/json")
 summary={"status":"V89A_H41_RELEASE_SAMPLES_PASS_WRITEBACK_VERIFIED",
  "releaseCount":len(captured),"first":captured[0]["releaseDate"],"last":captured[-1]["releaseDate"],
  "sha256":digest,"manifestSha256":msha,"prefix":root,
  "released":[{"date":x["releaseDate"],"nextSunday":x["firstEligibleCompletedSundayUTC"],
               "r2key":x["r2Key"],"sha256":x["sha256"]} for x in captured]}
 (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V89A_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
