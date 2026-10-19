#!/usr/bin/env python3
"""Conservative BTC/ETH/SOL joint-clean source-day calendar for 2022-2023.

Read exactly eight immutable publisher-audited per-quarter R2 manifests;
SHA256 verify each original report BEFORE extracting calendar. No re-fetch,
no interpolation, no silent replacement of incomplete asset-days.
This is raw 5m *label/number* quality, not original exchange publication PIT.
"""
import collections,datetime as dt,hashlib,json,os
from pathlib import Path
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2

PINS={
"2022Q1":("research/detector-binance-oi-pre2024-quarter-calendars/v1/2022Q1/39308756529-1.json","c9ba36b579e2011a350ebaf5914e6204880be84ae7bb369aecc8659f79647a30"),
"2022Q2":("research/detector-binance-oi-2022-2023-rest-quarters/v1/2022Q2/39311042453-1.json","7c129110b5ea0cc412956269e36616138185fc3562c8e6e7431809c075e9b812"),
"2022Q3":("research/detector-binance-oi-2022-2023-rest-quarters/v1/2022Q3/39311042453-1.json","e3e3f89227ee3eb8f4b80e5b4f6269320124e3dba457fe18de1d61694bd17c4b"),
"2022Q4":("research/detector-binance-oi-2022-2023-rest-quarters/v1/2022Q4/39311042453-1.json","dcd4065f15c333289cebbe1faefc75d337c965df20b3b588d920d2aec1ba54bf"),
"2023Q1":("research/detector-binance-oi-pre2024-quarter-calendars/v1/2023Q1/39308756529-1.json","d89226756f5061dc8bcd8f84b8f59bb8733ed9c74af54bd48b5738dce308bbbc"),
"2023Q2":("research/detector-binance-oi-2022-2023-rest-quarters/v1/2023Q2/39311042453-1.json","b1668387ea4c10357dedd1cf38589531810eac117fc9f407bf8174c94f857741"),
"2023Q3":("research/detector-binance-oi-2022-2023-rest-quarters/v1/2023Q3/39311042453-1.json","b0c06c8dfaab2244954cd619bbaa73d7de54bd91ddab3c45748421dc1b6e955d"),
"2023Q4":("research/detector-binance-oi-2022-2023-rest-quarters/v1/2023Q4/39311042453-1.json","1afce2cd9b5855d84e19d6ad947620fb6e8b89872cf5383113d74420ab20c425")}
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
FULL=("FULL_SINGLE_VALID","FULL_EXACT_DOUBLE_VALID")
ROOT="research/detector-2022-2023-joint-3coin-oi-daily-mask/v1"
OUT=Path("detector_joint_3coin_oi_source_calendar")
START=dt.date(2022,1,1)
END=dt.date(2023,12,31)

def date_grid():
    dates=[]
    cursor=START
    while cursor<=END:
        dates.append(cursor.isoformat())
        cursor+=dt.timedelta(days=1)
    if len(dates)!=730 or len(set(dates))!=730:
        raise ValueError("SOURCE_DAY_GRID_NOT_730")
    return dates

def validate_row(row,expected_quarter):
    symbol=row.get("symbol")
    day=row.get("date_utc")
    if symbol not in SYMBOLS or not isinstance(day,str):
        raise ValueError("SOURCE_ROW_ID_UNEXPECTED")
    date=dt.date.fromisoformat(day)
    quarter=f"{date.year}Q{(date.month-1)//3+1}"
    if quarter!=expected_quarter:
        raise ValueError("SOURCE_ROW_WRONG_QUARTER")
    if row.get("publisher_checksum_status")!="PUBLISHER_SHA256_MATCH":
        raise ValueError("PINNED_SOURCE_PUBLISHER_SHA_CHANGED")
    status=row.get("calendar_quality")
    if status not in (*FULL,"PARTIAL_OR_SEMANTIC_ANOMALY","SOURCE_UNVERIFIED"):
        raise ValueError("PINNED_SOURCE_QUALITY_STATUS_UNKNOWN")
    if status in FULL and row.get("status")!="FULL_288_SOURCE_LABEL_SAMPLE":
        raise ValueError("FULL_SOURCE_GRADE_WITHOUT_288_EVIDENCE")
    return day,symbol

def reports_to_calendar(quarter_reports):
    if set(quarter_reports)!=set(PINS):
        raise ValueError("QUARTER_REPORTS_INCOMPLETE")
    observations={}
    for quarter,doc in quarter_reports.items():
        if doc.get("quarter")!=quarter:
            raise ValueError("QUARTER_REPORT_ID_MISMATCH")
        expected=("detector-binance-usdm-pre2024-oi-quarter-calendar-v1"
                  if quarter.endswith("Q1") else
                  "detector-binance-oi-2022-2023-rest-quarter-daily-sources-v1")
        if doc.get("schema")!=expected:
            raise ValueError("UNEXPECTED_QUARTER_SCHEMA")
        source=(doc.get("records") if quarter.endswith("Q1")
                else doc.get("original_source_provenance"))
        if not isinstance(source,list):
            raise ValueError("ORIGINAL_SOURCE_DAILY_EVIDENCE_MISSING")
        for row in source:
            day,symbol=validate_row(row,quarter)
            key=(day,symbol)
            if key in observations:
                raise ValueError("REPEATED_SOURCE_DAY_RECORD")
            observations[key]=row
    expected={(day,sym) for day in date_grid() for sym in SYMBOLS}
    if set(observations)!=expected:
        raise ValueError("INCOMPLETE_2022_2023_THREE_COIN_CALENDAR")
    return observations

def full_runs(date_map):
    runs=[];current=None
    for day in date_grid():
        if date_map[day]["three_coin_full_source_day"]:
            if current is None:current=[day,day,1]
            else:current[1]=day;current[2]+=1
        elif current is not None:
            runs.append({"start":current[0],"end":current[1],"calendar_days":current[2]})
            current=None
    if current is not None:
        runs.append({"start":current[0],"end":current[1],"calendar_days":current[2]})
    return sorted(runs,key=lambda x:(-x["calendar_days"],x["start"]))

def derive(checked):
    if len(checked)!=2190:
        raise ValueError("WRONG_SOURCE_ASSET_DAY_COUNT")
    days={}
    full_asset=partial_asset=invalid=missing=joint=0
    by_asset={s:{"source_clean_days":0,"partial_days":0} for s in SYMBOLS}
    for day in date_grid():
        bad=[];quality={}
        for symbol in SYMBOLS:
            source=checked[(day,symbol)]
            q=source.get("quality",{})
            is_full=source["calendar_quality"] in FULL
            if is_full:full_asset+=1;by_asset[symbol]["source_clean_days"]+=1
            else:partial_asset+=1;by_asset[symbol]["partial_days"]+=1
            inv=int(q.get("invalid_or_missing_values",0))
            gap=int(q.get("missing_5m_labels",0))
            invalid+=inv;missing+=gap
            quality[symbol]={"status":source["calendar_quality"],
                "full_288_labels_and_numeric":is_full,
                "invalid_oi_numeric":inv,"missing_5m_labels":gap,
                "exact_original_duplicate_labels":int(q.get("duplicate_label_count",0))}
            if not is_full:bad.append(symbol)
        good=not bad
        if good:joint+=1
        days[day]={"day":day,"three_coin_full_source_day":good,
            "excluded_symbols":bad,"per_symbol":quality,
            "raw_source_available_not_release_pit":True}
    if full_asset+partial_asset!=2190 or sum(v["source_clean_days"] for v in by_asset.values())!=full_asset:
        raise ValueError("AGGREGATE_ASSET_DAY_ACCOUNTING_FAILED")
    return {"calendar_days":730,"total_asset_days":2190,
       "source_complete_asset_days":full_asset,"partial_asset_days":partial_asset,
       "three_coin_joint_full_days":joint,"three_coin_excluded_days":730-joint,
       "invalid_native_oi_values":invalid,"missing_5m_source_labels":missing,
       "per_coin":by_asset,
       "three_coin_full_source_runs_longest_first":full_runs(days),
       "daily_source_quality_mask":[days[d] for d in date_grid()],
       "joint_quality_rule":"All three have exact 288 valid original UTC 5m labels and numeric native OI; any incomplete asset rejects ENTIRE joint day.",
       "original_exchange_release_timestamp":"UNVERIFIED",
       "h1h10_confirmatory_trading_gate":"DENIED_SOURCE_QUALITY_NOT_PIT"}

def main():
    OUT.mkdir(exist_ok=True)
    cli=r2();bucket=os.environ["R2_BUCKET"]
    loaded={}
    for quarter,(key,sha) in PINS.items():
        blob=verify_r2(cli,bucket,key,sha,5_000_000)
        loaded[quarter]=json.loads(blob)
        print("JOINT_CALENDAR_PINNED_SOURCE",json.dumps({"quarter":quarter,
            "manifest_sha256":sha,"source_verified":True}),flush=True)
    grid=reports_to_calendar(loaded)
    evidence=derive(grid)
    if (evidence["source_complete_asset_days"]!=2159 or
        evidence["partial_asset_days"]!=31 or
        evidence["invalid_native_oi_values"]!=401 or
        evidence["missing_5m_source_labels"]!=26):
        raise ValueError("FROZEN_SOURCE_TOTAL_MISMATCH")
    report={"schema":"detector-h1h10-2022-2023-three-coin-joint-source-day-mask-v1",
        "source_manifest_sha256_pins":PINS,
        "source_report_only_no_new_price_or_oi_requests":True,
        "research_only":True,"edge_status":"EDGE_UNVALIDATED",
        "trading_portfolio_changes":False,
        "asof_exchange_original_publication":"UNVERIFIED",
        "causal_condition":"NOT_CERTIFIED",
        **evidence,"run_id":os.environ["GITHUB_RUN_ID"]}
    blob=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2).encode()
    digest=hashlib.sha256(blob).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    cli.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",Metadata={"sha256":digest})
    if verify_r2(cli,bucket,key,digest,len(blob)+1)!=blob:
        raise ValueError("R2_JOINT_REPORT_READBACK_FAILED")
    (OUT/"report.json").write_bytes(blob)
    print("H1H10_JOINT_CLEAN_2022_2023_SUMMARY",json.dumps({
        "days":evidence["calendar_days"],
        "clean_asset_days":evidence["source_complete_asset_days"],
        "joint_clean_calendar_days":evidence["three_coin_joint_full_days"],
        "joint_excluded_days":evidence["three_coin_excluded_days"],
        "top_three_runs":evidence["three_coin_full_source_runs_longest_first"][:3],
        "r2_key":key,"sha256":digest,"edge":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
if __name__=="__main__":
    main()
