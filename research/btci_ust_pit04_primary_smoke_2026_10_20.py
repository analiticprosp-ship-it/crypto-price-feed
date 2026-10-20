"""BTCI UST PIT04: primary archival sample, strictly research only."""
import os,io,re,json,time,hashlib,zipfile,datetime,html,pathlib
import requests
from bs4 import BeautifulSoup
OUT=pathlib.Path("btci_pit04_primary"); OUT.mkdir(exist_ok=True)
PARENT_SHA="539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091"
CASES=[
 ("2013-06-06","2013-06-09",41025,2026257),
 ("2018-06-07","2018-06-10",289454,2031965),
 ("2024-10-03","2024-10-06",823412,3097210),
 ("2014-03-06","2014-03-09",None,None),
 ("2018-03-08","2018-03-11",None,None),
 ("2023-03-09","2023-03-12",None,None),
 ("2025-03-06","2025-03-09",None,None)]
session=requests.Session(); session.headers.update({"User-Agent":"BTCI-original-release-research-only/1.0"})
def sha(b):return hashlib.sha256(b).hexdigest()
def fetch(url, auth=False):
    h={"Authorization":"Bearer "+os.environ["GITHUB_TOKEN"],"Accept":"application/vnd.github+json"} if auth else {}
    t=time.monotonic()
    try:
        r=session.get(url,timeout=(5,8),headers=h,allow_redirects=True)
        meta={"url":url,"final_url":r.url,"http_code":r.status_code,"elapsed_sec":round(time.monotonic()-t,2),"content_type":r.headers.get("Content-Type"),"last_modified_HTTP_NOT_FIRST_PUBLISHED":r.headers.get("Last-Modified"),"sha256":sha(r.content),"bytes":len(r.content)}
        r.raise_for_status()
        return r.content,meta
    except Exception as e:
        return None,{"url":url,"elapsed_sec":round(time.monotonic()-t,2),"error":str(e)[:500]}
def firstmatch(s, term):
    lines=s.get_text().splitlines()
    for ln in lines[:230]:
        if term.lower() in ln.lower():
            numbers=re.findall(r"(?<![A-Za-z0-9])[-]?[0-9]{1,3}(?:,[0-9]{3})+(?![A-Za-z0-9])",ln)
            if numbers:return int(numbers[-1].replace(",","")),"PRE_LINE"
    el=s.find(string=re.compile(re.escape(term),flags=re.I))
    if el:
        tr=el.find_parent("tr")
        if tr:
            cells=tr.find_all(["td","th"])
            vals=[]
            for c in cells[1:]:
                v=c.get_text(" ",strip=True).replace(",","").replace("\u00a0","").strip()
                if re.fullmatch(r"[-]?[0-9]+",v):vals.append(int(v))
            if vals:return vals[-1],"TABLE_LAST_CELL"
    return None,"NOT_EXTRACTED"
rows=[];rawfiles={}
for rel,sunday,expected_tga,expected_res in CASES:
    url="https://www.federalreserve.gov/releases/h41/"+rel.replace("-","")+"/"
    raw,meta=fetch(url)
    row={"release_date":rel,"decision_sunday":sunday,"source":meta,"strict_original_vintage_verified":False,"pIT_for_trading":False,"source_kind":"current_official_archived_release_page"}
    if raw:
        rawfiles[rel]=raw
        soup=BeautifulSoup(raw,"html.parser")
        t,tm=firstmatch(soup,"U.S. Treasury, General Account")
        r,rm=firstmatch(soup,"Reserve balances with Federal Reserve Banks")
        row.update({"tga_million_usd":t,"reserves_million_usd":r,"tga_parse":tm,"reserves_parse":rm})
        if expected_tga is not None:
            row["pinned_tga_match"]=t==expected_tga
            row["pinned_reserve_match"]=r==expected_res
        row["contains_subsequent_revision_banner"]=("June 12, 2014" in soup.get_text() and rel.startswith("2014"))
    rows.append(row)
    (OUT/"H41_PROGRESS.json").write_text(json.dumps(rows,indent=2,ensure_ascii=False)+"\n")
    print("H41",rel,meta.get("http_code",meta.get("error","?")),row.get("tga_million_usd"),row.get("reserves_million_usd"),flush=True)
treasury_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value_month=202510"
raw,treasury=fetch(treasury_url)
if raw:
    treasury["html_contains_october_2025"]=("10/10/2025" in raw.decode("utf-8","replace"))
    rawfiles["treasury_2025_10"]=raw
    print("TREASURY",treasury.get("http_code"),len(raw),flush=True)
else:print("TREASURY_FAIL",treasury.get("error"),flush=True)
# Read canonical immutable source from GitHub Actions artifact via native token only; no writes
parent_url="https://api.github.com/repos/analiticprosp-ship-it/crypto-price-feed/actions/artifacts/12168089066/zip"
parent_raw,parent_meta=fetch(parent_url,True)
parent_status={"metadata":parent_meta,"verified":False}
if parent_raw:
    try:
        with zipfile.ZipFile(io.BytesIO(parent_raw)) as z: orig=z.read("full_historical_rise_fall.json")
        data=json.loads(orig)
        dates=[r["date"] for r in data["weeklyPanel"]]
        assert sha(orig)==PARENT_SHA and len(dates)==684 and len(set(dates))==684 and dates[0]=="2012-06-03" and dates[-1]=="2025-10-12"
        parent_status["verified"]=True
    except Exception as e:parent_status["error"]=str(e)
archive=OUT/"official_pages_as_retrieved_in_2026_SHA_only.zip"
with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED) as z:
    for d,b in rawfiles.items():z.writestr(d+".html",b)
summary={"version":"BTCI UST-PIT-04","mode":"RESEARCH_ONLY","strict_PIT_eligible_rows":0,"forecast_edge_proven":False,"candidate_source_pages_downloaded":len(rawfiles),"h41_requested":len(CASES),"h41_http_ok":sum("http_code" in r["source"] and r["source"]["http_code"]==200 for r in rows),"pinned_h41_all_numeric_matched":all(r.get("pinned_tga_match") and r.get("pinned_reserve_match") for r in rows if r["release_date"] in ("2013-06-06","2018-06-07","2024-10-03")),"canonical_parent":parent_status,"treasury":treasury,"archive_sha256":sha(archive.read_bytes()),"values_source_status":"HISTORICALLY_DATED_OFFICIAL_PAGE_AS_RETRIEVED_2026; ORIGINAL_BYTES_NOT_ATTESTED","model_training_permitted":False,"portfolio_writeback":False,"r2_writeback":False}
(OUT/"PRIMARY_PIT04_RESULT.json").write_text(json.dumps({"summary":summary,"rows":rows},ensure_ascii=False,indent=2)+"\n")
print("BTCI_PIT04_RESULT",json.dumps(summary,ensure_ascii=False),flush=True)
