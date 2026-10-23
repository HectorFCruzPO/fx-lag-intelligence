# BCCR SDDE USD compra collector

The SDDE collector is a standalone Python CLI for **BCCR USD compra reference indicator 317**, in CRC per USD. Its REST request and parser are implemented and tested offline. **The project owner shared successful authenticated single-date, weekday-range and weekend-range queries on 2026-10-23, and confirmed the range rates matched BCCR's official history.** Broader live behavior and production readiness remain unverified. It does not fall back to the [legacy prototype](BCCR_COLLECTOR.md#status-legacy-prototype-not-a-production-integration).

## Setup

Use Python **3.10 or newer**. The collector and tests use the standard library, so no packages or paid services are required.

1. Install Python from [python.org](https://www.python.org/downloads/) if necessary. On Windows, enable the installer's PATH option.
2. Get the repository and enter its folder:

   ```sh
   git clone https://github.com/HectorFCruzPO/fx-lag-intelligence.git
   cd fx-lag-intelligence
   git switch feat/bccr-csv-history
   python --version
   ```

   If you already cloned it, run commands inside that repository. If your system uses `python3`, use that instead of `python` throughout. There is no package installation step.

3. For live collection, follow BCCR's documented registration and token generation process described in [the official-source review](BCCR_COLLECTOR.md#confirmed-official-information-reviewed-2026-10-22). Do not assume an old SOAP token works with SDDE. **Offline tests do not need credentials.**
4. Set **`BCCR_SDDE_TOKEN`** in the same terminal. On Bash (Linux/macOS), prompt for the token without putting its value in shell history:

   ```sh
   read -r -s -p 'SDDE token: ' BCCR_SDDE_TOKEN
   echo
   export BCCR_SDDE_TOKEN
   ```

   On Windows PowerShell:

   ```powershell
   $secret = Read-Host 'SDDE token' -AsSecureString
   $env:BCCR_SDDE_TOKEN = [System.Net.NetworkCredential]::new('', $secret).Password
   Remove-Variable secret
   ```

   The environment variable lasts for that terminal session. The CLI does not load `.env` files. No email, representative name or token command-line argument is required. It never uses the legacy `BCCR_TOKEN` or `BCCR_EMAIL` variables. Do not paste credentials into Git, screenshots, issues or chat.

## Run a query

Use effective dates in `YYYY-MM-DD` format. A range requests both boundary dates. These commands show the interface, not evidence of a successful live query:

```sh
python -m fx_lag.bccr_sdde --date 2026-01-01
python -m fx_lag.bccr_sdde --start 2026-01-01 --end 2026-01-03
python -m fx_lag.bccr_sdde --date 2026-01-01 --timeout 15
python -m fx_lag.bccr_sdde --help
```

Run from the repository folder. JSON goes to standard output; errors and warnings go to standard error. To save a result, append `> rates-sdde.json`. Check the command's exit code (`echo $?` in Bash, `$LASTEXITCODE` in PowerShell): shell redirection can create an empty file even when collection fails.

Exit codes:

- **0:** parsed nonempty result; inspect `missing_dates` for partial coverage.
- **1:** collection failed; no observations printed.
- **2:** invalid CLI arguments.

Synthetic output, **not a real BCCR observation**:

```json
{
  "observations": [
    {
      "source": "BCCR",
      "interface": "SDDE",
      "source_url": "https://apim.bccr.fi.cr/SDDE/api/Bccr.GE.SDDE.Publico.Indicadores.API/indicadoresEconomicos/317/series",
      "indicator": 317,
      "rate": "502.12000",
      "units": "CRC/USD",
      "effective_date": "2026-01-01",
      "retrieved_at": "2026-01-04T12:00:00Z"
    }
  ],
  "missing_dates": []
}
```

`rate` is a decimal string, avoiding binary float rounding and retaining source precision. Use Python's `Decimal` for calculations. Dates are effective calendar dates, without an invented timezone. `retrieved_at` records the completed download in UTC; it does not establish publication time or freshness. Units and reference-series identity are fixed for indicator 317, not inferred from a bank quote. This rate is not an executable Promerica quote.

## Save a timestamped local CSV history

The optional `--csv` flag saves each successful observation locally while still printing the same JSON to the terminal. With your token set as above, run this in PowerShell:

```powershell
python -m fx_lag.bccr_sdde --date 2026-10-22 --csv data/bccr-history.csv
```

For a range:

```powershell
python -m fx_lag.bccr_sdde --start 2026-10-20 --end 2026-10-22 --csv data/bccr-history.csv
```

The `data` folder and CSV are created automatically. Reuse the **same path** to build history. Open it in a spreadsheet or inspect it with:

```powershell
Import-Csv .\data\bccr-history.csv | Format-Table effective_date, rate, retrieved_at
```

Close the spreadsheet before running collection again if it locks the file. Use decimal/text import settings if your spreadsheet rounds rates. The underlying CSV retains the original rate precision. Files in the repository's `data/` folder are ignored by Git. Other custom destinations are not automatically ignored; keep collected data local and do not commit it inadvertently.

### Each query keeps its retrieval timestamp

The CSV columns are `source`, `interface`, `source_url`, `indicator`, `rate`, `units`, `effective_date`, and `retrieved_at`. Tokens, request headers and publication timestamps are not saved.

- `effective_date`: the date the BCCR reference rate applies to.
- `retrieved_at`: the UTC timestamp, including available fractional seconds, when that query's response finished downloading. This is not a publication timestamp.

Two queries an hour apart produce **two rows for the same effective date, even when the rate is unchanged**. Queries for a historical date also preserve the new retrieval timestamp; they do not make an old effective date fresh. A multi-date request gives all its observations the same retrieval timestamp.

Duplicate prevention only skips an already saved combination of source, interface, indicator, effective date, numeric rate **and retrieval timestamp**. Decimal padding (`502.12` versus `502.12000`) and equivalent UTC timestamp spellings do not create duplicates. Later retrievals always remain separate. A rate change, or a return to a previous rate in a later query, is preserved. Rows stay in the order saved; existing values are not overwritten. No poll ID is invented: observations identical in every identity field are treated as the same observation.

The stderr message reports counts, for example `CSV history: 3 added, 0 already saved.` Without `--csv`, no file is saved. This prepares successful-observation history for future hourly collection, but **does not schedule queries or send alerts**. Hourly polling is not evidence that BCCR publishes hourly, and monitoring cannot guarantee avoiding losses. Failed queries are not logged as successful observations. Scheduling, failed-query tracking, freshness and alert rules remain separate work.

### Storage errors and limits

A missing-data range saves only available observations and still prints the missing-date warning. An entirely empty/failed query writes nothing. If CSV saving fails, the command exits with code 1 and does not print success JSON; the prior CSV remains intact unless the error explicitly says saving may already have completed during lock cleanup.

The file is validated before updates. A foreign header, malformed CSV, invalid observation or pre-existing duplicate causes an error rather than silently repairing your data. Back up the file before editing it manually. Writes use a temporary file in the same folder and then replace the destination; write/replace failures preserve the previous CSV. Symlink destinations are rejected.

A `.lock` sidecar prevents cooperating collectors from updating the same path simultaneously. If you see a lock error, first stop any other collector using the file. A crash can leave a stale `.lock`; remove that lock only after confirming no collector is running and keeping the CSV itself. For the default path in PowerShell:

```powershell
Remove-Item .\data\bccr-history.csv.lock
```

This small CSV history is read and rewritten when new rows are added, so cost grows with history size. It is designed for local use, not a shared network filesystem or a database. Keep backups; abrupt process termination may leave a temporary file/lock, and power-loss durability is not guaranteed. The CSV preserves successful retrievals, not a complete operational audit trail.

## Wire contract and validation policy

The [official SDDE technical guide](https://gee.bccr.fi.cr/indicadoreseconomicos/Documentos/DocumentosMetodologiasNotasTecnicas/Estandar_API_SDDE.pdf), section 1.3 and pages 19–20, documents the REST series route and JSON example used here. The implemented URL uses the `Bccr.GE` spelling from the owner's successful query, with query parameters `fechaInicio`, `fechaFin` formatted `yyyy/mm/dd` and `idioma=ES`. Authentication is only `Authorization: Bearer <token>` over verified HTTPS. The request also sends `User-Agent: Mozilla/5.0`. The successful query used both settings together; it does not establish whether that header or the uppercase `GE` is required.

The parser accepts the documented `estado`/`mensaje`/`datos` envelope and a single indicator group with string `codigoIndicador`, `nombreIndicador` and `series`; each observation contains `fecha` and numeric `valorDatoPorPeriodo`. It does not accept legacy XML, quoted rates, boolean rates or undocumented alternate wrappers. A changed shape fails explicitly rather than guessing.

Local validation policy:

- Indicator identity must be the documented string `"317"`. Values must be positive finite JSON numbers. Decimal fractions are decoded directly as `Decimal`.
- Effective dates must be valid `YYYY-MM-DD`, unique and within the requested range. Results are sorted. Invalid data rejects the whole result.
- Null values and absent dates are reported in `missing_dates`; no zero or carried-forward rate is fabricated. This is a collector policy, not a claim that every calendar date must have a BCCR publication or that a gap means a holiday. Empty/all-null results fail as no data.
- The series example supplies no publication timestamp. The collector therefore omits that field. Metadata's `ultimaPublicacion` is not fetched or assigned to individual observations; unknown extra fields are ignored until their meaning is verified.
- False `estado` or a documented `CodigoError` error object produces a sanitized service failure. Remote messages are never printed or treated as reliable authentication evidence.

## Safety and troubleshooting

Missing or malformed local tokens fail before connecting. HTTP 401/403 report authentication/access rejection; 404 calls for checking both endpoint and authentication. Other HTTP errors, including 400/429/500, fail without printing response bodies. Errors can originate from intermediaries as well as BCCR. Timeouts, TLS/network failures, interrupted downloads, invalid JSON, duplicate JSON keys and unexpected schemas produce safe errors.

All redirects are rejected, including same-host redirects and HTTPS-to-HTTP changes. The token is never forwarded to a redirect target, placed in a query string or output. There is no automatic retry or fallback host. TLS verification stays enabled. Local tokens must have valid Bearer syntax, without whitespace/control characters. The default socket timeout is 30 seconds (not a total execution deadline), with a 2 MB response limit; use smaller ranges if needed.

## Reported live query: 2026-10-23

The project owner ran this command locally in Windows PowerShell and shared its parsed output in the development conversation:

```powershell
python -m fx_lag.bccr_sdde --date 2026-10-22
```

| Output field | Reported value |
| --- | --- |
| Indicator | 317 (USD compra reference) |
| Rate | 453.45000000 CRC/USD |
| Effective date | 2026-10-22 |
| Retrieved at | 2026-10-23T21:13:05.546174Z (UTC) |
| Missing dates | None (`[]`) |

This is owner-supplied evidence of one successful authenticated query using the uppercase `Bccr.GE` URL and `User-Agent: Mozilla/5.0` together. The request settings were saved in commit `469978a` of [PR #5](https://github.com/HectorFCruzPO/fx-lag-intelligence/pull/5); commit `d8296d1` fixed the comment encoding.

The assistant did not execute this authenticated request, inspect the token, or capture the raw API response. The output is the collector's parsed JSON, not a raw-response fixture. No credential is included in this record. The owner also reported that local tests passed, without sharing an exact test count; that report is separate from the offline suite run during this review.

The initial sample supports live request/parse success for one date. The subsequent range and owner-reported reconciliation are recorded below. Neither sample proves URL case sensitivity, User-Agent necessity, general calendar behavior, freshness, historical completeness or production reliability. No publication timestamp was returned by the collector.

### Three-day range and owner-reported reconciliation

The owner subsequently shared output from:

```powershell
python -m fx_lag.bccr_sdde --start 2026-10-20 --end 2026-10-22
```

| Effective date | Returned rate (CRC/USD) |
| --- | --- |
| 2026-10-20 | 448.07000000 |
| 2026-10-21 | 450.09000000 |
| 2026-10-22 | 453.45000000 |

All three observations had retrieval timestamp `2026-10-23T21:44:19.013551Z` (UTC); `missing_dates` was `[]`. Both requested boundary dates were present in this sample, and the overlapping October 22 value matched the earlier single-date query.

After being asked to compare all three values with BCCR's official published history, the owner explicitly confirmed that they matched. This is **owner-reported reconciliation**, not an independent check performed by the assistant. No publication-history URL, screenshot or raw API response was supplied for that comparison. No credential was shared or stored.

This completes a small-sample check of authenticated collection, multi-date parsing, inclusion of both boundaries for this range, and owner-reported agreement with official history. At that stage, weekend behavior was untested; the subsequent weekend sample below narrows this gap. Holiday behavior, missing/null cases, revisions, historical completeness, repeated operation and broader reliability remain untested live.

### Weekend range and owner-reported reconciliation

The owner shared this successful Friday-through-Monday query:

```powershell
python -m fx_lag.bccr_sdde --start 2026-10-16 --end 2026-10-19
```

| Effective date | Day | Returned rate (CRC/USD) |
| --- | --- | --- |
| 2026-10-16 | Friday | 448.47000000 |
| 2026-10-17 | Saturday | 448.31000000 |
| 2026-10-18 | Sunday | 448.31000000 |
| 2026-10-19 | Monday | 448.31000000 |

All four observations had retrieval timestamp `2026-10-23T21:53:27.208715Z` (UTC), with `missing_dates: []`. The owner explicitly confirmed all four matched BCCR's official history. This is owner-supplied parsed output and owner-reported reconciliation; the assistant did not run the authenticated request or independently perform the comparison. No official-history URL, screenshot or raw API response was supplied. No credentials were shared.

The collector returned explicit weekend dates in this sample rather than filling gaps. Equal weekend/Monday rates do not establish a universal carry-forward rule, publication time, or weekend/holiday policy. These observations were collected before the CSV feature existed; the new CSV feature has been tested offline, not live on the owner's Windows machine yet.

## Validation and remaining live checks

Run the complete suite, including the unchanged legacy tests:

```sh
python -m unittest discover -s tests -v
```

Fixtures under `tests/fixtures/sdde/` are synthetic examples shaped from the guide; they are not captured authenticated responses. Tests run without credentials or network. No SDDE token was configured during implementation. Shell network access could not connect to the environment proxy; reading the guide through the web tool does not validate the API.

Before relying on broader collection, complete these checks with a legitimately supplied token:

1. The three-day sample and owner-reported reconciliation above are complete. For a repeatable audit trail, retain the exact official-history reference used in future comparisons, without credentials.
2. The reported query establishes that the current `SDDE`/`Bccr.GE` spelling worked for the reported single-date and range queries. Other casing variants and the necessity of the User-Agent header were not tested separately. The code does not try alternate hosts or follow redirects.
3. Extend validation beyond these samples: raw response types, missing/null semantics, other weekends, holidays, future effective dates, revisions and historical coverage. Both boundaries worked for the reported range; general range behavior remains to be tested. The parser continues to follow the documented example.
4. Confirm account/token validity, expiry, service limits and current publication metadata semantics. Do not infer per-observation publication timestamps from series metadata.

The guide provides enough structure to build an adapter; it does not substitute for live validation. Optional local CSV history is included. No database, schedule, Promerica, MONEX, dashboard, alerts or predictions are included. Institutional data use remains subject to the terms discussed in [DATA_SOURCES.md](DATA_SOURCES.md).
