# BCCR SDDE USD compra collector

The SDDE collector is a standalone Python CLI for **BCCR USD compra reference indicator 317**, in CRC per USD. Its REST request and parser are implemented and tested offline. **No authenticated live request has been attempted or succeeded.** It is not yet a verified live integration or production-ready collector. It does not fall back to the [legacy prototype](BCCR_COLLECTOR.md#status-legacy-prototype-not-a-production-integration).

## Setup

Use Python **3.10 or newer**. The collector and tests use the standard library, so no packages or paid services are required.

1. Install Python from [python.org](https://www.python.org/downloads/) if necessary. On Windows, enable the installer's PATH option.
2. Get the repository and enter its folder:

   ```sh
   git clone https://github.com/HectorFCruzPO/fx-lag-intelligence.git
   cd fx-lag-intelligence
   git switch feat/bccr-sdde-api
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
      "source_url": "https://apim.bccr.fi.cr/SDDE/api/Bccr.Ge.SDDE.Publico.Indicadores.API/indicadoresEconomicos/317/series",
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

## Wire contract and validation policy

The [official SDDE technical guide](https://gee.bccr.fi.cr/indicadoreseconomicos/Documentos/DocumentosMetodologiasNotasTecnicas/Estandar_API_SDDE.pdf), section 1.3 and pages 19–20, documents the REST series route and JSON example used here. The implemented URL uses its section 1.3 spelling, with query parameters `fechaInicio`, `fechaFin` formatted `yyyy/mm/dd` and `idioma=ES`. Authentication is only `Authorization: Bearer <token>` over verified HTTPS.

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

## Validation and remaining live checks

Run the complete suite, including the unchanged legacy tests:

```sh
python -m unittest discover -s tests -v
```

Fixtures under `tests/fixtures/sdde/` are synthetic examples shaped from the guide; they are not captured authenticated responses. Tests run without credentials or network. No SDDE token was configured during implementation. Shell network access could not connect to the environment proxy; reading the guide through the web tool does not validate the API.

Before relying on collected rates, complete these checks with a legitimately supplied token:

1. Obtain a successful authenticated query and reconcile a small range with BCCR's official publication.
2. Confirm exact accepted URL casing: the guide varies `Ge`/`GE` and `SDDE`/`sddE`; the code follows section 1.3 and does not try alternate hosts or forward redirects.
3. Confirm actual response types, indicator 317 identity/units, inclusive date boundaries, missing/null semantics, weekend/holiday behavior, future effective dates, revisions and historical coverage. Until then, the parser intentionally implements the documented example only.
4. Confirm account/token validity, expiry, service limits and current publication metadata semantics. Do not infer per-observation publication timestamps from series metadata.

The guide provides enough structure to build an adapter; it does not substitute for live validation. No database, schedule, Promerica, MONEX, dashboard, alerts or predictions are included. Institutional data use remains subject to the terms discussed in [DATA_SOURCES.md](DATA_SOURCES.md).
