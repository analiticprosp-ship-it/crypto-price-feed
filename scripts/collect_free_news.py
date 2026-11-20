#!/usr/bin/env python3
"""Research-only RSS/Atom ingestion. No production trading dependencies."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc

def now():
    return dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def tagname(tag):
    return tag.rsplit("}", 1)[-1].lower()

def children_text(node, name):
    for child in node:
        if tagname(child.tag) == name:
            return (child.text or "").strip()
    return ""

def parse_feed(raw):
    root = ET.fromstring(raw)
    result = []
    for node in root.iter():
        if tagname(node.tag) not in ("item", "entry"):
            continue
        link = children_text(node, "link")
        if not link:
            for child in node:
                if tagname(child.tag) == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        result.append({"title": children_text(node, "title"),
                       "original_url": link,
                       "published_raw": children_text(node, "pubdate") or children_text(node, "published") or children_text(node, "updated"),
                       "source_item_id": children_text(node, "guid") or children_text(node, "id") or link})
    return result

def collect(config, output, fetcher=None):
    output.mkdir(parents=True, exist_ok=True)
    fetcher = fetcher or urllib.request.urlopen
    started = now()
    records = []
    receipts = []
    for source in config["sources"]:
        if not source.get("enabled", False):
            continue
        observed = now()
        status = "OK"
        error = None
        payload_hash = None
        try:
            req = urllib.request.Request(source["url"], headers={"User-Agent": "CryptoPortfolioResearchNews/1.0 (public research; contact via GitHub)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
            with fetcher(req, timeout=15) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("feed exceeds 2 MB")
            payload_hash = digest(raw)
            items = parse_feed(raw)
            for item in items:
                if not item["title"] or not item["original_url"]:
                    continue
                key = digest((source["id"] + "|" + (item["source_item_id"] or item["original_url"])).encode())
                records.append({"schema_version":"1.0","source":source["id"],"category":source.get("category"),"dedupe_key":key,
                                **item,"first_seen_at_utc":observed,"collected_at_utc":now(),
                                "time_quality":"SOURCE_UNVERIFIED" if item["published_raw"] else "PUBLISHED_MISSING",
                                "research_only":True})
        except (urllib.error.URLError, ET.ParseError, ValueError, OSError) as exc:
            status = "UNAVAILABLE"
            error = type(exc).__name__ + ": " + str(exc)[:250]
            items = []
        receipts.append({"source":source["id"],"url":source["url"],"status":status,"error":error,
                         "payload_sha256":payload_hash,"items_parsed":len(items),"observed_at_utc":observed})
    run_id = started.replace(":", "").replace("-", "").replace(".", "")
    run = {"schema_version":"1.0","run_id":run_id,"fetch_started_at_utc":started,"fetch_completed_at_utc":now(),
           "status":"OK" if all(r["status"]=="OK" for r in receipts) else "PARTIAL" if any(r["status"]=="OK" for r in receipts) else "UNAVAILABLE",
           "sources":receipts,"record_count":len(records),"research_only":True}
    (output / "run.json").write_text(json.dumps(run,ensure_ascii=False,indent=2)+"\n")
    (output / "items.jsonl").write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in records))
    print(json.dumps({"status":run["status"],"record_count":len(records),"receipts":receipts}))
    return run

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources",default=str(ROOT / "research/free_news/sources.json"))
    parser.add_argument("--output",default=str(ROOT / "research/free_news/out"))
    args = parser.parse_args()
    result = collect(json.loads(Path(args.sources).read_text()),Path(args.output))
    sys.exit(0 if result["status"]=="OK" else 2)
