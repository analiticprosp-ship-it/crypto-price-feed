"""Synthetic fixtures only: these prices are never exported as election results."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import us_midterms_windows as m


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = json.loads((m.ROOT / 'us_midterms_2026_11_03_v1.json').read_bytes())
        self.event = copy.deepcopy(self.ledger['events'][4])
        self.t0 = m.utc('2026-11-03T23:00:00Z')

    def evidence(self, name='present.json', seen='2026-11-03T23:00:01Z'):
        raw = b'{"fixture":"synthetic-not-election-data"}'
        (self.root / name).write_bytes(raw)
        return dict(path=name, sha256=hashlib.sha256(raw).hexdigest(), observed_at_utc=seen,
                    capture_kind='ORIGINAL_SOURCE_RESPONSE', source_url='https://example.invalid/fixture',
                    source_item_id='synthetic', source_version='fixture-v1',
                    semantic_review='SYNTHETIC_TEST_ONLY', publication_proof_method='SYNTHETIC_TEST_ONLY')

    def exact(self, seen='2026-11-03T23:00:01Z'):
        self.event.update(timing_status='EXACT_SOURCE_AVAILABLE',
                          first_market_available_timestamp_utc='2026-11-03T23:00:00Z',
                          availability_evidence=self.evidence(seen=seen))
        return self.event

    def bounded(self, lo='2026-11-03T23:00:01Z', hi='2026-11-03T23:01:00Z'):
        self.event.update(timing_status='BOUNDED_SOURCE_AVAILABLE', availability_lower_utc=lo,
                          availability_upper_utc=hi, availability_evidence=self.evidence(seen=hi))
        self.event['availability_evidence']['last_absent'] = self.evidence('absent.json', lo)
        return self.event

    def rows(self, event=None, cutoff='2026-11-04T23:10:00Z', market=None):
        ledger = dict(self.ledger, events=[event or self.event])
        return list(m.windows(ledger, m.utc(cutoff), market, self.root))

    def bars(self, start=None, count=3):
        start = int(self.t0 + 300 if start is None else start)
        bars = {start + i * 300: [start + i * 300, 90, 120, 100, 110, 2] for i in range(count)}
        return {p: copy.deepcopy(bars) for p in m.PRODUCTS}

    def post(self, rows, product='BTC-USD', horizon='15m'):
        return next(r for r in rows if r['window'] == horizon and r['product'] == product)

    def manifest(self, bars, received='2026-11-03T23:20:00Z', product='BTC-USD'):
        raw = json.dumps(bars).encode()
        (self.root / 'market.json').write_bytes(raw)
        receipt = dict(product_id=product, path='market.json', sha256=hashlib.sha256(raw).hexdigest(),
                       retrieved_at_utc=received,
                       request_url=f'https://api.exchange.coinbase.com/products/{product}/candles?granularity=300&start=2026-11-03T23:05:00Z&end=2026-11-03T23:20:00Z')
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(dict(receipts=[receipt])))
        return path

    def test_original_asof_regression(self):
        rows = list(m.windows(self.ledger, m.utc(self.ledger['audit_as_of_utc'])))
        self.assertEqual(Counter(r['status'] for r in rows), {'PENDING_ANCHOR': 72, 'WINDOW_NOT_MATURED': 16})
        self.assertTrue(all(r['metrics'] is None for r in rows))

    def test_later_calendar_maturity_without_market(self):
        rows = list(m.windows(self.ledger, m.utc('2026-11-05T16:52:10Z')))
        self.assertEqual(Counter(r['status'] for r in rows), {'PENDING_ANCHOR': 72, 'PENDING_MARKET_DATA': 10, 'WINDOW_NOT_MATURED': 6})

    def test_exact_boundary_excluded(self):
        row = self.post(self.rows(self.exact()))
        self.assertEqual(row['start_utc'], '2026-11-03T23:05:00Z')
        self.assertEqual(row['end_utc'], '2026-11-03T23:20:00Z')

    def test_inside_bucket_alignment(self):
        event = self.exact(seen='2026-11-03T23:04:59Z')
        event['first_market_available_timestamp_utc'] = '2026-11-03T23:04:58Z'
        self.assertEqual(self.post(self.rows(event))['start_utc'], '2026-11-03T23:05:00Z')

    def test_closed_horizon_correct_formula_both_assets(self):
        rows = self.rows(self.exact(), cutoff='2026-11-03T23:20:00Z', market=self.bars())
        for product in m.PRODUCTS:
            row = self.post(rows, product)
            self.assertEqual(row['status'], 'OK')
            self.assertAlmostEqual(row['metrics']['return'], .10)
            self.assertAlmostEqual(row['metrics']['mae_from_open'], -.10)
            self.assertAlmostEqual(row['metrics']['mfe_from_open'], .20)
            self.assertEqual(row['metrics']['base_volume'], 6)

    def test_not_matured_never_zero_or_interim(self):
        row = self.post(self.rows(self.exact(), cutoff='2026-11-03T23:19:59Z', market=self.bars()))
        self.assertEqual(row['status'], 'WINDOW_NOT_MATURED')
        self.assertIsNone(row['metrics'])
        self.assertEqual(row['baseline']['price'], 100)

    def test_missing_first_bar_does_not_shift_baseline(self):
        market = self.bars()
        del market['BTC-USD'][int(self.t0 + 300)]
        row = self.post(self.rows(self.exact(), market=market))
        self.assertEqual(row['status'], 'DATA_GAP')
        self.assertIsNone(row['baseline'])
        self.assertEqual(row['start_utc'], '2026-11-03T23:05:00Z')
        self.assertIsNone(row['metrics'])

    def test_missing_middle_bar(self):
        market = self.bars()
        del market['BTC-USD'][int(self.t0 + 600)]
        row = self.post(self.rows(self.exact(), market=market))
        self.assertEqual(row['missing_bars'], 1)
        self.assertIsNone(row['metrics'])

    def test_no_market_vs_gap(self):
        self.assertEqual(self.post(self.rows(self.exact()))['status'], 'PENDING_MARKET_DATA')

    def test_true_zero_return_is_allowed_only_complete(self):
        market = self.bars()
        for p in m.PRODUCTS:
            for bar in market[p].values():
                bar[4] = 100
        row = self.post(self.rows(self.exact(), market=market))
        self.assertEqual((row['status'], row['metrics']['return']), ('OK', 0))

    def test_bounded_uses_upper_bound(self):
        row = self.post(self.rows(self.bounded()))
        self.assertEqual(row['anchor_upper_utc'], '2026-11-03T23:01:00Z')
        self.assertEqual(row['start_utc'], '2026-11-03T23:05:00Z')

    def test_wide_bracket_pending(self):
        rows = self.rows(self.bounded(hi='2026-11-03T23:04:00Z'))
        self.assertTrue(all(r['status'] == 'PENDING_ANCHOR' for r in rows))

    def test_cross_bucket_pending(self):
        rows = self.rows(self.bounded(lo='2026-11-03T22:59:59Z'))
        self.assertTrue(all(r['status'] == 'PENDING_ANCHOR' for r in rows))

    def test_receipt_after_cutoff_pending(self):
        rows = self.rows(self.exact(seen='2026-11-05T00:00:00Z'))
        self.assertTrue(all(r['status'] == 'PENDING_ANCHOR' for r in rows))

    def test_delayed_reconstruction_is_descriptive(self):
        rows = self.rows(self.exact(seen='2026-11-04T20:00:00Z'))
        self.assertTrue(all(r['study_class'] == 'DESCRIPTIVE' for r in rows))

    def test_extract_cannot_be_result_anchor(self):
        self.exact()['availability_evidence']['capture_kind'] = 'RETRIEVAL_EXTRACT_NOT_ORIGINAL_HTTP'
        with self.assertRaisesRegex(ValueError, 'original source'):
            self.rows()

    def test_semantic_review_required(self):
        del self.exact()['availability_evidence']['semantic_review']
        with self.assertRaisesRegex(ValueError, 'reviewed publication'):
            self.rows()

    def test_hash_tamper_rejected(self):
        self.exact()
        (self.root / 'present.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.rows()

    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            m.verified_bytes(self.root, '../outside', 'a' * 64)

    def test_ambiguous_timestamp_rejected(self):
        for value in ['2026-11-03T23:00Z', '2026-11-03T23:00:00+01:00Z', '2026-11-03T23:00:00', '2026-11-03']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.utc(value)

    def test_calendar_metadata_not_scored(self):
        self.assertEqual(self.rows(self.ledger['events'][0]), [])

    def test_market_excludes_future_receipts(self):
        path = self.manifest(list(self.bars()['BTC-USD'].values()), received='2026-11-03T23:21:00Z')
        self.assertEqual(m.load_market(path, self.t0 + 1200)['BTC-USD'], {})

    def test_market_excludes_unclosed_bars_at_receipt(self):
        path = self.manifest(list(self.bars()['BTC-USD'].values()), received='2026-11-03T23:19:59Z')
        self.assertEqual(len(m.load_market(path, self.t0 + 1200)['BTC-USD']), 2)

    def test_conflicting_duplicate_rejected(self):
        bars = list(self.bars()['BTC-USD'].values())
        extra = copy.deepcopy(bars[0]); extra[4] = 111
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            m.load_market(self.manifest(bars + [extra]), self.t0 + 1200)

    def test_invalid_candle_rejected(self):
        bars = list(self.bars()['BTC-USD'].values()); bars[0][3] = 0
        with self.assertRaisesRegex(ValueError, 'invalid candle'):
            m.load_market(self.manifest(bars), self.t0 + 1200)

    def test_wrong_venue_rejected(self):
        path = self.manifest(list(self.bars()['BTC-USD'].values()))
        path.write_text(path.read_text().replace('api.exchange.coinbase.com', 'other.invalid'))
        with self.assertRaisesRegex(ValueError, 'unexpected venue'):
            m.load_market(path, self.t0 + 1200)

    def test_baseline_pinned_across_horizons_and_revisions(self):
        rows = self.rows(self.exact(), market=self.bars())
        entries = m.baseline_entries(rows)
        self.assertEqual(len(entries), 2)
        lock = dict(frozen_as_of_utc='2026-11-04T23:10:00Z', entries=entries)
        m.check_baseline_lock(rows, lock, self.t0 + 2 * 86400)
        revised = copy.deepcopy(rows)
        for r in revised:
            if r['baseline']:
                r['baseline']['price'] = 101
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            m.check_baseline_lock(revised, lock, self.t0 + 2 * 86400)

    def test_observation_is_separate_from_pending_result(self):
        ledger = json.loads((m.ROOT / 'us_midterms_2026_11_05_v2.json').read_bytes())
        rows = list(m.windows(ledger, m.utc(ledger['audit_as_of_utc']), news_dir=m.ROOT))
        self.assertEqual(Counter(r['status'] for r in rows), {'PENDING_ANCHOR': 72, 'PENDING_MARKET_DATA': 10, 'WINDOW_NOT_MATURED': 20})
        obs = [r for r in rows if r['role'] == 'observation_control']
        self.assertEqual(len(obs), 14)
        self.assertTrue(all(r['start_utc'] == '2026-11-05T16:55:00Z' for r in obs))
        self.assertTrue(all(r['estimand'] == 'AFTER_OBSERVATION_MONITORING' for r in obs))

    def test_baseline_lock_never_overwritten(self):
        ledger = dict(self.ledger, events=[self.ledger['events'][1]])
        ledger_path = self.root / 'ledger.json'; ledger_path.write_text(json.dumps(ledger))
        bars = list(self.bars()['BTC-USD'].values())
        manifest = self.manifest(bars)
        lock = self.root / 'lock.json'
        command = [sys.executable, str(m.ROOT / 'us_midterms_windows.py'), '--ledger', str(ledger_path),
                   '--as-of', '2026-11-03T23:20:00Z', '--market-manifest', str(manifest),
                   '--write-baseline-lock', str(lock)]
        subprocess.run(command, check=True, capture_output=True)
        original = lock.read_bytes()
        repeated = subprocess.run(command, capture_output=True)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertEqual(lock.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
