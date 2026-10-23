# MONEX and three-source timing research

Research date: 2026-10-23. Documentation only; no MONEX or Promerica collector or live alert was added.

## Research decision

Track three distinct published series: a precisely identified MONEX statistic, BCCR USD reference compra (317), and Promerica public branch USD/CRC compra. The owner accepts that the public branch quote may differ from the online/app quote. That difference does not block this research; it limits claims about executable proceeds.

Test whether movements often appear in MONEX, then BCCR, then Promerica. Do not build that order into the data or assume that BCCR mechanically passes a MONEX price to the bank. Each source describes a different market or price. Record increases, decreases, unchanged observations, opposite moves and absent follow-through. No useful lag or causal relationship has been established.

## Official MONEX evidence

| Source | Confirmed observation | Limit |
| --- | --- | --- |
| [MONEX average table 748](https://gee.bccr.fi.cr/indicadoreseconomicos/cuadros/frmvercatcuadro.aspx?CodCuadro=748&Idioma=1) | Describes a transaction-weighted wholesale average; dated values and zeros are displayed. | API identifier, zero semantics, finality and historical completeness are unverified. One URL capitalization failed; the linked lowercase path opened. |
| [MONEX summary table 770](https://gee.bccr.fi.cr/indicadoreseconomicos/Cuadros/frmVerCatCuadro.aspx?CodCuadro=770&Idioma=1) | Separates traded-rate statistics and activity; includes a session-state clock. | The clock does not establish per-observation publication time, timezone or refresh guarantees. |
| [Official MONEX service description](https://www.bccr.fi.cr/cr/es/sistema-de-pagos/servicios-sinpe/servicios-dirigidos-a-entidades/mercado-de-monedas-extranjeras.html) | Describes participant currency trading and states business-day trading hours of noon–13:00. | Trading hours do not establish the publication window or holiday calendar. |
| [BCCR payments regulation](https://www.bccr.fi.cr/content/dam/bccr/sobre-bccr/gobierno-corporativo/reglamentos/reglamento-sistema-pagos.pdf) | Official indexed text defines reference rates using authorized entities' transactions with the public. | Full current reference methodology and subsequent amendments were not verified here. This is not evidence that indicator 317 copies MONEX. |

Web-tool content may be cached. Page access is evidence about published content, not a working adapter or guaranteed fresh quote.

## Selected candidate and mapping still needed

**Recommendation:** begin with the completed-session daily transaction-weighted average. Reconcile a small sample of matching completed dates between tables 748 and 770 before adopting a single series. Keep a running session average separate if it later becomes available; its changing aggregation window is not interchangeable with a completed-day value.

Neither 748 nor 770 is a verified SDDE indicator code. Do not code an adapter using those numbers as indicator IDs.

The [official SDDE guide](https://gee.bccr.fi.cr/indicadoreseconomicos/Documentos/DocumentosMetodologiasNotasTecnicas/Estandar_API_SDDE.pdf) documents authenticated catalog downloads, metadata and date-range series queries. Its MONEX example identifies 3434 as the first traded rate, not the weighted average. Examples are not live validation. Series examples contain dates and values; metadata's last-publication example is date-only. Neither supplies a verified per-observation intraday publication timestamp.

The documented discovery route, relative to the existing SDDE base URL in [BCCR_SDDE.md](BCCR_SDDE.md), is:

1. Download `/cuadro/descargar?idioma=ES` and `/indicadoresEconomicos/descargar?idioma=ES` as Excel catalogs.
2. Find the exact MONEX table and weighted-average indicator. Record code, full name, units, frequency and catalog retrieval date.
3. Use `/cuadro/{codigo}/metadata?idioma=ES` or `/indicadoresEconomicos/{codigo}/metadata?idioma=ES` with the catalog-confirmed code.
4. Validate a short historical series through the documented series route and reconcile official table values.

These are documented routes, not authenticated requests made during this research. Bearer credentials stay local; never paste a token into an issue or chat. Do not assume legacy table IDs equal SDDE table IDs. An authenticated catalog/metadata result is the next missing evidence, rather than a guessed endpoint.

## What timestamps can tell us

Preserve effective date/session, source publication time only when provided, and UTC retrieval time separately. Keep every retrieval, including unchanged rates. No date-only field or page clock should be expanded into an invented publication timestamp.

For comparable observations of one effective period, a changed value first seen at 12:30 after an unchanged 12:00 observation bounds its observed transition to that sampling gap, assuming successful comparable reads. Exact source update time remains unknown; changes and reversals inside the gap may be missed.

A new effective date is a new period, not automatically a revision to the previous period. Study consecutive daily-rate changes separately from within-period revisions. Missing reads, cached responses and unknown freshness weaken transition bounds.

For two sources with bounded transition intervals `(a0, a1]` and `(b0, b1]`, the possible timing difference lies within bounds `b0 - a1` and `b1 - a0`. Overlapping intervals cannot establish order. Overnight/weekend gaps must retain their actual width; do not report them as 30-minute precision.

Daily history can support descriptive day-level associations, not reconstructed intraday lead time. Never replay a final daily average as if it were known earlier in its session.

## Implementation sequence

1. Keep the working BCCR collector and owner-selected weekday 09:00–17:00, 30-minute schedule unchanged. That schedule is a sampling choice, not a confirmed publication calendar or quota.
2. Resolve MONEX catalog mapping and timestamps. The published noon–13:00 trading session may fit within sampling hours, but rate publication can occur outside it.
3. Resolve automated access for the selected Promerica public page/feed; see [PROMERICA_SOURCES.md](PROMERICA_SOURCES.md). Robots guidance does not establish a data-use license. App matching is optional later execution-price research.
4. Add separate adapters with offline fixtures only after contracts are verified. Extend storage with explicit series/statistic identity before combining sources; do not put MONEX or bank rates under indicator 317.
5. Collect descriptive history before alert rules. Predeclare movement thresholds, matching horizons and baseline choices. Compare all three pairs; retain ambiguous order, reverse order, no response and excluded/missing cases.
6. Report coverage, sample sizes and timing uncertainty before tendencies. Keep alerts and forecasts unimplemented until evidence and quality policies support them.

The existing BCCR live successes are owner-reported and documented separately. No authenticated MONEX request, bank login, bank contact or live Promerica integration succeeded or was attempted in this research.
