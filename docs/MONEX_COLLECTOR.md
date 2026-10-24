# MONEX daily closing-average collector

This command retrieves BCCR's **MONEX closing average, indicator 3323**, through
the official SDDE REST API. It is a wholesale market statistic in CRC per USD,
not BCCR reference compra (317) or an executable Promerica quote.

The implementation is tested offline. On 2026-10-23 the owner successfully
requested authenticated metadata and four-date series samples from their Windows
computer using PowerShell. The owner subsequently reported a successful live
Python MONEX query and CSV save; see the validation record below. No credentials
are available in the development environment.

## Install and configure

Use Python 3.10 or newer. From PowerShell, enter your repository folder:

```powershell
cd C:\Users\marce\fx-lag-intelligence
python --version
python -m fx_lag.monex --help
```

There are no third-party Python runtime dependencies. Use the same BCCR SDDE
subscription token as the reference collector, through `BCCR_SDDE_TOKEN`.
Never paste it into chat, Git, command arguments or screenshots.

If that environment variable is already configured, skip this step. If you have
the protected `data/bccr-token.dpapi` created by the existing setup, load it in
the same Windows account that saved it:

```powershell
try {
    $encrypted = (Get-Content .\data\bccr-token.dpapi -Raw).Trim()
    $secret = ConvertTo-SecureString $encrypted
    $credential = [System.Management.Automation.PSCredential]::new('bccr', $secret)
    $env:BCCR_SDDE_TOKEN = $credential.GetNetworkCredential().Password
    Write-Host "Token loaded into this PowerShell session."
} catch {
    Write-Host "Could not load the protected token for this Windows account."
} finally {
    Remove-Variable encrypted, secret, credential -ErrorAction SilentlyContinue
}
```

The success message does not verify that the token is currently valid. Other
systems can follow the environment-variable setup in [BCCR_SDDE.md](BCCR_SDDE.md).
Do not copy a Windows protected token file between accounts or operating systems.

## Request rates and save history

One effective date:

```powershell
python -m fx_lag.monex --date 2026-10-23
```

Inclusive range and separate local CSV:

```powershell
python -m fx_lag.monex --start 2026-10-20 --end 2026-10-23 --csv .\data\monex-history.csv
```

Use a small range first. Dates are examples from the owner's sample, not an
instruction to repeatedly collect old data. `--timeout 30` sets the socket timeout
in seconds. Dates must be `YYYY-MM-DD`; the start must not follow the end.

Output is JSON with `observations` and `missing_dates`. Each observation contains:

| Field | Meaning |
| --- | --- |
| `source`, `interface` | `BCCR`, `SDDE`; BCCR publishes the MONEX statistic |
| `source_url`, `indicator` | The exact series endpoint and integer `3323` |
| `rate`, `units` | Decimal string, preserving source precision; `CRC/USD` |
| `effective_date` | Source observation date, not the retrieval date |
| `retrieved_at` | UTC timestamp after receiving the response |

No publication timestamp is invented. A successful query with some missing or
null-valued dates returns the available rows and a warning; it never fills rates.
No usable rows, invalid data, authentication, HTTP or transport failures return
exit code 1. Invalid CLI arguments return exit code 2. Successful queries return 0.
All-null or empty responses fail rather than fabricating a zero. A numeric zero
or negative price is rejected; its meaning must be investigated, not interpreted
as a market collapse.

CSV saving is optional. Use `monex-history.csv`, not `bccr-history.csv`: the writer
rejects incompatible source URLs or indicators and preserves the existing file.
Rows retain indicator 3323 as the series identity. Every distinct retrieval is
kept even when the effective date and rate are unchanged. Only an exact duplicate
observation is skipped. Saving uses the existing atomic replacement and lock
protections; see [CSV history guidance](BCCR_SDDE.md#save-a-timestamped-local-csv-history)
for lock recovery and backups. Local `data/` files are ignored by Git.

After using the command, remove the session token when no longer needed:

```powershell
Remove-Item Env:BCCR_SDDE_TOKEN -ErrorAction SilentlyContinue
```

The existing scheduled task loads its protected token independently. The manual collector
does not install a task. Optional scheduling is now available separately in
[MARKET_AUTOMATION.md](MARKET_AUTOMATION.md); BCCR triggers remain unchanged. The manual
command does not share the scheduler's persistent HTTP 429 pause: if it reports
429, stop manual requests and respect the existing pause/Retry-After guidance.
There are no automatic retries. Numeric request limits remain unverified.

## Contract and evidence

The [official SDDE guide](https://gee.bccr.fi.cr/indicadoreseconomicos/Documentos/DocumentosMetodologiasNotasTecnicas/Estandar_API_SDDE.pdf),
pages 19–20, documents date-range indicator series. The collector uses:

```text
GET https://apim.bccr.fi.cr/SDDE/api/Bccr.GE.SDDE.Publico.Indicadores.API/indicadoresEconomicos/3323/series
    ?fechaInicio=YYYY/MM/DD&fechaFin=YYYY/MM/DD&idioma=ES
Authorization: Bearer <token from environment>
```

The shared SDDE parser validates the status envelope, exact indicator identity,
series array, positive numeric prices and unique dates within the requested range.
Decimal parsing avoids binary floating-point rounding. All redirects are rejected
before a follow-up request can forward credentials. Error messages omit remote
bodies and tokens; HTTP 401/403, 429 and other errors remain distinguishable.

The owner uploaded the catalog `bccr-indicators-20261023-172414.xlsx`, obtained
through an authenticated official catalog request. It maps:

| Indicator | Catalog identity | SDDE table |
| --- | --- | --- |
| 3323 | Promedio monex al cierre | 547, Tipo de cambio promedio MONEX |
| 3439 | Promedio ponderado; description: Promedio Monex durante la sesión | 219, Resumen de negociación en MONEX |

Both catalog rows are daily. The owner subsequently reported successful
authenticated metadata requests: 3323 starts 2006-11-24; 3439 starts 2007-12-01.
Both metadata responses reported last data/publication **date** 2026-10-23,
and units `Colón Costarricense`. The CRC/USD interpretation comes from the
published MONEX exchange-rate table, not from assigning currency units to volume
or trade-count indicators.

The owner reported these identical values for both series after the session:

| Effective date | 3323 closing average | 3439 session average |
| --- | --- | --- |
| 2026-10-20 | 456.12000000 | 456.12000000 |
| 2026-10-21 | 454.99000000 | 454.99000000 |
| 2026-10-22 | 454.66000000 | 454.66000000 |
| 2026-10-23 | 454.31000000 | 454.31000000 |

Official comparison pages: [daily average](https://gee.bccr.fi.cr/indicadoreseconomicos/cuadros/frmvercatcuadro.aspx?CodCuadro=748&Idioma=1)
and [session summary](https://gee.bccr.fi.cr/indicadoreseconomicos/Cuadros/frmVerCatCuadro.aspx?CodCuadro=770&Idioma=1).
Legacy webpage table numbers differ from the catalog's SDDE table codes.

These samples confirm owner-side authenticated access and mapping. They do not
prove complete historical coverage, unrevised finality, publication time, refresh
frequency, holiday behavior or reliable unattended operation. The formatted
PowerShell output is not a captured raw JSON fixture. Tests use explicitly
synthetic JSON based on the documented structure; a deliberately different
eight-decimal price tests precision. No catalog workbook or token is committed.

## Research limits and next validation

3323 is the selected daily closing-average series. Indicator 3439 is deliberately
not exposed by this CLI; its during-session refresh behavior requires observation
and verification. Matching completed-day values do not prove that the two series
update together or are interchangeable during trading.

Poll timestamps measure when a value was observed. Daily history cannot establish
an exact intraday lag or that a MONEX change caused a BCCR/Promerica change. A
future study must keep all three series separate and retain unchanged, missing,
reverse-order and no-follow-through cases. The owner's chosen Promerica public
branch rate need not equal the app rate, but it must be labeled correctly.

The owner has now run the new Python command locally with matching sample values.
Validate dates around weekends/holidays and revisions before configuring
any MONEX schedule. No Promerica collector, alert, prediction, database or paid
service is included.

## Offline tests

```powershell
python -m unittest discover -s tests -v
```

The complete suite includes the legacy collector, reference SDDE collector,
CSV history, BCCR scheduler and MONEX tests. MONEX cases cover precision, identity,
missing/invalid data, JSON/schema errors, authentication, HTTP 429, safe error
handling, redirects, transport failures, CSV isolation and CLI behavior. Tests
make no real network requests and require no token.

## Owner-reported live Python validation, 2026-10-23

On Windows with Python 3.14, the owner ran:

```powershell
python -m fx_lag.monex --start 2026-10-20 --end 2026-10-23 --csv .\data\monex-history.csv
```

The CLI returned indicator 3323, all four rates listed above, `CRC/USD`, the
correct effective dates and retrieval timestamp `2026-10-23T23:55:03.537779Z`.
It reported `missing_dates: []` and `CSV history: 4 added, 0 already saved.`
This is a successful owner-reported authenticated Python query and CSV save for
that sample, not a live request executed by the development environment.

Before that query, the owner ran 116 offline tests in 1.066s: `OK (skipped=1)`.
The skip was not identified in that abbreviated output. ResourceWarnings named
synthetic HTTP errors 401/403/429/503; investigation found the legacy collector
left non-500 HTTP error responses unclosed. The follow-up fix closes those
responses without reading their bodies and adds a focused regression test.
Existing SOAP HTTP 500 parsing and closure remain covered by the full suite.
The owner must rerun the updated suite to confirm cleanup on Python 3.14/Windows.

Publication times, intraday behavior, holiday coverage, historical completeness,
revisions and repeated unattended reliability remain unverified. The manual collector
installs no task. Optional scheduling is now available separately; no predictive
or lag claim is made.

## Optional scheduling follow-up

A guarded MONEX task can now be installed using the
[market automation guide](MARKET_AUTOMATION.md). It preserves the closing-series
identity and shares a persistent provider pause with BCCR 317. Installation and
repeated unattended operation still need owner-side validation.
