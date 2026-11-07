#!/usr/bin/env python3
"""Acquire original Coinbase responses and score the frozen election ledger.

Research only. All outputs are exclusive-created in a new run directory.
No source substitutions, credentials, trades, zero-fills or ledger edits.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import us_midterms_windows as m


def now():
    return datetime.now(timezone.utc).timestamp()


def write_json(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def pages(start, end):
    if start % m.STEP or end % m.STEP or end < start:
        raise ValueError('invalid aligned request range')
    while start < end:
        stop = min(start + 299 * m.STEP, end)
        yield start, stop
        start = stop


def acquire_page(root, product, start, end, opener=urlopen, clock=now, pause=time.sleep):
    url = f'https://{m.API}/products/{product}/candles?' + urlencode(dict(
        granularity=m.STEP, start=m.iso(start), end=m.iso(end)))
    attempts = []
    for number in range(1, 4):
        stem = f'{product}_{start}_{end}_attempt{number}'
        record = dict(product_id=product, request_url=url, attempt=number,
                      request_started_at_utc=m.iso(clock()))
        raw = None
        headers = {}
        try:
            request = Request(url, headers={'Accept': 'application/json',
                              'Accept-Encoding': 'identity',
                              'User-Agent': 'crypto-price-feed-election-research/1.0'})
            with opener(request, timeout=25) as response:
                record['http_status'] = response.status
                headers = dict(response.headers.items())
                raw = response.read()
            record['retrieved_at_utc'] = m.iso(clock())
            if record['http_status'] != 200:
                raise ValueError('non-200 response')
            values = json.loads(raw)
            if not isinstance(values, list):
                raise ValueError('expected original Coinbase array')
            raw_path = root / 'raw' / (stem + '.json')
            raw_path.write_bytes(raw)
            receipt = dict(product_id=product, path=raw_path.relative_to(root).as_posix(),
                           sha256=hashlib.sha256(raw).hexdigest(), request_url=url,
                           retrieved_at_utc=record['retrieved_at_utc'])
            # Use a root-level manifest to retain the calculator's path confinement.
            check_path = root / (stem + '_validation.json')
            write_json(check_path, {'receipts': [receipt]})
            eligible = m.load_market(check_path, m.utc(record['retrieved_at_utc']))[product]
            if not eligible:
                raise ValueError('no eligible closed candles returned for requested range')
            record.update(status='VALIDATED', eligible_candles=len(eligible),
                          response_path=receipt['path'], sha256=receipt['sha256'])
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, KeyError) as error:
            if isinstance(error, HTTPError):
                record['http_status'] = error.code
                headers = dict(error.headers.items()) if error.headers else {}
                raw = error.read()
            record.setdefault('retrieved_at_utc', m.iso(clock()))
            record.update(status='FAILED', error=str(error))
        if raw is not None and 'response_path' not in record:
            failed_path = root / 'raw' / (stem + '_failed.bin')
            failed_path.write_bytes(raw)
            record.update(response_path=failed_path.relative_to(root).as_posix(),
                          sha256=hashlib.sha256(raw).hexdigest())
        record['response_headers'] = headers
        write_json(root / 'attempts' / (stem + '.json'), record)
        attempts.append(record)
        if record['status'] == 'VALIDATED':
            return receipt, attempts
        if number < 3:
            pause(number)
    return None, attempts


def run(output, ledger_path, prior_lock=None):
    output.mkdir(parents=True, exist_ok=False)
    (output / 'raw').mkdir()
    (output / 'attempts').mkdir()
    ledger = json.loads(ledger_path.read_bytes())
    started = now()
    planned = list(m.windows(ledger, started, news_dir=ledger_path.parent))
    fixed = [r for r in planned if r['start_utc'] is not None]
    start = int(min(m.utc(r['start_utc']) for r in fixed))
    end = min(int(started // m.STEP) * m.STEP,
              int(max(m.utc(r['end_utc']) for r in fixed)))
    write_json(output / 'collection_plan.json', dict(
        started_at_utc=m.iso(started), start_utc=m.iso(start), end_utc=m.iso(end),
        products=m.PRODUCTS, granularity_seconds=m.STEP,
        ledger_sha256=hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        source_revision='CURRENT_HISTORY_RETRIEVED_NOW_NOT_ORIGINAL_PIT',
        github_run_id=__import__('os').environ.get('GITHUB_RUN_ID'),
        github_sha=__import__('os').environ.get('GITHUB_SHA')))
    receipts, failed_pages = [], []
    for product in m.PRODUCTS:
        for left, right in pages(start, end):
            receipt, attempts = acquire_page(output, product, left, right)
            if receipt:
                receipts.append(receipt)
            else:
                failed_pages.append(dict(product_id=product, start_utc=m.iso(left),
                                         end_utc=m.iso(right), attempts=len(attempts)))
    manifest = output / 'market.json'
    write_json(manifest, dict(receipts=receipts))
    cutoff = now()
    market = m.load_market(manifest, cutoff)
    rows = list(m.windows(ledger, cutoff, market, ledger_path.parent))
    if prior_lock:
        m.check_baseline_lock(rows, json.loads(prior_lock.read_bytes()), cutoff)
    entries = m.baseline_entries(rows)
    lock_hash = None
    if entries:
        lock_path = output / 'baselines_001.json'
        write_json(lock_path, dict(frozen_as_of_utc=m.iso(cutoff), entries=entries,
            ledger_sha256=hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            market_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
            parent_lock_sha256=(hashlib.sha256(prior_lock.read_bytes()).hexdigest() if prior_lock else None)))
        lock_hash = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    report = dict(as_of_utc=m.iso(cutoff), windows=rows,
        event_audit=m.event_audit(ledger, cutoff, ledger_path.parent),
        market_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        ledger_sha256=hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        calculator_sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
        collector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        baseline_lock_sha256=lock_hash)
    write_json(output / 'results.json', report)
    summary = dict(as_of_utc=m.iso(cutoff), statuses=dict(Counter(r['status'] for r in rows)),
        received_pages=len(receipts), failed_pages=failed_pages,
        candles={p: len(market[p]) for p in m.PRODUCTS}, baseline_count=len(entries),
        complete_windows=[{k: r[k] for k in ('event_id', 'product', 'window', 'start_utc', 'end_utc', 'metrics')}
                          for r in rows if r['status'] == 'OK'],
        baselines=entries,
        classification='DESCRIPTIVE_CURRENT_HISTORY_NOT_ORIGINAL_PIT')
    write_json(output / 'summary.json', summary)
    inventory = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(output.rglob('*')) if p.is_file()}
    write_json(output / 'SHA256.json', inventory)
    print(json.dumps(summary, indent=2, allow_nan=False))
    # A partial result is retained and explicitly fails collection acceptance.
    mature = [r for r in rows if r['status'] not in ('PENDING_ANCHOR', 'WINDOW_NOT_MATURED')]
    return 0 if not failed_pages and all(r['status'] == 'OK' for r in mature) and entries else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--ledger', type=Path, default=m.ROOT / 'us_midterms_2026_11_05_v2.json')
    parser.add_argument('--baseline-lock', type=Path)
    args = parser.parse_args()
    return run(args.output, args.ledger, args.baseline_lock)


if __name__ == '__main__':
    sys.exit(main())
