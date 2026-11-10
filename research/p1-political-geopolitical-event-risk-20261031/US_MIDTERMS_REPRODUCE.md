# US midterms: reproducible clock and incomplete-data rules (v2)

Scope: draft PR #157 / issue #156, research only. The v1 ledger is retained byte-for-byte. v2 adds one separately labelled observation checkpoint, not a replacement election result. Source selection, assets, venue, candle grid and result horizons remain those in v1. The original 3 November audit is reproducible without market or news inputs.

## Clock inventory

All event IDs have prefix `P1-POL-2026-11-03-US-MIDTERMS`.

| Event ID suffix | Timing confirmed in ledger | Result clock / treatment | Original outcome rows |
|---|---|---|---:|
| (no suffix) | Election local date, 3 November | Metadata; no UTC result instant | 0 |
| `-FIRST-CLOSE` | 3 Nov 23:00 UTC | Scheduled calendar comparison only | 16 |
| `-NYC-CLOSE` | 4 Nov 02:00 UTC | Metadata only | 0 |
| `-CA-REPORT-START` | 4 Nov 04:00 UTC | Scheduled reporting metadata; actual first report unknown | 0 |
| `-IN05-FIRST-TALLY` | No first positive release receipt | `PENDING_ANCHOR` | 10 |
| `-KY06-FIRST-TALLY` | Current positive tally now observed; first release unknown | `PENDING_ANCHOR` | 10 |
| `-IN05-AP-CALL` | No qualifying original timed call receipt in this branch | `PENDING_ANCHOR` | 10 |
| `-KY06-AP-CALL` | No qualifying original timed call receipt in this branch | `PENDING_ANCHOR` | 10 |
| `-AP-HOUSE-CONTROL` | AP outcome coverage exists; first call receipt missing | `PENDING_ANCHOR` | 16 |
| `-AP-SENATE-CONTROL` | AP outcome coverage exists; first call receipt missing | `PENDING_ANCHOR` | 16 |
| `-CA-CERTIFICATION` | 11 December scheduled local date only | `PENDING_CERTIFICATION`; metadata | 0 |

The 72 pending rows are six result events × two assets × their windows, including pre-24h. They are not 72 independent results. The 16 calendar rows are one schedule × two assets × eight windows. At the v1 cutoff all 16 were unclosed. At **2026-11-05T16:52:10Z**, ten are mature but lack verified market data; six remain unclosed. Passage of time changes maturity, never creates market observations.

The new KY-06 receipt records positive totals on the official 2026 page (Dembo 138777; Alvarado 114030, unofficial). Its displayed update has no verified offset and is not the first tally timestamp. AP's elections hub and chamber outcome coverage were also inspected, but no original versioned first-distribution receipt was obtained. Indiana's rendered page remained a template. These checks establish neither that a call is absent nor when it first became public. The saved KY receipt is a small structured retrieval extract, explicitly **not original HTTP bytes**, and cannot satisfy a result anchor.

## A useful first point without inventing publication time

`-OBSERVED-KY06-20261105` is the first hash-backed observation receipt added in this branch. Collection started at 16:52:07 UTC and completed at **16:52:10 UTC on 5 November** (17:52:10 in Alicante). This is a conservative collection clock; browser cache/source latency is unknown. It is not evidence that results first became public then. The older 3 November audit timestamp is retained; it is not silently promoted to a raw source receipt or a market quote.

For this separate monitoring series the frozen start is **5 November 16:55 UTC**, the first grid boundary strictly after the observation. There are 14 post-observation rows (two assets × seven horizons), no pre-result P1 baseline and no claim to measure the original election reaction. The horizons are 15m, 1h, 4h, 1d, 7d, 30d, 90d, unchanged from the long-window selection. If later evidence establishes an earlier true result publication, append a versioned result anchor in its own series; never move this monitoring checkpoint. Later daily observations do not reset it.

All current outputs are conservatively `DESCRIPTIVE`. A local hash and an audit date alone cannot prove pre-result registration. Upgrading a result study to prospective requires separately reviewed contemporaneous capture, pre-result publication of rules and receipt provenance. Newly inspected outcomes or later reconstructions must not be relabelled prospective.

## Return calculation and fixed baseline

Use only Coinbase Exchange spot `BTC-USD` and `ETH-USD`, native 300-second candles. Do not substitute Binance, USDT, a ticker quote or another feed when Coinbase is unavailable. Preserve original JSON response bytes, request URL, retrieval completion UTC and SHA-256 in a market manifest. Coinbase documents gaps when no ticks exist; they remain gaps.

For an exact accepted publication, `lo=hi=t0`; for an accepted bracket use `(lo,hi]`. The bracket must be ≤120 seconds within one 5-minute bucket. A wider or cross-bucket bracket leaves `PENDING_ANCHOR`; both-bound sensitivity is separate. A result anchor requires original response bytes plus `capture_kind=ORIGINAL_SOURCE_RESPONSE`, `source_url`, `source_item_id`, `source_version`, `semantic_review`, `publication_proof_method`, `path`, `sha256`, `observed_at_utc`. Those review fields are researcher attestations: hashes validate integrity, not the truth of a call. The absent receipt for a bracket also needs its own path, hash and time; the researcher must verify same feed/version/election semantics. Reject contradictory exact-plus-interval clocks. A receipt after the audit cutoff is unavailable to that run.

Pre-24h ends at `floor5m(lo)`. Each post horizon starts at `s=(floor(hi/300)+1)*300`, even for a release exactly on a boundary. The excluded release bucket is not reintroduced later. All intervals are half-open `[s,s+H)`.

For each asset separately:

`return(H) = close of candle starting at (s+H-300) / open of candle starting at s - 1`

Returns are fractions (0.01 = 1%). The same first candle/open is used for every post horizon. `timestamp_utc` in the exported baseline is the candle bucket start; the exact first-trade timestamp is not supplied by this endpoint. It is not a tick quote or assumed trade fill. A missing first candle never moves `s` to the next available candle. BTC and ETH have the same selected clock, but their data completeness is reported independently.

The baseline is visible as soon as its first candle is fully closed and hash-verified, even while a longer horizon remains unclosed. **Its horizon metrics stay null.** Create a baseline lock at the first run with verified initial candles. The lock pins event, product, selected clock, receipt hash, start, open and canonical candle hash, and records the ledger and market manifest hashes. Files are created exclusively and cannot be overwritten. Every subsequent scoring command must pass the existing `--baseline-lock`; changed/missing locked candles or clock changes fail loudly. When adding newly verified baselines, pass both the old lock and a new `--write-baseline-lock` path; archive both and their receipts. Keep run outputs as immutable snapshots. The CLI cannot prevent a researcher from discarding a lock or editing repository history; review the linked lock chain and Git receipts.

| Status | Meaning | Metrics |
|---|---|---|
| `PENDING_ANCHOR` | Result availability not established/usable by cutoff | null |
| `WINDOW_NOT_MATURED` | Selected window ends after cutoff | null |
| `PENDING_MARKET_DATA` | Mature window, no eligible product data | null |
| `DATA_GAP` | Eligible series exists but required candle(s) missing | null |
| `OK` | Every required bar closed by both cutoff and receipt completion | Calculated |

Never use partial horizons, carry forward prices, fill gaps, use a later candle as the start or enter zero for a missing result. A genuine zero return is valid only for an `OK` complete window. News/candle hash failures and conflicting duplicate bars are input errors; they do not become successful rows. Baseline prices are price levels, not zero-return placeholders.

## Replay and verification

From this directory, Python 3.10+, standard library only:

```sh
python3 -m unittest -v test_us_midterms_windows.py
python3 us_midterms_windows.py --as-of 2026-11-03T18:21:45Z
python3 us_midterms_windows.py --ledger us_midterms_2026_11_05_v2.json --news-dir . --as-of 2026-11-05T16:52:10Z
```

Expected v1: 88 rows; 72 pending anchors, 16 unclosed. Expected v2: 102 rows; 72 pending anchors, 10 pending market data, 20 unclosed (six calendar and fourteen observation). All horizon metrics null. `us_midterms_audit_2026_11_05.json` lists all event clocks, counts and deterministic CLI output hashes. Tests use temporary synthetic prices; none are persisted as observed BTC/ETH returns.

After obtaining original market receipts, the command is:

```sh
python3 us_midterms_windows.py --ledger us_midterms_2026_11_05_v2.json --news-dir . --market-manifest market.json --as-of <actual-cutoff-Z> --write-baseline-lock baselines_001.json
python3 us_midterms_windows.py --ledger us_midterms_2026_11_05_v2.json --news-dir . --market-manifest market_later.json --as-of <later-cutoff-Z> --baseline-lock baselines_001.json
```

Do not run the illustrative `<...>` placeholders literally. Market manifest schema and paging are documented in `US_MIDTERMS_2026_11_03.md`: max 299 aligned requested buckets per page, original six-field Coinbase array. Fetch completion, not request start, is the receipt time. Retain failed requests separately. Market responses retrieved later cannot be inserted into the 3 November as-of replay; a new actual cutoff creates a new descriptive reconstruction.

A Coinbase endpoint retrieval through the available web retriever returned an accessibility error on this run; no live price response, initial price lock or actual return is claimed. The existing P1 context/control rules remain in the v1 protocol. No production, trading, P1 regime rules, NAV/P&L or schedules are changed.
