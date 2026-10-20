"""BTCI H4.1 archive replay v8.18d7, independent frozen-date primary evidence only."""
import os,sys,io,re,json,time,zipfile,hashlib,datetime,pathlib
import requests
from bs4 import BeautifulSoup
ROOT=pathlib.Path("btci_pit05_h41"); ROOT.mkdir(exist_ok=True)
ERA=os.environ.get("BTCI_ERA","2012-2016")
SPAN={"2012-2016":(2012,2016),"2017-2020":(2017,2020),"2021-2025":(2021,2025)}
assert ERA in SPAN
PARENT="539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091"
REPO="https://api.github.com/repos/analiticprosp-ship-it/crypto-price-feed/actions/artifacts/12168089066/zip"
PIN={
"2013-06-06":(41025,2026257),"2014-06-05":(31902,2708064),
"2015-06-04":(184099,2490044),"2016-06-02":(259693,2400969),
"2017-06-08":(154760,2270846),"2018-06-07":(289454,2031965),
"2019-06-06":(207647,1559710),"2020-07-30":(1792434,2685376),
"2021-06-03":(812087,3848262),"2022-06-02":(780575,3357395),
"2023-06-08":(77500,3306154),"2024-06-06":(703314,3457738),
"2024-10-03":(823412,3097210),"2025-06-05":(376160,3361938),
"2025-10-09":(794054,3033855)}
S=requests.Session();S.headers.update({"User-Agent":"BTCI-public-h41-research/2026-10-20 scientific replay"})
def hashbytes(b):return hashlib.sha256(b).hexdigest()
def get(url,token=None):
    h={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"} if token else {}
    try:
        r=S.get(url,headers=h,timeout=(5,9));r.raise_for_status()
        return r.content,{"http":r.status_code,"bytes":len(r.content),"sha256":hashbytes(r.content),"content_type":r.headers.get("Content-Type"),"last_modified_current_http_not_original_publication":r.headers.get("Last-Modified")}
    except Exception as e:return None,{"error":str(e)[:420]}
def number(s): 
    x=s.replace(",","").replace("\u00a0","").strip()
    return int(x) if re.fullmatch(r"[-]?[0-9]+",x) else None
def get_table1_num(soup,needle):
    # 2012–2020 releases often use preformatted ASCII tables
    pre=soup.find("pre")
    if pre:
        for line in pre.get_text().splitlines()[:140]:
            if needle.lower() in line.lower():
                n=re.findall(r"(?<![A-Za-z0-9])-?[0-9]{1,3}(?:,[0-9]{3})+(?![A-Za-z0-9])",line)
                if n:return int(n[-1].replace(",",""))
    # modern releases use HTML tables
    for tr in soup.find_all("tr")[:125]:
        cells=tr.find_all(["td","th"],recursive=False)
        if not cells:continue
        label=cells[0].get_text(" ",strip=True)
        if needle.lower() not in label.lower():continue
        vals=[number(c.get_text(" ",strip=True)) for c in cells[1:]]
        vals=[v for v in vals if v is not None]
        if vals:return vals[-1]
    return None
raw,meta=get(REPO,os.environ["GITHUB_TOKEN"])
assert raw is not None, "ORIGINAL_GITHUB_ARTIFACT_UNAVAILABLE "+str(meta)
with zipfile.ZipFile(io.BytesIO(raw)) as z:orig=z.read("full_historical_rise_fall.json")
assert hashbytes(orig)==PARENT,"ORIGINAL_684_SHA_CHANGED"
panel=json.loads(orig)
assert panel["researchOnly"] is True and panel["tradeApproval"] is False
dates=[r["date"] for r in panel["weeklyPanel"]]
assert len(dates)==684 and dates==sorted(set(dates)) and dates[0]=="2012-06-03" and dates[-1]=="2025-10-12"
dates=[x for x in dates if SPAN[ERA][0]<=int(x[:4])<=SPAN[ERA][1]]
rows=[];url_cache={}
rawarchive=ROOT/("official_h41_pages_current_retrieval_"+ERA+".zip")
with zipfile.ZipFile(rawarchive,"w",compression=zipfile.ZIP_DEFLATED) as z:
  for i,d in enumerate(dates):
    decision=datetime.date.fromisoformat(d)
    thursday=decision-datetime.timedelta(days=3)
    found=False;attempts=[]
    for shift in (0,1):
      rd=thursday+datetime.timedelta(days=shift)
      rel=rd.isoformat();url="https://www.federalreserve.gov/releases/h41/"+rd.strftime("%Y%m%d")+"/"
      if url not in url_cache:url_cache[url]=get(url)
      html,stat=url_cache[url]
      attempts.append({"release_date":rel,"url":url,**stat})
      if not html:continue
      soup=BeautifulSoup(html,"html.parser")
      t=get_table1_num(soup,"U.S. Treasury, General Account")
      r=get_table1_num(soup,"Reserve balances with Federal Reserve Banks")
      # Only accept tables with both figures; avoid mixing last week values with Wednesday column.
      if t is None or r is None:continue
      label=soup.get_text(" ",strip=True)[:900]
      month=rd.strftime("%B");day=str(rd.day)
      if month.lower() not in label.lower() or day not in label:continue
      match=(t,r)==PIN[rel] if rel in PIN else None
      archive_path=rd.strftime("%Y%m%d")+".html"
      z.writestr(archive_path,html)
      rows.append({"btc_decision_sunday":d,"release_date":rel,"obs_wednesday":(rd-datetime.timedelta(days=1)).isoformat(),"tga_wednesday_million_usd":t,"reserve_balances_wednesday_million_usd":r,"official_url":url,"downloaded_page_sha256":stat["sha256"],"pinned_match":match,"original_publication_bytes_verified":False,"strict_pit_eligible":False,"revision_notice_possible":("June 12, 2014" in soup.get_text() and rd.year==2014),"status":"DATED_OFFICIAL_PAGE_AS_RETRIEVED_2026","original_market_availability_timestamp_proven":False})
      found=True
      break
    if not found:
      rows.append({"btc_decision_sunday":d,"status":"NO_VALID_PRIMARY_RELEASE","attempts":attempts,"strict_pit_eligible":False})
    if (i+1)%20==0:
      (ROOT/("progress_"+ERA+".json")).write_text(json.dumps({"processed":i+1,"requested":len(dates),"success":sum(x.get("status")=="DATED_OFFICIAL_PAGE_AS_RETRIEVED_2026" for x in rows),"missing":sum(x.get("status")=="NO_VALID_PRIMARY_RELEASE" for x in rows)},indent=2)+"\n")
      print("PROGRESS",ERA,i+1,len(dates),flush=True)
    time.sleep(0.24)
for p in rows:
 if p.get("pinned_match") is False:
   print("PARENT_NUMERIC_MISMATCH",p["release_date"],flush=True)
summary={"protocol":"BTCI UST PIT05","parent_version":"8.18d7","research_only":True,"era":ERA,"original_panel_sha256":PARENT,"all_canonical_684_dates_unchanged":True,"requested":len(dates),"dated_page_with_tga_reserves":sum(x.get("status")=="DATED_OFFICIAL_PAGE_AS_RETRIEVED_2026" for x in rows),"missing_or_unparsed":sum(x.get("status")=="NO_VALID_PRIMARY_RELEASE" for x in rows),"pinned_matches":sum(x.get("pinned_match") is True for x in rows),"pinned_mismatches":[x["release_date"] for x in rows if x.get("pinned_match") is False],"strict_pit_eligible":0,"model_fit":False,"predictive_edge_proven":False,"main_writeback":False,"r2_writeback":False,"portfolio_writeback":False,"raw_archive_sha256":hashbytes(rawarchive.read_bytes()),"source_status":"Dated official historic H4.1 pages retrieved 2026, not original first-release bytes; revisions possible."}
(ROOT/("h41_"+ERA+"_SOURCE_ONLY_FULL.json")).write_text(json.dumps({"summary":summary,"rows":rows},indent=2,ensure_ascii=False)+"\n")
(ROOT/("summary_"+ERA+".json")).write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
print("BTCI_PIT05_RESULT",json.dumps(summary,ensure_ascii=False),flush=True)
