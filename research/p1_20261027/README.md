# P1 — prospective research v1

Original BTCI v8.16 hypotheses remain frozen. This is an operational research implementation with a new actual registration date, first intended Sunday 2026-11-01 and first Monday clock 2026-11-02 10:00 UTC. Nothing is backfilled as a prospective forecast.

The operational window is Monday10:00–14:00UTC. Missing/unverified sources are SOURCE_PENDING; late runs never mint an old forecast. The runner keeps exact raw source bytes and timestamps. NFCI/ANFCI are one family. All complete future observations are stored, including false/no-signal states, with NON_EXPANSION_PRIMARY and ALREADY_EXPANSION_DIAGNOSTIC cohorts separate.

The BTC fast flag is tested against781 original parent weeks. Slow structural states are tested against750 parent weeks. Five H.4.1 releases use the original parser, publication-date checks and explicit gap checks. Data are market reference values, not executable prices.

Writes are only under research/p1/v1/ in the existing research bucket, create-only with readback checks. Forecasts and outcomes are separate immutable objects. No modification of main, live feeds, protected LONG PAPER, BTC72H coefficients or financial books.

After13 complete future Sundays, score terminal BTC return, daily-close adverse excursion and presence of confirmed structural expansion using the original price-proxy convention. These are separate outcomes. At least26 future Sundays are needed before review; that count is not a success gate or live approval.

This workflow is kept on research/p1-readiness-20261027. GitHub cron does not run nondefault branch workflows; the authorized weekly ChatGPT task updates only the branch-local tick.json, causing the isolated push workflow to execute. A triggered job is not success until its result and write/readback receipt are verified.
