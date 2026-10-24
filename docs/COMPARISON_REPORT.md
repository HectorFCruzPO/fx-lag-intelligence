# Three-source comparison report

The report reads the existing BCCR, MONEX and Promerica CSV histories. It makes
no network requests, writes no histories and changes no scheduled tasks. It is a
descriptive research report, not an alert or prediction.

## Run it in PowerShell

From your repository folder:

```powershell
python -m fx_lag.report
```

The default output is Markdown printed in the terminal. It reads:

- `data/bccr-history.csv`: BCCR reference compra, indicator 317.
- `data/monex-history.csv`: MONEX daily closing average, indicator 3323.
- `data/promerica-history.csv`: Promerica public branch compra.

It works with the data you already have. Monday's observations will appear the
next time you run the command. **The report is manual; no report task or automatic
refresh was installed.** You do not need to wait for new observations to test it.
There are no new dependencies beyond the existing Python 3.10+ setup.

To save a readable report, use a new filename under the ignored data folder:

```powershell
python -m fx_lag.report | Set-Content -Encoding utf8 .\data\comparison-report.md
```

Open it with `notepad .\data\comparison-report.md`, or a Markdown preview in your
editor. Never redirect report output over one of the source CSV histories.

For structured output:

```powershell
python -m fx_lag.report --format json
```

Other options:

```powershell
python -m fx_lag.report --data-dir .\data --limit 20 --gap-minutes 60
python -m fx_lag.report --as-of 2026-10-26T17:00:00Z --format json
```

`--limit` controls recent entries per Markdown section; JSON includes all entries.
`--as-of` requires an explicit timezone and excludes later retrievals. It does not
reconstruct missing source publications or turn backfilled data into information
available earlier. Without it, the current UTC clock is used. Output times in
Markdown are labeled Costa Rica (UTC-06:00); machine timestamps remain UTC.

## What it shows

1. **Latest eligible poll per source:** rate, effective date when supplied, and
   retrieval time. These independently retrieved prices are not a simultaneous
   snapshot. Prior-local-date polls are labeled accordingly; retrieval age is
   displayed separately. All source freshness remains unverified.
2. **Recent poll comparisons:** previous/current rates, exact decimal delta in
   CRC/USD, increases, decreases and unchanged values. Same-date value changes
   remain separate from changes between daily effective periods.
3. **Daily history:** latest retrieved value for each effective date, first/last
   retrieval time, count of observed value revisions and signed changes between
   daily dates. This is descriptive history, not intraday evidence. JSON also
   includes all daily comparisons and retrieval counts.
4. **Observation gaps:** intervals over the configured threshold between eligible
   polls. The default 45 minutes is a diagnostic choice, not a verified source
   cadence or freshness rule. Overnight/weekend gaps remain their true length and
   are marked when they span local dates. A gap does not prove a failed request.
   Time since the last successful retrieval is shown even without a later poll;
   it is not counted as a completed gap interval.
5. **Changed-observation timeline:** retrieval chronology across the three series,
   without matching movements into causal episodes or calculating a market lag.
   Equal retrieval timestamps do not establish order; ties sort by source key only
   for deterministic display.

Missing files and header-only histories are visible, not filled with invented
rates. One observation has no comparison baseline. Invalid headers, foreign series,
duplicate/conflicting records, invalid values or unreadable files fail clearly;
no partial success report hides corrupt input. Histories are read through the
existing strict validator. Atomic collector replacement allows reading a complete
old or new file, but the three files are not read in one transaction.

## Historical batches and unknown timestamps

BCCR/MONEX rows are eligible for the observed polling timeline only when their
effective date equals their retrieval's Costa Rica date. Earlier-date rows are
backfills for this purpose; later-date rows are not current polls. Their counts
are exposed. Dated history still retains available effective dates through the
report's local as-of date, including revisions observed by then.

For example, querying October 20–23 on October 23 does **not** tell us when the
October 20 price changed. Those earlier rows belong in daily history, not an
October 20 intraday timeline. The rule is deliberately conservative: it can exclude
late observations of an earlier effective period rather than invent a signal.

Promerica supplies no verified source effective date. Its empty CSV date remains
`null` in JSON and `unknown` in Markdown. It is never filled from retrieval time.
The report compares its public-page observations, not an executable app quote.

For comparable observations of one period, the report shows the **two check
times** around a change. Those checks do not prove that the source updated between
them: caching, stale content, revisions or missed intermediate changes can affect
the result. `publication_transition_verified` is always false. Different daily
periods and daily backfills receive no intraday transition window.

No publication timestamp, exact lag, propagation order, freshness guarantee,
actionable alert, proceeds estimate or prediction is generated. BCCR reference
compra, wholesale closing averages and public branch quotes remain distinct.
Current daily closing data may not support the intraday tendencies the project
hopes to investigate. A useful relationship may not exist.

## Synthetic example and offline tests

The committed fixtures are synthetic and must not be interpreted as actual rates:

```powershell
python -m fx_lag.report --data-dir .\tests\fixtures\report --as-of 2026-10-26T17:00:00Z
python -W error::ResourceWarning -m unittest discover -s tests
```

The example includes all three sources, a MONEX decrease, unchanged checks and
later BCCR/Promerica decreases. That sequence is deliberately constructed for
tests; it supplies no evidence of a real causal chain. Tests also cover increases,
numeric equality, precision, historical batches, future dates, missing/corrupt
files, sorting, unknown times, clock timezone boundaries, gaps and read-only
behavior. Existing collector and scheduler tests run unchanged.

Success exits 0, including reports with explicit missing-file/empty statuses.
Invalid data or as-of time exits 1; invalid CLI options exit 2. `--gap-minutes`
accepts whole numbers from 1 through 525600. Extreme decimal spans exceeding
10,000 arithmetic digits are rejected safely instead of rounding silently.

Next, review the report against Monday's saved observations before adding any
matching horizons, thresholds, freshness policy or alerts. See the
[three-source research plan](MONEX_RESEARCH.md) and [automation guide](MARKET_AUTOMATION.md).
