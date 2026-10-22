# BCCR USD compra collector

This first collector requests **BCCR reference USD compra, indicator 317**, in CRC per USD. It is reference context, not an executable bank quote. It does not collect Promerica or MONEX data, store a database, run on a schedule, predict rates, or send alerts.

## Current service limitation — read first

The collector implements the official legacy web service listed in [DATA_SOURCES.md](DATA_SOURCES.md), using its `ObtenerIndicadoresEconomicosXML` operation.

On 2026-10-22, we read the [official service guide](https://gee.bccr.fi.cr/indicadoreseconomicos/Documentos/DocumentosMetodologiasNotasTecnicas/Webservices_de_indicadores_economicos.pdf). It confirms indicator 317, subscription email/token, representative user name, no sublevels, date ranges in `dd/mm/yyyy`, and XML results with code, date and value.

However, [BCCR's announcement](https://es.linkedin.com/posts/banco-central-de-costa-rica_el-banco-central-de-costa-rica-informa-a-activity-7475548841979854848-q9oI) states that the legacy Web Service would be disabled on **2026-06-30** in favor of an API. Both the legacy WSDL and operation help page returned **503 through the research web tool** during this task. A shell request could not connect to the configured proxy. These observations do not independently prove the service has been retired, but make its availability doubtful. **No authenticated request succeeded or was attempted: no BCCR credentials were configured.** This implementation is not a verified working live integration. Confirm supported access with BCCR before relying on it; a replacement API adapter is separate work.

## Setup (Python 3.10 or newer)

1. Install Python from [python.org](https://www.python.org/downloads/) if needed. On Windows, enable the installer option to add Python to PATH.
2. Clone the repository, enter its folder, and select this branch:

   ```sh
   git clone https://github.com/HectorFCruzPO/fx-lag-intelligence.git
   cd fx-lag-intelligence
   git switch feat/bccr-data-collector
   python --version
   ```

   If your system uses `python3`, replace `python` with `python3` below. No third-party Python packages or paid services are needed. Run commands from the repository folder; there is no installation step.

3. Obtain legitimate subscription credentials only through BCCR's supported process. The historical guide describes email activation and a subscription token; current registration and legacy-token validity remain unverified after the announced retirement. Do not use someone else's token or paste credentials into Git, source files, issues, or this chat.
4. Set `BCCR_EMAIL` and `BCCR_TOKEN` in your terminal's environment. For Bash on Linux/macOS, these prompts avoid placing the values in shell history:

   ```sh
   read -r -p 'BCCR subscription email: ' BCCR_EMAIL
   read -r -s -p 'BCCR subscription token: ' BCCR_TOKEN
   echo
   export BCCR_EMAIL BCCR_TOKEN
   ```

   For Windows PowerShell:

   ```powershell
   $env:BCCR_EMAIL = Read-Host 'BCCR subscription email'
   $secret = Read-Host 'BCCR subscription token' -AsSecureString
   $env:BCCR_TOKEN = [System.Net.NetworkCredential]::new('', $secret).Password
   Remove-Variable secret
   ```

   Variables last for that terminal session. The program reads these environment variables directly; it does **not** automatically load `.env` files. `.env` and Python caches are ignored by Git as a precaution.

## Request one date or a range

Replace `Your Name` with a representative name of the person using the service. Dates are effective dates in `YYYY-MM-DD` format. A range includes both endpoints.

```sh
python -m fx_lag.bccr --date 2026-01-01 --name 'Your Name'
python -m fx_lag.bccr --start 2026-01-01 --end 2026-01-05 --name 'Your Name'
python -m fx_lag.bccr --date 2026-01-01 --name 'Your Name' --timeout 15
python -m fx_lag.bccr --help
```

Output is JSON on standard output; warnings/errors go to standard error. You can save successful results with `> rates.json`. An error can leave an empty redirected file: always check the exit code before consuming it (`echo $?` in Bash or `$LASTEXITCODE` in PowerShell).

Synthetic single-date example, **not live BCCR data**:

```json
{
  "observations": [
    {
      "source": "BCCR",
      "source_url": "https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx",
      "indicator": 317,
      "rate": "502.12000",
      "units": "CRC/USD",
      "effective_date": "2026-01-01",
      "retrieved_at": "2026-01-03T12:00:00Z"
    }
  ],
  "missing_dates": []
}
```

`rate` is a string to preserve decimal precision; use `Decimal(value)` in Python for calculations. `effective_date` comes from `DES_FECHA` and retains its calendar date, without inventing a timezone or publication time. `retrieved_at` is the UTC time when the response finished downloading. There is **no publication-time field** because the documented records do not supply one; midnight in `DES_FECHA` is not evidence of publication at midnight. Retrieval does not establish freshness.

Results are sorted by date. Partial ranges return available observations plus explicit `missing_dates` and a warning. Missing dates are never filled, carried forward or assigned zero; a missing date does not establish a market holiday. If all data is missing the command fails. Invalid records (including another indicator, nonpositive/nonfinite rates, invalid or out-of-range dates, or duplicate dates) fail the entire batch without printing partial observations.

Exit codes: **0** = a parsed nonempty result (inspect `missing_dates`); **1** = collection failure; **2** = invalid command-line syntax. Authentication failures mention subscription credentials; an empty response alone is not proof of invalid credentials. HTTP 401/403 may also reflect an intermediary access policy. Network/TLS/timeouts, HTTP failures, unexpected schemas, malformed XML and SOAP faults have clear errors. Error messages never echo the response body or credentials. TLS verification stays enabled; redirects are rejected to avoid forwarding credentials. There is a 30-second default socket timeout and 2 MB response limit; use a smaller range if the response is too large. There are no automatic retries, which avoids repeated credential/service failures.

## Offline validation

Run from the repository folder:

```sh
python -m unittest discover -s tests -v
```

No credentials or network are required. Fixtures are **synthetic**, not recorded authenticated responses. Mocks test request construction, SOAP and direct XML, dates/precision/provenance, missing observations, invalid values/XML, authentication faults, HTTP/network/read failures, redirects, size limits, argument validation and CLI output/exit codes.

## API assumptions still requiring verification

- SOAP 1.1 POST to the documented endpoint is assumed to accept action/namespace `http://ws.sdde.bccr.fi.cr/ObtenerIndicadoresEconomicosXML`, with fields `Indicador`, `FechaInicio`, `FechaFinal`, `Nombre`, `SubNiveles`, `CorreoElectronico`, `Token`. WSDL access failed; exact current names/action cannot be confirmed. Credentials are sent in the HTTPS request body, never query strings.
- The parser assumes records named `INGC011_CAT_INDICADORECONOMIC` with `COD_INDICADORINTERNO`, `DES_FECHA`, `NUM_VALOR`. SOAP escaped-XML results and direct XML are supported. The official guide describes field meanings, but these exact wire names and wrappers have not been validated against an authenticated response.
- Inclusive date boundaries, decimal-point values, one record per effective date, calendar-date interpretation, error text and no-data wrappers require real-response verification. Auth-related fault text uses a conservative keyword heuristic; a generic server error may not identify authentication specifically.
- Publication calendar/timezone, weekends/holidays, future effective dates, revisions, historical completeness, limits, supported range size, token lifecycle, current legacy availability, and replacement API access are unverified. The historical 17:30 next-day availability note is not a publication timestamp and is not used by the code.
- Data use and redistribution remain subject to institutional terms described in DATA_SOURCES.md; the repository's MIT license is for code, not a grant of rights to BCCR data.

Before calling the integration live-tested, supply credentials privately, obtain a successful authenticated response, reconcile a small date range against BCCR's official publication, and update these assumptions with the actual evidence. Never commit credentials or raw responses containing them.
