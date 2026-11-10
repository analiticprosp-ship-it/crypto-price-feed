# US midterms 2026 · point-in-time audit and window protocol v1

> The following is the preserved v1 audit. For the 5 November clock inventory, separate observation checkpoint, baseline locks and executable tests, see [US_MIDTERMS_REPRODUCE.md](US_MIDTERMS_REPRODUCE.md). The v1 ledger and horizon selection remain unchanged.

Scope: issue #156, draft PR #157, `SHADOW_RESEARCH_ONLY_NO_TRADES`. The v1 ledger records the election-day check at **2026-11-03 18:21:45 UTC (19:21:45 Alicante, 13:21:45 EST)**. This is after polls opened in some states and before the first scheduled close. The selection below is fixed before any result windows have matured; the eventual prospective classification also requires a pre-result GitHub receipt and contemporaneous event evidence. No prices or outcome data were used to choose events or horizons.

| Observation | Time in UTC | Status / treatment |
|---|---|---|
| Federal general election date | 3 Nov US local date; no single UTC instant | Confirmed by FEC; no news anchor |
| First scheduled closes in eastern IN/KY | 3 Nov 23:00 (18:00 EST; 4 Nov 00:00 Alicante) | Confirmed schedule. Calendar comparison only; no evidence of a result at this instant |
| NYC scheduled close | 4 Nov 02:00 | Calendar metadata only |
| California scheduled close and start of reporting | 4 Nov 04:00 | Calendar metadata only; actual first release not verified |
| Initial official IN-05 / KY-06 counts | Unknown | Official feeds identified; no qualifying first positive vote total verified |
| AP calls for IN-05 / KY-06 and control of House / Senate | Unknown | No original timed announcement verified in the audit |
| California certification | 11 Dec local date on calendar | Actual certification and time of public release pending; no federal certification timestamp inferred |

The AP explainer published on election day discusses when the chambers might be called; it announces neither outcome. An indexed wire time is not a verified first-publication receipt. The KY results page showed zero for the displayed KY-06 candidates and a changing update stamp. The Indiana page did not yield a verifiable 2026 live tally; a search preview combined 100% reporting with an October 20 update. None of these values qualifies as a news timestamp. Source URLs, locators, and paraphrases are in the ledger; those notes are not archived HTML or precise source publication times.

The four historical seed rows were left unchanged. Their first-availability timestamps and market results remain empty: SEC approval and the reserve order need original timed publication receipts; Bybit occurrence and FBI attribution are distinct; the Binance incident and later reporting about attribution are distinct, with the latter still a secondary report in the seed. This election audit does not upgrade any of those rows.

## Event selection and evidence

- **Primary:** first explicit AP announcement of control of the US House and first explicit AP announcement of control of the US Senate, separate IDs even if the announcements coincide. Use the original AP timestamped update/dispatch. No switch to a faster publisher, a market odds threshold, a headline mentioning seat counts, or the timestamp of the most decisive price bar. These are source-specific public availability clocks; an earlier release elsewhere can be recorded as a confounder without moving the primary anchor.
- **Diagnostic:** first public official feed snapshot with a positive vote count for any candidate in IN-05 or KY-06 (one row each), and the first AP winner call for each of those districts. Selection is based on the pre-close AP agenda, not price movement or the winner. Exact election ID, district/office, candidate/party, vote total or call status and source item ID must match. A countdown, zero-filled template, partial test result, refreshed page timestamp, AP `lastUpdated`, or publication time of an explainer is insufficient. AP `winnerDateTime` denotes declaration; verify initial distribution/publication separately. If a call is reversed, append a new correction event linked to the original; retain the original receipt and label.
- **Calendar comparison:** only the first scheduled close is scored as a planned-clock comparison; it is expected information and stays separate from publication reactions. NYC/California schedules are source checks. California certification is an audit record, not a primary anchor. Pre-election commentary, private exit polls, leaks, and market odds do not become election results.

For each new event retain original URL or API request, stable source item/version and original timestamp text with offset, event occurrence time (if known), source publication time (if known), first observed receipt time, first source availability (exact or interval), UTC normalization, proof method/confidence, raw bytes path and SHA-256. Store collection clock and source clock independently. Redact credentials from any recorded request; never replace raw bytes with a later revision. Save a new ledger version for each batch of observations, preserving v1 and previous versions. Store forecasts/news separately from price labels.

**Exact:** authenticated contemporaneous original public delivery/publication with full timestamp and offset; set `EXACT_SOURCE_AVAILABLE`, `first_market_available_timestamp_utc` and `availability_evidence` with `path`, `sha256`, `observed_at_utc`, source item/version and URL. Do not convert a minute-only timestamp into false second precision. When actively observing a feed, capture successful clean responses roughly once a minute around the relevant releases, preserving each response, HTTP result and UTC fetch completion; failures, cache ambiguity, and missed polls do not establish absence. A publisher archive with both version and exact original publication metadata may support a delayed reconstruction; label it accordingly.

**Bounded:** from the same current feed use the last proven absent and first proven present receipts, `(lo, hi]`. Put both in the ledger with `BOUNDED_SOURCE_AVAILABLE`, `availability_lower_utc`, `availability_upper_utc`, and a nested `availability_evidence.last_absent` with its own path/hash/time. Leave the exact field null. Automated scoring requires a bracket of at most 120 seconds in one 5-minute bucket, and starts after the upper bound. A wider bracket, cross-bucket uncertainty, update-only metadata or no receipt leaves the main result pending; if analyzed at both bounds later, report separately as sensitivity. Use `PENDING_ANCHOR` for unresolved evidence. Publish classification separately: only genuinely captured events with rules recorded before the result and a traceable contemporaneous capture before the first scored bar are prospective; delayed reconstructions and all historical controls are descriptive. The tool checks hashes, timestamps and boundaries; a researcher still validates semantics and original publication.

## BTC/ETH alignment

Frozen venue for this event study: **Coinbase Exchange spot BTC-USD / ETH-USD**, native **5-minute UTC OHLCV** from the documented public candles endpoint. Coinbase USD is a research series, separate from existing P1's price inputs, production, Binance/USDT, indices, and perps. No substitutions. No live Coinbase rows were downloaded or verified for this audit. No trade fill is inferred.

- Use `lo=t0=hi` for exact clocks (including the separate calendar comparison). For a bounded clock use `lo, hi`. Pre-window ends at `floor5m(lo)` and spans the previous 24 hours. Save baseline close and its actual timestamp when interpreting the window. Post-window starts at the first 5-minute boundary **strictly after** `hi`. The bucket containing the news is excluded even if the time is exactly on a boundary. This sacrifices up to 5 minutes of immediate reaction for consistent ordering. An optional immediate jump can be reported separately, as first post-bar open divided by last eligible pre-bar close minus one; that interval straddles the release and is descriptive.
- All intervals are half-open `[start,end)`. Diagnostics: 15m, 1h, 4h and 1d. Primary and calendar comparison: these plus 7d, 30d and 90d. For each product/horizon return is final fully closed candle close divided by first eligible candle open minus one. MAE/MFE use the minimum low/maximum high versus that open, clipped at zero; MAE is not peak-to-trough drawdown. Realized volatility is the square root of summed squared 5m log returns, beginning at the first open, not annualized. Volume is summed in base units; it describes activity, not bid/ask liquidity.
- Process only candles closed by both audit cutoff and receipt time. Keep `PENDING_ANCHOR`, `WINDOW_NOT_MATURED`, `PENDING_MARKET_DATA` and `DATA_GAP` separate from `OK`. No gap filling, current partial bar, or zero return for missing data. Do not evaluate an unclosed horizon using interim values.

| Calendar comparison (UTC, both assets) | First eligibility for a closed window |
|---|---|
| Pre 24h | 3 Nov 23:00 |
| 15m / 1h / 4h | 3 Nov 23:20 / 4 Nov 00:05 / 4 Nov 03:05 |
| 1d / 7d / 30d / 90d | 4 Nov 23:05 / 10 Nov 23:05 / 3 Dec 23:05 / 1 Feb 2027 23:05 |

These are close times only, conditional on complete data. Each real result starts its own clock and may be days after Election Day.

## Controls and P1 comparison

Attach the latest actually published, complete P1 v8.16 receipt strictly before `lo` (with ID, provenance, decision time and age); no same-day reconstruction of a missing state. Keep BTCI as originally defined; ETH is a parallel outcome. Use point-in-time macro, ETF and liquidity context only from receipts already available before `lo`; later prints and revisions may be labeled concurrent/after as confounders, never as baseline features. Record missing P1/ETF/macro/order-book receipts as missing. Without a same-venue pre-event book archive, spreads/depth are unavailable; candle volume does not replace them.

For each horizon, propose a fixed historical comparison: list the prior 104 matching UTC weekdays at the same UTC time of day as the frozen pre-window cutoff, newest first, with the same alignment and venue. Require full horizon to end by the news cutoff, exact same frozen P1 pre-event regime, both assets complete, and no overlap with another accepted control window or known seed-event date/result window (use the full UTC date if a historical timestamp is unresolved). Log exclusions before comparing returns and take up to eight eligible intervals without replacement, no further search if fewer qualify. The absence of an event in the current seed is not evidence of an event-free control; review against a separately frozen event census with the same inclusion criteria, else label the comparison exploratory. No post-event volatility or returns in matching. Report coverage and baseline distribution before event deltas. Use one Nov 3 election cluster; overlapping release windows are correlated and cannot increase independent sample size. Leave single-cluster inference descriptive; broader validation of P1 incremental value is still open.

## Reproduce

From this directory, Python 3.10+ (standard library only):

```sh
python3 us_midterms_windows.py --as-of 2026-11-03T18:21:45Z
```

Expected: 88 rows (both assets), 72 `PENDING_ANCHOR` and 16 `WINDOW_NOT_MATURED`, all metrics null. Later, pass `--ledger <version.json> --news-dir <news-receipts> --market-manifest <market.json> --as-of <UTC-Z>`. A separate execution must acquire the public market responses; this tool does not call external services or change project state. The manifest is `{"receipts":[{"product_id":"BTC-USD","path":"btc-page.json","sha256":"<hex>","retrieved_at_utc":"<UTC-Z>","request_url":"https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=300&start=<UTC-Z>&end=<UTC-Z>"}]}`. Include ETH and repeat for contiguous requests, max 299 intervals per page; align to UTC grid and keep original Coinbase JSON array bytes. The loader filters vendor extra bars beyond the requested range, rejects conflicting duplicate candles, verifies hashes, and never uses a receipt newer than the cutoff. Keep receipts and their output hashes together. Preserve failed requests separately. The absence of a live quote in the current PR is intentional and is not a failed reaction test.

No production files, P1 rules, LONG PAPER, BTC72H, schedules, NAV/P&L, signals or limits are modified.

