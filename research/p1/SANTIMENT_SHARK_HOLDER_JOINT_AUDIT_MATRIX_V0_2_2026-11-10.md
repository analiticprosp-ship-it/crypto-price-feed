# Joint Santiment cohort × holder contraction — audit matrix v0.2
As of 2026-11-10. Research only; NOT_ACCEPTED; NO_TRADES.
Related: PR #162 and PR #163. This is a combined analysis plan, NOT a completed data run.

## Verified repository state
PR #162 contains only a research registration file, as does PR #163. No API receipts, cohort CSV, point-in-time archive, or OOS results in either changed-file list. The two PRs are separate drafts; do not mistake them for deployed indicators.

## Screenshot arithmetic and what cannot be inferred
1-10 BTC supply change: +10,076 BTC (+0.49%); 10-100 BTC: +4,131 BTC (+0.10%); sum +14,207 BTC. This is aggregate balance change by address bucket, not proven buys or investor identity. Count of all holders down 108,700 from ~59.99M = -0.1812%; total 59.88M rounded. Exchange supply ~1.28M BTC is a level, not a measured inflow/outflow for the same window. Dates, measurement intervals, metric definitions and labels remain unverified.
No logical contradiction between total count falling and mid-sized bucket supply rising. But it does NOT establish transfer from small to large addresses without cohort-specific balances and flows.

## Point-in-time evidence checklist
A. Exact Santiment metric identifiers and API availability/permissions: MISSING.
B. UTC as-of timestamp and first-available timestamp for both screenshots: MISSING.
C. Daily 0-0.001, 0.001-0.01, 0.01-0.1, 0.1-1, 1-10, 10-100, 100-1000 BTC holder counts and combined balances: MISSING.
D. Exchange supply history and label revision history: MISSING.
E. Address cohort transitions, change decomposition, exchange flows and entity adjustment: MISSING.
F. Independent BTC daily price history and point-in-time snapshots: MISSING.
G. Negative examples and out-of-sample results: NOT RUN.

## Decomposition
Delta total count = sum(delta counts across exhaustive nonoverlapping buckets) subject to provider scope/definition. Validate total vs sum daily; require same UTC day. For each bucket compute delta N and delta BTC. Bucket boundary crossings and consolidation can move both series without any new economic buying. Calculate supply and count changes separately. Use exchange supply only as contextual covariate; cannot identify retail sales from its decline.

## Hypothesis table
H1 absorption: count of small addresses falls; 1-100 BTC supply rises; BTC stabilizes; realized cap does not deteriorate. Candidate only.
H2 false bottom: same on-chain combination occurs, BTC subsequently falls >=10% or >=20% before 30/60-day recovery. Explicit negative control.
H3 custody artifact: address counts shift, on-chain cohort balances/flows inconsistent with retail selling. Classification warning.
H4 liquidity regime: interaction with yields, USD and exchange liquidity changes apparent signal. Must compare against macro-conditioned baseline.

## Next runnable gate
First fetch timestamped metric definitions and daily historical cohort series from Santiment Sanbase with authorized access, preserve raw response hash and first availability; then verify the two screenshot anchors. Do not calculate an OOS hit rate until source evidence exists. Keep P1 CYCLE, ONCHAIN_DEMAND, RECOVERY_QUALITY consumers research-only.

## Writeback limits
Only this document added to PR #163 branch. No merge, API collection, automation, strategy change, NAV or P&L change.
