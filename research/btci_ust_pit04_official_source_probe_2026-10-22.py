"""BTCI UST-PIT-04 official-source connectivity & archival backfill; RESEARCH_ONLY.
Data from current official XML are NOT verified original point-in-time vintages.
Historical H.4.1 pages are release-dated but original bytes may have been amended.
"""
import os, io, json, hashlib, pathlib, datetime as dt, zipfile, time
import requests, xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

OUT=pathlib.Path("btci_pit04_output");OUT.mkdir(exist_ok=True)
SHA="539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091"
BASE="https://api.github.com/repos/analiticprosp-ship-it/crypto-price-feed/actions/artifacts/12168089066/zip"
S=requests.Session();S.headers.update({"User-Agent":"BTCI-academic-research/0.4"})
def sha(b):return hashlib.sha256(b).hexdigest()
def load(url,authorization=False,limit=8):
    h={"Authorization":"Bearer "+os.environ["GITHUB_TOKEN"],"Accept":"application/vnd.github+json"} if authorization else {}
    r=S.get(url,headers=h,timeout=(4,limit))
    r.raise_for_status()
    return r.content, {"url":url,"sha256":sha(r.content),"bytes":len(r.content),"http_status":r.status_code,"retrieval_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
def save(obj,name):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
base_raw,base_log=load(BASE,True,15)
with zipfile.ZipFile(io.BytesIO(base_raw)) as z: original=z.read("full_historical_rise_fall.json")
assert sha(original)==SHA
p=json.loads(original);panel=p["weeklyPanel"];dates=[r["date"] for r in panel]
assert len(dates)==684 and dates[0]=="2012-06-03" and dates[-1]=="2025-10-12" and len(set(dates))==684
print("PARENT_PASS",len(dates),SHA,flush=True)
url_y="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2024"
url_r="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_real_yield_curve&field_tdr_date_value=2024"
url_h="https://www.federalreserve.gov/releases/h41/20251009/"
probe=[];success={};
for name,url in [("treasury_nominal",url_y),("treasury_real",url_r),("fed_h41",url_h)]:
    try:
        raw,meta=load(url,False,8);meta["source_name"]=name;meta["probe"]="success";meta["raw_preview"]=raw[:240].decode("utf-8","replace")
        success[name]=True
        (OUT/(name+"_probe.bin")).write_bytes(raw)
        if name.startswith("treasury"):
            root=ET.fromstring(raw)
            allkeys=sorted({x.tag.rsplit("}",1)[-1] for x in root.iter()})
            entries=[x for x in root.iter() if x.tag.rsplit("}",1)[-1]=="entry"]
            meta["xml_entries"]=len(entries);meta["xml_fields_sample"]=allkeys[:100]
        else:
            soup=BeautifulSoup(raw,"html.parser")
            content=soup.get_text(" ",strip=True)
            meta["html_has_release_date"]="October 09, 2025" in content
            meta["html_tga_text_seen"]="U.S. Treasury, General Account" in content or "Treasury, General Account" in content
            meta["html_reserves_seen"]="Reserve balances with Federal Reserve Banks" in content
        print("PROBE_OK",name,meta.get("xml_entries"),meta["bytes"],flush=True)
    except Exception as e:
        meta={"source_name":name,"url":url,"probe":"failed","error":repr(e)}
        print("PROBE_FAILED",name,str(e)[:220],flush=True)
    probe.append(meta);save(probe,"PROBE_LOG.json")
def itemfields(entry):
    return {n.tag.rsplit("}",1)[-1].upper():(n.text or "").strip() for n in entry.iter() if n.text and n.tag.rsplit("}",1)[-1].upper() in {"NEW_DATE","BC_2YEAR","BC_10YEAR","TC_10YEAR","DATE"}}
def nom_xml(raw):
    rt=ET.fromstring(raw)
    out={}
    for e in rt.iter():
        if e.tag.rsplit("}",1)[-1]!="entry":continue
        f=itemfields(e);date=(f.get("NEW_DATE") or f.get("DATE") or "")[:10]
        if len(date)!=10:continue
        obs={}
        for k in ("BC_2YEAR","BC_10YEAR","TC_10YEAR"):
            try:obs[k]=float(f[k])
            except:pass
        if obs:out[date]=obs
    return out
series={"nominal":{},"real":{}};raw_index=[]
if success.get("treasury_nominal") or success.get("treasury_real"):
    for y in range(2012,2026):
        for kind,data in [("nominal","daily_treasury_yield_curve"),("real","daily_treasury_real_yield_curve")]:
            if not success.get("treasury_"+kind):continue
            url=f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data={data}&field_tdr_date_value={y}"
            try:
                raw,metadata=load(url,False,8)
                parsed=nom_xml(raw)
                assert parsed,"NO_ROWS"
                series[kind].update(parsed);metadata.update({"year":y,"type":kind,"parsed_days":len(parsed)})
                raw_index.append(metadata)
                print("YEAR_OK",kind,y,len(parsed),flush=True)
            except Exception as e:
                raw_index.append({"url":url,"year":y,"type":kind,"error":repr(e)})
                print("YEAR_FAILED",kind,y,str(e)[:140],flush=True)
            save(raw_index,"ARCHIVE_DOWNLOAD_LOG.json")
def val(v,k):
    try:return v[k]
    except:return None
joined=[]
for d in dates:
    date=dt.date.fromisoformat(d)
    look=[(date-dt.timedelta(days=n)).isoformat() for n in (2,3,4,5,6,7,8)]
    def mostrecent(kind,key):
        for q in look:
            if q in series[kind] and key in series[kind][q]: return {"obsDate":q,"valuePct":series[kind][q][key],"daysOld":(date-dt.date.fromisoformat(q)).days}
        return None
    r2=mostrecent("nominal","BC_2YEAR");r10=mostrecent("nominal","BC_10YEAR");tips=mostrecent("real","TC_10YEAR")
    joined.append({"date":d,"UST2Y":r2,"UST10Y":r10,"TIPS10Y":tips,"yield_spread_10y_2y":round(r10["valuePct"]-r2["valuePct"],5) if r2 and r10 else None,"vintage_verification":"CURRENT_BACKFILL_ONLY","strict_PIT":False})
out={"mode":"RESEARCH_ONLY","canonical":"BTCI v8.18d7","parent_sha256":SHA,"parent_dates_exact":True,"zero_trades":True,"no_model_fit":True,"treasury_original_release_proven":False,"probe":probe,"archive_log":raw_index,"series_rows":{k:len(v) for k,v in series.items()},"coverage":{k:sum(r.get(k)!=None for r in joined) for k in ("UST2Y","UST10Y","TIPS10Y")},"h41_probe_success":success.get("fed_h41",False),"source_clock_verified":False,"status":"DIAGNOSTIC_ONLY_NOT_STRICT_PIT","run_source_branch":"research/btci-ust-pit04-20261022"}
save({"rows":joined,"metadata":out},"JOIN_684_CANDIDATES.json")
save(out,"RESULT.json")
print("PIT04_RESULT",json.dumps({k:out[k] for k in ["coverage","series_rows","h41_probe_success","status"]},ensure_ascii=False),flush=True)
