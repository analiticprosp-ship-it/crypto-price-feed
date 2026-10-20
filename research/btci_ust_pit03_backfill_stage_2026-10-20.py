"""BTCI UST-PIT-03 | research-only, current-backfill staging; not historically PIT."""
import os,io,csv,json,zipfile,hashlib,datetime,time,pathlib,requests
OUT=pathlib.Path("btci_pit03_output");OUT.mkdir(exist_ok=True)
SHA="539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091"
SYMS=["DGS2","DGS10","DFII10","WDTGAL","WRESBAL","WALCL","RRPONTSYD"]
s=requests.Session();s.headers.update({"User-Agent":"BTCI-Research-Only/0.1"})
def digest(raw):return hashlib.sha256(raw).hexdigest()
def get(url,auth=False):
    for attempt in range(2):
        try:
            h={"Accept":"application/vnd.github+json","Authorization":"Bearer "+os.environ["GITHUB_TOKEN"]} if auth else {}
            r=s.get(url,headers=h,timeout=(5,12));r.raise_for_status()
            return r.content,{"url":url,"resolved_url":r.url,"sha256":digest(r.content),"bytes":len(r.content),"status_code":r.status_code}
        except Exception as e:
            error=str(e);time.sleep(2**attempt)
    raise RuntimeError("FETCH_FAILED "+url+" "+error)
raw,original=get("https://api.github.com/repos/analiticprosp-ship-it/crypto-price-feed/actions/artifacts/12168089066/zip",True)
with zipfile.ZipFile(io.BytesIO(raw)) as z: panelraw=z.read("full_historical_rise_fall.json")
assert digest(panelraw)==SHA,"PARENT_SHA_MISMATCH"
p=json.loads(panelraw)
assert p.get("researchOnly") is True and p.get("tradeApproval") is False
panel=p["weeklyPanel"];dates=[v["date"] for v in panel]
assert len(dates)==684 and dates==sorted(set(dates)) and dates[0]=="2012-06-03" and dates[-1]=="2025-10-12"
series={};logs=[]
for sid in SYMS:
    errors=[]
    for u in ["https://fred.stlouisfed.org/graph/fredgraph.csv?id="+sid,"https://fred.stlouisfed.org/graph/fredgraph.csv?cosd=2012-01-01&coed=2025-10-12&id="+sid]:
        try:
            raw,meta=get(u);t=raw.decode("utf-8-sig")
            assert "observation_date" in t[:140].lower() or "DATE" in t[:100],"not csv"
            rdr=csv.DictReader(io.StringIO(t));h=rdr.fieldnames
            assert h and len(h)>1
            dk=h[0];vk=sid if sid in h else h[1];vals={}
            for rec in rdr:
                d=rec.get(dk);v=rec.get(vk)
                if not d or not v or v.strip() in [".","","NA","null"]:continue
                if "2012-01-01"<=d<="2025-10-12":
                    f=float(v);assert f==f and abs(f)<1e12;vals[d]=f
            assert len(vals)>250,"TOO_FEW_POINTS"
            series[sid]=vals;meta.update({"id":sid,"numeric_points":len(vals),"first":min(vals),"last":max(vals),"status":"CURRENT_BACKFILL_NOT_ORIGINAL_VINTAGE"});logs.append(meta)
            print("OK",sid,len(vals),flush=True)
            break
        except Exception as e:errors.append(str(e))
    if sid not in series:
        logs.append({"id":sid,"status":"FETCH_FAILED","errors":errors});print("FAILED",sid,str(errors)[:1500],flush=True)
    (OUT/'SOURCE_DIAGNOSTIC_PARTIAL.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if len(series)<3:print('INSUFFICIENT_SOURCE_COVERAGE',len(series),'of',len(SYMS),flush=True)
def asof(sid,decision,maxdays):
    vals=series.get(sid,{})
    can=[d for d in vals if d<decision and 0<(datetime.date.fromisoformat(decision)-datetime.date.fromisoformat(d)).days<=maxdays]
    if not can:return None
    last=max(can)
    return {"obsDate":last,"value":vals[last],"daysOld":(datetime.date.fromisoformat(decision)-datetime.date.fromisoformat(last)).days}
joined=[]
for point in panel:
    d=point["date"]
    f={sid:asof(sid,d,8 if sid in ["DGS2","DGS10","DFII10","RRPONTSYD"] else 12) for sid in SYMS}
    spread=round(f["DGS10"]["value"]-f["DGS2"]["value"],6) if f["DGS10"] and f["DGS2"] else None
    joined.append({"date":d,"features":f,"UST10y_minus_2y_pct_points":spread,"source_status":"CURRENT_BACKFILL_NOT_HISTORICALLY_VERIFIED","strict_pit":False})
assert len(joined)==684 and [x["date"] for x in joined]==dates
summary={"schema":"btci_ust_pit03_current_backfill_v1","canonical":"BTCI v8.18d7","original_report_sha256":SHA,"immutable_684_dates":True,"mode":"RESEARCH_ONLY","trade_authority":False,"original_release_time_verified":False,"current_fred_vintages_not_strict_pit":True,"WRESBAL_is_weekly_average_not_h41_Wednesday_level":True,"no_model_fit":True,"coverage":{sid:sum(x["features"][sid]!=None for x in joined) for sid in SYMS},"yield_spread_coverage":sum(x["UST10y_minus_2y_pct_points"]!=None for x in joined),"failed_series":[x["id"] for x in logs if x.get("status")=="FETCH_FAILED"],"portfolio_writeback":False}
for name,body in [("btci_684_macro_backfill_join.json",{"summary":summary,"rows":joined}),("source_sha256_log.json",logs),("coverage.json",summary)]:
    (OUT/name).write_text(json.dumps(body,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
summary["join_sha256"]=digest((OUT/"btci_684_macro_backfill_join.json").read_bytes())
(OUT/"RESULT.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
print("BTCI_PIT03_RESULT",json.dumps(summary,ensure_ascii=False),flush=True)
