"""Network boundary tests use synthetic responses, never actual election prices."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from urllib.parse import parse_qs, urlsplit
from urllib.error import HTTPError

import collect_us_midterms_market as c
import us_midterms_windows as m


class Response(io.BytesIO):
    status = 200
    headers = {'Content-Type': 'application/json'}


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'raw').mkdir()
        (self.root / 'attempts').mkdir()
        self.start = int(m.utc('2026-11-03T23:05:00Z'))
        self.clock = lambda: self.start + 3600

    def get(self, opener, end=None):
        return c.acquire_page(self.root, 'BTC-USD', self.start, end or self.start + 900,
                              opener=opener, clock=self.clock, pause=lambda _: None)

    def test_paging_contiguous_and_under_limit(self):
        chunks = list(c.pages(self.start, self.start + 600 * 300))
        self.assertEqual([b-a for a,b in chunks], [299*300, 299*300, 2*300])
        self.assertEqual(chunks[0][1], chunks[1][0])

    def test_original_bytes_preserved_and_loadable(self):
        raw = ('[\n [' + str(self.start) + ', 90,120,100,110,2]\n]\n').encode()
        receipt, attempts = self.get(lambda *a, **kw: Response(raw))
        self.assertEqual((self.root / receipt['path']).read_bytes(), raw)
        self.assertEqual(attempts[-1]['eligible_candles'], 1)
        self.assertEqual(receipt['sha256'], c.hashlib.sha256(raw).hexdigest())

    def test_http_failure_receipt_then_success(self):
        calls = []
        raw = json.dumps([[self.start,90,120,100,110,2]]).encode()
        def opener(request, **kw):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise HTTPError(request.full_url, 429, 'rate limit', {}, io.BytesIO(b'limited'))
            return Response(raw)
        receipt, attempts = self.get(opener)
        self.assertIsNotNone(receipt)
        self.assertEqual([r['status'] for r in attempts], ['FAILED', 'VALIDATED'])
        self.assertEqual((self.root / attempts[0]['response_path']).read_bytes(), b'limited')

    def test_api_error_object_never_becomes_market(self):
        receipt, attempts = self.get(lambda *a, **kw: Response(b'{"message":"unavailable"}'))
        self.assertIsNone(receipt)
        self.assertEqual(len(attempts), 3)
        self.assertTrue(all(r['status'] == 'FAILED' for r in attempts))

    def test_empty_or_unclosed_only_not_accepted(self):
        raw = json.dumps([[self.start+3600,90,120,100,110,2]]).encode()
        receipt, attempts = self.get(lambda *a, **kw: Response(raw))
        self.assertIsNone(receipt)
        self.assertIn('no eligible', attempts[0]['error'])

    def test_partial_page_keeps_missing_bar_as_gap(self):
        raw = json.dumps([[self.start,90,120,100,110,2],
                          [self.start+600,90,120,100,110,2]]).encode()
        receipt, _ = self.get(lambda *a, **kw: Response(raw))
        manifest = self.root / 'market.json'
        c.write_json(manifest, {'receipts': [receipt]})
        market = m.load_market(manifest, self.clock())
        self.assertNotIn(self.start+300, market['BTC-USD'])

    def test_invalid_numeric_price_rejected(self):
        raw = json.dumps([[self.start,90,120,0,110,2]]).encode()
        receipt, _ = self.get(lambda *a, **kw: Response(raw))
        self.assertIsNone(receipt)

    def test_full_run_scores_both_assets_and_writes_replay_lock(self):
        cutoff = m.utc('2026-11-05T17:15:00Z')
        acquire = c.acquire_page
        def opener(request, **kw):
            q = parse_qs(urlsplit(request.full_url).query)
            left, right = (int(m.utc(q[k][0])) for k in ('start', 'end'))
            return Response(json.dumps([[t,90,120,100,110,2]
                for t in range(left, right, 300)]).encode())
        def fake_acquire(root, product, start, end):
            return acquire(root, product, start, end, opener=opener,
                           clock=lambda: cutoff, pause=lambda _: None)
        output = self.root / 'run'
        with patch.object(c, 'now', return_value=cutoff), patch.object(c, 'acquire_page', side_effect=fake_acquire), redirect_stdout(io.StringIO()):
            code = c.run(output, m.ROOT / 'us_midterms_2026_11_05_v2.json')
        self.assertEqual(code, 0)
        summary = json.loads((output / 'summary.json').read_bytes())
        self.assertEqual(summary['statuses'], {'PENDING_ANCHOR':72, 'OK':12, 'WINDOW_NOT_MATURED':18})
        self.assertEqual(summary['baseline_count'], 4)
        result = json.loads((output / 'results.json').read_bytes())
        lock = json.loads((output / 'baselines_001.json').read_bytes())
        m.check_baseline_lock(result['windows'], lock, cutoff)
        self.assertTrue((output / 'SHA256.json').exists())

    def test_failed_collection_preserves_nulls_and_returns_failure(self):
        cutoff = m.utc('2026-11-05T17:15:00Z')
        output = self.root / 'failed'
        with patch.object(c, 'now', return_value=cutoff), patch.object(c, 'acquire_page', return_value=(None, [dict(status='FAILED')])), redirect_stdout(io.StringIO()):
            code = c.run(output, m.ROOT / 'us_midterms_2026_11_05_v2.json')
        self.assertEqual(code, 2)
        rows = json.loads((output / 'results.json').read_bytes())['windows']
        self.assertTrue(all(r['metrics'] is None for r in rows))
        self.assertFalse((output / 'baselines_001.json').exists())

    def test_later_run_rejects_changed_previously_locked_candle(self):
        cutoff = m.utc('2026-11-06T11:55:00Z')
        acquire = c.acquire_page
        def opener(request, **kw):
            q = parse_qs(urlsplit(request.full_url).query)
            left, right = (int(m.utc(q[k][0])) for k in ('start', 'end'))
            return Response(json.dumps([[t,90,120,100,110,2]
                for t in range(left, right, 300)]).encode())
        def fake_acquire(root, product, start, end):
            return acquire(root, product, start, end, opener=opener,
                           clock=lambda: cutoff, pause=lambda _: None)
        # Construct an accepted synthetic lock and deliberately revise it.
        prior = self.root / 'prior-lock.json'
        with patch.object(c, 'now', return_value=cutoff), patch.object(c, 'acquire_page', side_effect=fake_acquire), redirect_stdout(io.StringIO()):
            self.assertEqual(c.run(self.root / 'first', m.ROOT / 'us_midterms_2026_11_05_v2.json'), 0)
            lock = json.loads((self.root / 'first' / 'baselines_001.json').read_bytes())
            next(iter(lock['entries'].values()))['baseline']['price'] = 101
            prior.write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError, 'baseline changed'):
                c.run(self.root / 'later', m.ROOT / 'us_midterms_2026_11_05_v2.json', prior)
        self.assertFalse((self.root / 'later' / 'results.json').exists())


if __name__ == '__main__':
    unittest.main()
