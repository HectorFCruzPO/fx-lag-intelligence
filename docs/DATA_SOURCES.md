# FX Lag Intelligence — Data source discovery

Status: historical discovery notes researched 2026-10-22, with a current collector review below. No live collection, predictive relationship, or production readiness is established.

## Current collector and API review

The [SDDE REST adapter](BCCR_SDDE.md) is implemented and tested offline. The [legacy collector prototype](BCCR_COLLECTOR.md) remains intact and is not the intended production integration. The linked review records BCCR's announced 2026-06-30 retirement, the separately located official replacement SDDE API guide, inaccessible pages and remaining uncertainties. The project owner subsequently shared successful authenticated SDDE single-date, weekday-range and weekend-range queries on 2026-10-23 and confirmed that the range rates matched BCCR's official history; see the [validation record](BCCR_SDDE.md#reported-live-query-2026-10-23). The legacy interface remains unvalidated. The following original discovery notes describe historical evidence, not current service availability.

## Current three-source research decision

The owner selected Promerica public branch compra for research even when it differs from the app. See [MONEX and three-source research](MONEX_RESEARCH.md) for the weighted-average candidate, official sources, timestamp limits and unresolved SDDE mapping. Earlier channel-applicability questions below concern executable-price claims, not a prerequisite for studying the selected public series. No Promerica or MONEX collector has been implemented.

## Repository and access status

At the time of the original discovery, the local checkout was stale: branch work, HEAD 7c122941cbe22d11eaf23ad7c047b8b0dd28b2dd, contained the original short README and no PRD. GitHub’s main was read directly through the GitHub connector before source research:

- README, file hash ebb43a70b50acc57fe80fa5b637f6951f2b6d8c0.
- PRD, file hash ca2902683ab08d9df7ff573069c18b7d67d65f50.

These are file hashes, not the main commit SHA. The exact remote main commit could not be established through Git in that discovery task; this is historical context, not the current branch status.

git ls-remote and a push dry run to a proposed documentation branch both failed because the environment could not connect to proxy port 8080. No push occurred. Those discovery notes were prepared as a standalone proposal; that statement does not describe publication of the current implementation branch.

Official websites were researched through the web tool. Shell network access was unavailable; some web fetches also failed, as recorded below. Search-index content is weaker evidence than a successful page fetch. Neither establishes a working ingestion adapter.

## Evidence labels

VERIFIED means supported by cited official material, with access limitations stated. ASSUMPTION / RECOMMENDATION means a proposed interpretation or approach. OPEN QUESTION means evidence remains insufficient.

Compra is the bank buying USD from the customer—the relevant direction when selling USD for CRC. A bank quote, BCCR reference rate, and wholesale market statistic are different series. The current README and PRD require preserving those distinctions.

## Comparison table

| Source | Official access found | Definition | Frequency and timestamps | History | Main unresolved gate |
| --- | --- | --- | --- | --- | --- |
| Promerica Costa Rica | Homepage, branch rate page, history form | Published USD/CRC compra; separate accounting reference must be excluded | Homepage says today’s rate; effective timestamp and update schedule unverified | Interface exists; records and coverage unverified | Collection permission, channel applicability, effective time |
| BCCR reference compra | Official service guide; indicator 317 | Official reference buying rate, CRC/USD | Daily; guide describes next-day availability after 17:30; present calendar/timezone need confirmation | Date-range service documented; complete retrieval untested | Current API operation, methodology, reuse rights |
| MONEX via BCCR | Average table 748, summary table 770 | Wholesale transaction statistics, including weighted-average CRC/USD | Dated observations; summary includes a session-state clock; refresh guarantee unverified | Date filters and Excel-export controls exist; full coverage untested | Exact API indicator, finality, release delay, redistribution |

## Promerica Costa Rica

A [follow-up Promerica access review](PROMERICA_SOURCES.md) researched on 2026-10-23 records the owner's online/app channel, public source candidates, robots exclusions, unreadable website terms, and unresolved supported-access questions. No Promerica collector is implemented. The notes below are the earlier discovery snapshot.

VERIFIED: The homepage labels dollar/euro compra and venta and links to a history form. Its extracted rate cells were empty. The separately fetched branch page displays USD/CRC compra and venta and warns that prices can change with market conditions. It also contains a distinct accounting-reference section. No effective date/time accompanies the figures in the extracted branch page. The history form has selectors and a query button, but historical records were not retrieved. Reading these pages required no login. Homepage, branch page, history form.

OPEN QUESTIONS:

- No documented public API/feed or API authentication scheme was verified. This does not prove one does not exist.
- Automated-collection permission, polling limits, source-specific terms and robots guidance remain unresolved.
- No fixed refresh cadence or publication timestamp was verified.
- Confirm whether the published rate applies to USD 3,000 through the user’s online channel, branches, cash, transfers or negotiated conversions, and whether fees apply.
- Confirm historical coverage, daily versus intraday detail, revisions, and whether past values represent opening or closing rates.

RECOMMENDATION: Prefer a bank-approved structured feed. Otherwise investigate a permitted webpage method with manual validation. Do not substitute the accounting reference or assume branch and online quotes match.

Reliability risks include dynamic empty cells, page changes, caching, missing timestamps and channel differences. An initial non-www homepage fetch timed out; www pages subsequently loaded.

## BCCR USD compra reference rate

VERIFIED: The official service guide identifies compra as indicator 317; 318 is venta. It documents free current/historical queries, subscription activation through email and a subscription token. Inputs include indicator, date range, representative user name, sublevels, email and token. XML and DataSet methods are documented. Official service guide.

The documented service address is:

https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx

This is a documented endpoint, not a successfully tested integration. No token was created or authenticated request attempted.

The guide says next-day compra/venta can be queried after 17:30. Its timezone, holiday behavior and present applicability need confirmation. A value’s effective date must not be treated as its publication timestamp. Service guide.

VERIFIED: BCCR’s 2025 site guide describes downloadable CSV/Excel/PDF data and metadata containing indicator code, frequency, units, first/last observation and last publication. Its compra example shows indicator 317, daily frequency and first observation 1983-01-01. This documentation screenshot does not verify a complete live archive. The guide identifies the newer portal as https://sdd.bccr.fi.cr/es/IndicadoresEconomicos/Inicio/. Site guide, sections 2.7–2.13.

DEFINITION / OPEN QUESTION: The verified identity is BCCR reference compra for USD, not a Promerica quote or MONEX transaction price. An official indexed 2017 amendment describes a previous-day transaction-amount-weighted buying-price average over a BCCR-defined period, but direct access to its PDF returned 404. Older official methodology documents differ. The currently operative formula, eligible transactions, cutoff, exclusions, non-business-day handling and amendments therefore remain not fully verified. 2017 amendment—indexed evidence only.

OPEN QUESTIONS / RISKS: The subscription catalog returned 503 and the service-page fetch failed. Verify current API support after the portal migration, token lifecycle, request limits, historical retrieval, revisions and publication metadata. Credentials must remain outside Git.

## MONEX market data

VERIFIED: Table 748 defines its rate as the weighted average of transactions in the wholesale MONEX market. It displays daily observations across years, zero entries, date filters and an Excel-export control. Earliest history, completeness, precise weighting rules, revision policy and API indicator code were not established. Table 748.

VERIFIED: Table 770 publishes first, last, minimum, maximum, simple-average and weighted-average traded rates in CRC/USD; previous-session weighted average; USD amounts; match counts; and best board offers. Its notes describe a session-state clock and trading hours of 12:00–13:00 starting 2022-06-06. These notes do not establish a guaranteed refresh interval or complete current holiday calendar. Public reading required no login; information about trading subscriptions points separately to Central Directo. Table 770.

## Candidate recommendation

RECOMMENDATION: Investigate the completed-session daily weighted-average traded rate first. Use table 748 and reconcile matching completed dates with table 770’s weighted-average row.

An amount-weighted average is a reasonable research candidate for representing aggregate trading, but its exact weighting and eligible transactions still require confirmation. Do not assume the tables are identical until reconciled. Table numbers 748 and 770 are not verified API indicator codes.

| Candidate | Proposed role and limitation |
| --- | --- |
| Daily weighted average | First candidate for daily comparison with Promerica compra; cannot establish intraday lead time |
| Running session weighted average | Later intraday study only after refresh cadence, cumulative window, timestamps and historical snapshots are verified |
| First/last, minimum/maximum, simple average | Sensitivity checks; distinct statistics that must not be interchanged |
| Best board compra/venta | Offers rather than completed trades; observed zeros and snapshot timing leave suitability unresolved |
| Volume and match count | Activity/data-quality context; amounts and counts are not CRC/USD prices |

OPEN QUESTIONS: Identify exact indicator codes and current API availability. Confirm displayed-clock timezone, which date it applies to, release delay, session calendar, finality, earliest history and revisions. Clarify missing/zero semantics; never interpret a displayed zero as a market collapse.

Historical daily tables do not establish availability of historical intraday snapshots. No live MONEX API, subscription entitlement or trading credentials were verified.

## Permissions and reliability

VERIFIED: BCCR’s website terms allow personal/business/organizational use and downloading without altering content, but require express authorization for distribution, transmission or commercialization. They reserve the ability to change or suspend information and do not guarantee uninterrupted or error-free service. Free API access does not establish permission to republish data. BCCR terms.

RECOMMENDATION / OPEN QUESTION: Clarify which current terms govern storage, dashboard display, derived statistics, WhatsApp/web-push alerts and raw-data redistribution. Obtain required authorization before those uses. Resolve Promerica permissions separately. The repository’s MIT license does not grant rights to institutional data.

This spike contacted no institutional staff and makes no legal determination about a particular proposed use.

## Recommended approach and next research steps

1. Keep source research and implementation changes on reviewed branches; do not merge automatically.
2. Resolve permissions and Promerica quote applicability. Request supported feeds, timestamps, history, schedules, request limits and applicable terms.
3. Inspect current BCCR metadata/catalog. Confirm indicator 317, current reference methodology, MONEX indicator mapping, historical boundaries and release calendar. Test authorized read-only access later with a legitimately supplied token.
4. Validate a small official historical sample across all sources, including weekends, holidays, missing/zero records and revisions. Reconcile the MONEX tables before selecting a series.
5. Preserve exact series identity, CRC/USD units, effective date/session, separate publication and retrieval times, timezone, final/provisional status, quality and provenance. Preserve unknown source times. Refetching old data cannot make it fresh.
6. Start with daily descriptive comparisons if only daily history is available. Reconstruct information available at each decision time; never use a day’s final average earlier that day.
7. Predeclare comparison horizons and baselines, then measure false alarms, missed moves and lead-time distributions on held-out data. A useful predictive lag may not exist. Keep live movement alerts disabled until access, cadence, freshness and PRD quality requirements are resolved.

For the beginner: an actual 1 CRC/USD Promerica compra change alters gross proceeds on USD 3,000 by CRC 3,000. A MONEX change of that size supplies only a hypothetical equal-movement scenario. It does not establish that Promerica changed or will change. No fixed lag or financial benefit has been demonstrated.
