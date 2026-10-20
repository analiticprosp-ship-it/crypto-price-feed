#!/usr/bin/env python3
"""BTCI Research Engine v0.1. RESEARCH_ONLY. Never grants trade authority."""
import argparse, csv, datetime as dt, hashlib, io, json, os, pathlib, re, sys, time, zipfile
import requests
from bs4 import BeautifulSoup
PARENT_SHA = "539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091"
PARENT_RUN = "39212878778"
PARENT_ARTIFACT = "12168089066"
ARCHIVE = "https://api.github.com/repos/analiticprosp-ship-it/crypto-price-feed/actions/artifacts/" + PARENT_ARTIFACT + "/zip"
MISSING_H41 = ("2014-12-28","2016-11-20","2019-12-01","2020-12-27")
TRACKS = ("audit","h41","treasury","mvrv")
FIXTURES = pathlib.Path("fixtures")
RUN_TAG = "RESEARCH_ONLY"
def sh(data): return hashlib.sha256(data).hexdigest()
def dump(path, val):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(val,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def retrieve(url, session, token=None):
    headers = {"Accept":"application/vnd.github+json","Authorization":"Bearer "+token} if token else {}
    start=time.monotonic()
    try:
        r=session.get(url,headers=headers,timeout=(5,12),allow_redirects=True)
        r.raise_for_status()
        b=r.content
        return b,{"url":url,"http":r.status_code,"sha256":sh(b),"bytes":len(b),"elapsed_s":round(time.monotonic()-start,3),"captured_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"http_last_modified_not_original_publication":r.headers.get("Last-Modified")}
    except requests.RequestException as exc:
        return None,{"url":url,"error":str(exc)[:500],"elapsed_s":round(time.monotonic()-start,3)}
def immutable_parent(session):
    path=FIXTURES/"BTCI_v8171_684_MACRO_ORIGINAL.zip"
    if path.is_file():
        zbytes=path.read_bytes(); origin="PORTABLE_LOCAL_FROZEN"
    else:
        token=os.environ.get("GITHUB_TOKEN","")
        zbytes,m=retrieve(ARCHIVE,session,token or None)
        if not zbytes: raise RuntimeError("CANONICAL_PARENT_MISSING: local fixture absent, GitHub artifact inaccessible: "+str(m))
        origin="TEMP_GITHUB_ACTIONS_ARTIFACT_EXPIRING"
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        raw=z.read("full_historical_rise_fall.json")
    if sh(raw)!=PARENT_SHA:raise RuntimeError("CANONICAL_PARENT_SHA_MISMATCH")
    doc=json.loads(raw)
    dates=[p["date"] for p in doc["weeklyPanel"]]
    if not(doc.get("researchOnly") is True and doc.get("tradeApproval") is False and len(dates)==684 and dates==sorted(set(dates)) and dates[0]=="2012-06-03" and dates[-1]=="2025-10-12"):
        raise RuntimeError("CANONICAL_PARENT_INVARIANT_BROKEN")
    return dates,{"parent_sha256":PARENT_SHA,"origin":origin,"weeks":len(dates),"btc_only_old_results_preserved":True}
def read_join(dates):
    p=FIXTURES/"BTCI_684_UST_H41_MVRV_SOURCE_ONLY_JOIN.json"
    if not p.is_file():return {"available":False,"reason":"PIT07_JOIN_FIXTURE_NOT_YET_INSTALLED","strict_pit_eligible":0}
    doc=json.loads(p.read_text(encoding="utf-8"))
    rows=doc["rows"]
    got=[r["btc_sunday_utc"] for r in rows]
    if got!=dates or len(rows)!=684:raise RuntimeError("PIT07_DATE_ALIGNMENT_FAIL")
    if any(r.get("strict_pit_eligible") is not False or r.get("trading_authority") is not False for r in rows):
        raise RuntimeError("PIT07_UNAUTHORIZED_PIT_PROMOTION")
    h=sum(x.get("h41",{}).get("tga_wednesday_million_usd") is not None for x in rows)
    u=sum(x.get("UST",{}).get("nominal_2y_pct") is not None and x.get("UST",{}).get("real_10y_pct") is not None for x in rows)
    w=sum(x.get("MVRV",{}).get("historically_dated_witness") is True for x in rows)
    if (h,u,w)!=(680,684,31):raise RuntimeError("PIT07_REPLAY_COUNTS_DIFFER")
    return {"available":True,"historically_dated_h41_candidates":h,"treasury_nominal_and_real_candidates":u,"mvrv_prior_witnesses":w,"strict_pit_eligible":0,"join_sha256":sh(p.read_bytes())}
def sources(track,mode,session,out):
    if mode=="offline":return [{"status":"NOT_QUERIED_OFFLINE","track":track}]
    entries=[]
    if track=="h41":
        for sunday in MISSING_H41:
            decision=dt.date.fromisoformat(sunday)
            old=decision-dt.timedelta(days=3)
            candidate_dates=[old+dt.timedelta(days=i) for i in (-1,0,1)]
            for day in candidate_dates:
                url="https://www.federalreserve.gov/releases/h41/"+day.strftime("%Y%m%d")+"/"
                raw,meta=retrieve(url,session)
                meta.update({"sunday":sunday,"source_type":"H41","release_date_candidate":day.isoformat(),"PIT":"CANDIDATE_ONLY_NOT_FIRST_RELEASE"})
                if raw:
                    page=BeautifulSoup(raw,"html.parser").get_text(" ",strip=True)
                    meta["has_tga_label"]="U.S. Treasury, General Account" in page
                    meta["has_reserves_label"]="Reserve balances with Federal Reserve Banks" in page
                    (out/"raw"/(day.strftime("%Y%m%d")+".html")).parent.mkdir(parents=True,exist_ok=True)
                    (out/"raw"/(day.strftime("%Y%m%d")+".html")).write_bytes(raw)
                entries.append(meta)
                if raw and meta.get("has_tga_label") and meta.get("has_reserves_label"):break
    elif track=="treasury":
        for month in ("202410","202510"):
            url=("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                 "daily-treasury-rates.csv/all/"+month+
                 "?type=daily_treasury_yield_curve&field_tdr_date_value_month="+month+"&page=&_format=csv")
            raw,meta=retrieve(url,session)
            meta.update({"source_type":"TREASURY_2Y_10Y","month":month,"PIT":"OFFICIAL_2026_RETRIEVAL_CANDIDATE"})
            if raw:
                text=raw.decode("utf-8-sig",errors="replace")
                meta["csv_has_header"]="Date" in text[:250] and "10-year" in text[:250].lower()
                (out/"raw"/("treasury_"+month+".csv")).parent.mkdir(parents=True,exist_ok=True)
                (out/"raw"/("treasury_"+month+".csv")).write_bytes(raw)
            entries.append(meta)
    elif track=="mvrv":
        # Preserve 31 pre-existing witnesses; discover only. No automatic PIT promotion.
        url="https://api.github.com/repos/coinmetrics/data/commits?path=csv/btc.csv&per_page=1"
        raw,meta=retrieve(url,session)
        meta.update({"source_type":"MVRV_RESEARCH_LEAD","PIT":"LEAD_ONLY_NOT_DATE_WITNESS"})
        entries.append(meta)
    return entries
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--track",choices=TRACKS,required=True)
    p.add_argument("--mode",choices=("offline","smoke","daily"),default="smoke")
    p.add_argument("--out",default="out")
    a=p.parse_args()
    out=pathlib.Path(a.out)/a.track
    out.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    session.headers["User-Agent"]="BTCI-Research-Engine-RESEARCH-ONLY/0.1"
    result={"schema":"BTCI_RESEARCH_ENGINE_0_1","track":a.track,"mode":a.mode,
       "run_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"authority":RUN_TAG,
       "main_branch_writes":False,"R2_writes":False,"portfolio_writes":False,
       "model_training_allowed":False,"new_strict_pit_promotions":0,"negative_results_preserved":True}
    try:
        dates,base=immutable_parent(session)
        result["canonical"]=base
        result["pit07"]=read_join(dates)
        result["sources"]=sources(a.track,a.mode,session,out)
        result["source_successes"]=sum("http" in s for s in result["sources"])
        result["status"]="PASS_BASELINE_SOURCE_STAGING_NOT_PIT"
        if a.mode!="offline" and a.track!="audit" and result["source_successes"]==0:
            result["status"]="WARN_NO_SOURCE_RETRIEVED"
    except Exception as exc:
        result["status"]="FAIL_CLOSED"
        result["error"]=str(exc)
    dump(out/"RESULT.json",result)
    lines=["# BTCI Research Engine / "+a.track,"",f"**Режим:** {RUN_TAG}","",f"**Статус:** {result['status']}","",f"**Дата UTC:** {result['run_utc']}","",
        "Исходные данные BTCI, торговые правила и отрицательные результаты не менялись.",
        "Строгая PIT-аттестация новых значений автоматически не выполняется.",
        "GitHub Actions SUCCESS не подтверждает прогностическое преимущество.",
        "",f"**Новые строгие PIT-допуски:** {result['new_strict_pit_promotions']}","",
        f"**Полученных HTTP-источников:** {result.get('source_successes','нет')}",""]
    if result.get("error"):lines.append("**Ошибка:** "+result["error"])
    (out/"REPORT_RU.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("BTCI_ENGINE_RESULT",json.dumps({"track":a.track,"status":result["status"],"source_successes":result.get("source_successes",0)},ensure_ascii=False),flush=True)
    return 1 if result["status"]=="FAIL_CLOSED" else 0
if __name__=="__main__":sys.exit(main())
