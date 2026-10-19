#!/usr/bin/env python3
"""Compare exact duplicate native OI values in Binance 2020-09-01 BTC archive.

Does not deduplicate, edit original rows, interpolate, infer PIT or signal.
"""
import collections
import csv
from decimal import Decimal,InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
from research.detector_btc_early_oi_forensic_v1 import URL
from research.detector_earliest_archive_byte_audit_v1 import (
    get_limited,extract_zip,publisher_hash,r2,verify_r2)

OUT=Path("detector_btc_2020_oi_duplicate_value_audit")
ROOT="research/detector-btc-early-oi-duplicate-values/v1"

def audit(data):
    reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if not set(("create_time","sum_open_interest")).issubset(reader.fieldnames or []):
        raise ValueError("EXPECTED_FIELDS_MISSING")
    groups=collections.defaultdict(list)
    count=0
    for row in reader:
        count+=1
        value=row["sum_open_interest"]
        try:
            native=Decimal(value)
            if not native.is_finite() or native<=0:
                raise InvalidOperation()
        except (InvalidOperation,ValueError):
            raise ValueError("BAD_OI_NATIVE_VALUE")
        groups[row["create_time"]].append((native,row))
    sizes=collections.Counter(len(v) for v in groups.values())
    equal_oi=equal_whole=0;conflicts=[]; differing_other=[]
    for time, observations in sorted(groups.items()):
        if len(observations)!=2:
            continue
        (left,leftrow),(right,rightrow)=observations
        if left==right: equal_oi+=1
        elif len(conflicts)<10: conflicts.append({"label":time,"values":[str(left),str(right)]})
        if leftrow==rightrow: equal_whole+=1
        elif left==right and len(differing_other)<10:
            differing_other.append({"label":time,
                "differing_fields":[key for key in leftrow if leftrow.get(key)!=rightrow.get(key)]})
    return {"raw_rows":count,"unique_source_labels":len(groups),
        "group_size_histogram":dict(sizes),
        "pairs_same_native_oi":equal_oi,
        "pairs_same_complete_csv_row":equal_whole,
        "conflicting_native_oi_example":conflicts,
        "non_oi_field_discrepancy_examples":differing_other,
        "all_labels_exactly_twice":bool(groups) and set(sizes)=={2},
        "no_original_rows_modified":True}

def main():
    OUT.mkdir(exist_ok=True)
    blob=get_limited(URL,4_000_000)
    inner,member=extract_zip(blob)
    sha=hashlib.sha256(blob).hexdigest()
    publisher=publisher_hash(URL,sha)
    if publisher["status"]!="PUBLISHER_SHA256_MATCH":
        raise ValueError("NOT_SOURCE_PUBLISHER_HASH_VERIFIED")
    details=audit(inner)
    if details["all_labels_exactly_twice"] and details["pairs_same_native_oi"]==details["unique_source_labels"]:
        status="DUPLICATE_OI_NUMERIC_VALUES_MATCH"
    else:
        status="DUPLICATE_VALUES_PARTIAL_OR_CONFLICTING"
    report={"schema":"detector-btc-2020-09-01-oi-duplicate-value-forensic-v1",
            "source_url":URL,"archive_sha256":sha,
            "source_csv_sha256":hashlib.sha256(inner).hexdigest(),"source_member":member,
            "publisher_checksum_status":publisher["status"],"archive_crc":"PASS",
            "duplicate_value_status":status,"details":details,
            "research_only":True,"original_exchange_publication":"UNVERIFIED",
            "source_oi_units":"BINANCE_NATIVE_NOT_INDEPENDENTLY_CONFIRMED",
            "safe_use":"DESCRIPTIVE_ONLY_WITH_PROVENANCE; NEVER_RAW_ROWCOUNT_AS_INDEPENDENT_BARS",
            "trade_actions":False,"run_id":os.environ.get("GITHUB_RUN_ID")}
    content=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2).encode()
    digest=hashlib.sha256(content).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    client=r2(); bucket=os.environ["R2_BUCKET"]
    client.put_object(Bucket=bucket,Key=key,Body=content,ContentType="application/json",Metadata={"sha256":digest})
    if verify_r2(client,bucket,key,digest,len(content)+1)!=content:
        raise ValueError("R2_BYTE_MISMATCH")
    (OUT/"report.json").write_bytes(content)
    print("BTC_2020_OI_DUPLICATE_VALUE_SUMMARY",json.dumps({
        "status":status,"rows":details["raw_rows"],"unique":details["unique_source_labels"],
        "pair_distribution":details["group_size_histogram"],
        "same_oi":details["pairs_same_native_oi"],
        "same_complete_row":details["pairs_same_complete_csv_row"],
        "conflicts":details["conflicting_native_oi_example"],
        "other_field_changes":details["non_oi_field_discrepancy_examples"],
        "r2_key":key,"sha256":digest,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False))
if __name__=="__main__":
    main()
