#!/usr/bin/env python3
"""Bounded 3-free-day expansion of already SHA-verified Tardis OI research pipeline.

Runs the existing audited parser and vendor-asof builder against THREE new
predeclared first-of-month dates, never mutating the canonical four-day archive.
Not a random sample or full 7-14 continuous days. No paid data or trading.
"""
from pathlib import Path
from research import detector_tardis_vendor_asof_multiday as vetted

NEW_DAYS=("2024-04-01","2025-07-01","2026-02-01")
ROOT="research/tardis-binance-oi-expansion/v1"
REPORT=Path("detector_tardis_expansion")

def configure():
    if (vetted.DAYS!=("2024-01-01","2025-01-01","2026-09-01")
        or vetted.ROOT!="research/tardis-binance-oi-multiday/v1"):
        raise ValueError("BASELINE_SOURCE_IMPLEMENTATION_CHANGED")
    if len(set(NEW_DAYS))!=3 or any(not x.endswith("-01") for x in NEW_DAYS):
        raise ValueError("PREDECLARED_SAMPLE_DAY_INVALID")
    vetted.DAYS=NEW_DAYS
    vetted.ROOT=ROOT
    vetted.OUT=REPORT
    vetted.OUT.mkdir(exist_ok=True)
    return (vetted.DAYS,vetted.ROOT)

def main():
    configure()
    vetted.main()

if __name__=="__main__":main()
