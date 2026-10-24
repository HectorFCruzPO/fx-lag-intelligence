# MONEX and three-source timing research

Research date: 2026-10-23; reconciled with merged PR #9 on 2026-10-24. This PR changes documentation only. The MONEX closing-average collector is now implemented and owner-tested live; no Promerica collector or live alert is implemented.

## Research decision

Track three distinct published series: a precisely identified MONEX statistic, BCCR USD reference compra (317), and Promerica public branch USD/CRC compra. The owner accepts that the public branch quote may differ from the online/app quote. That difference does not block this research; it limits claims about executable proceeds.

Test whether movements often appear in MONEX, then BCCR, then Promerica. Do not build that order into the data or assume that BCCR mechanically passes a MONEX price to the bank. Each source describes a different market or price. Record increases, decreases, unchanged observations, opposite moves and absent follow-through. No useful lag or causal relationship has been established.

## Official MONEX evidence

| Source | Confirmed observation | Limit |
| --- | --- | --- |
| [MONEX average table 748](https://gee.bccr.fi.cr/indicadoreseconomicos/cuadros/frmvercatcuadro.aspx?CodCuadro=748&Idioma=1) | Describes a transaction-weighted wholesale average; dated values and zeros are displayed. | Catalog/metadata now identify closing-average indicator 3323 (SDDE table 547). Zero semantics, finality and historical completeness remain unverified. One URL capitalization failed; the linked lowercase path opened. |
| [MONEX summary table 770](https://gee.bccr.fi.cr/indicadoreseconomicos/Cuadros/frmVerCatCuadro.aspx?CodCuadro=770&Idioma=1) | Separates traded-rate statistics and activity; includes a session-state clock. | The clock does not establish per-observation publication time, timezone or refresh guarantees. |
| [Official MONEX service description](https://www.bccr.fi.cr/cr/es/sistema-de-pagos/servicios-sinpe/servicios-dirigidos-a-entidades/mercado-de-monedas-extranjeras.html) | Describes participant currency trading and states business-day trading hours of noon–13:00. | Trading hours do not establish the publication window or holiday calendar. |
| [BCCR payments regulation](https://www.bccr.fi.cr/content/dam/bccr/sobre-bccr/gobierno-corporativo/reglamentos/reglamento-sistema-pagos.pdf) | Official indexed text defines reference rates using authorized entities' transactions with the public. | Full current reference methodology and subsequent amendments were not verified here. This is not evidence that indicator 317 copies MONEX. |

Web-tool content may be cached. Page access is evidence about published content, not a working adapter or guaranteed fresh quote.

## Confirmed mapping and implemented collector

The owner downloaded the official SDDE indicator catalog and successfully queried authenticated metadata and sample series. The catalog maps:

| Indicator | Meaning | SDDE table |
| --- | --- | --- |
| **3323** | Promedio Monex al cierre | 547, Tipo de cambio promedio MONEX |
| **3439** | Promedio ponderado; description: Promedio Monex durante la sesión | 219, Resumen de negociación en MONEX |

Legacy webpage table numbers 748/770 are not SDDE table or indicator IDs. Indicator 3434 in the guide is the first traded rate, not the weighted average.

PR #9 implemented `python -m fx_lag.monex` for **3323 only**, preserving decimal values, effective dates, retrieval timestamps and separate CSV history. The owner reported a successful authenticated Python range query for October 20–23 and four CSV rows saved at `2026-10-23T23:55:03.537779Z`. Both 3323 and 3439 returned matching completed-day values in the earlier PowerShell sample. See [MONEX_COLLECTOR.md](MONEX_COLLECTOR.md) for exact values, commands and evidence limits.

The owner subsequently confirmed the updated test run was OK; no exact updated Windows test count or elapsed time was supplied. The recorded development-environment result was 117 tests in 0.140s, all passing, with ResourceWarnings treated as errors. An earlier Windows run was 116 tests in 1.066s, OK with one skip.

The [official SDDE guide](https://gee.bccr.fi.cr/indicadoreseconomicos/Documentos/DocumentosMetodologiasNotasTecnicas/Estandar_API_SDDE.pdf) documents catalog downloads, metadata and date-range series queries. The owner used `/indicadoresEconomicos/descargar?idioma=ES`, then indicator metadata/series routes. Credentials stayed local. Metadata provides daily frequency and a last-publication date, not a verified per-observation intraday publication time.

**Still open:** 3439's refresh behavior during trading, publication times, revisions/finality, holiday behavior, complete history and repeated unattended reliability. Do not substitute its changing session window for a completed-day average. The implemented 3323 collector is manual; no MONEX schedule was installed.

## What timestamps can tell us

Preserve effective date/session, source publication time only when provided, and UTC retrieval time separately. Keep every retrieval, including unchanged rates. No date-only field or page clock should be expanded into an invented publication timestamp.

For comparable observations of one effective period, a changed value first seen at 12:30 after an unchanged 12:00 observation bounds its observed transition to that sampling gap, assuming successful comparable reads. Exact source update time remains unknown; changes and reversals inside the gap may be missed.

A new effective date is a new period, not automatically a revision to the previous period. Study consecutive daily-rate changes separately from within-period revisions. Missing reads, cached responses and unknown freshness weaken transition bounds.

For two sources with bounded transition intervals `(a0, a1]` and `(b0, b1]`, the possible timing difference lies within bounds `b0 - a1` and `b1 - a0`. Overlapping intervals cannot establish order. Overnight/weekend gaps must retain their actual width; do not report them as 30-minute precision.

Daily history can support descriptive day-level associations, not reconstructed intraday lead time. Never replay a final daily average as if it were known earlier in its session.

## Implementation sequence

1. Keep the working BCCR collector and owner-selected weekday 09:00–17:00, 30-minute schedule unchanged. That schedule is a sampling choice, not a confirmed publication calendar or quota.
2. Retain the confirmed MONEX mapping and owner-tested closing collector. Verify source timestamps and intraday behavior separately. The published noon–13:00 trading session may fit within sampling hours, but rate publication can occur outside it.
3. Resolve automated access for the selected Promerica public page/feed; see [PROMERICA_SOURCES.md](PROMERICA_SOURCES.md). Robots guidance does not establish a data-use license. App matching is optional later execution-price research.
4. Keep the implemented MONEX history separate under indicator 3323. Add a Promerica adapter with offline fixtures after its access/contract questions are resolved. Preserve explicit series identities before combining sources; do not put bank rates under indicator 317.
5. Collect descriptive history before alert rules. Predeclare movement thresholds, matching horizons and baseline choices. Compare all three pairs; retain ambiguous order, reverse order, no response and excluded/missing cases.
6. Report coverage, sample sizes and timing uncertainty before tendencies. Keep alerts and forecasts unimplemented until evidence and quality policies support them.

BCCR reference and MONEX sample successes are owner-reported and documented separately. No bank login, bank contact or live Promerica integration was performed. The development environment did not execute authenticated bank requests.
