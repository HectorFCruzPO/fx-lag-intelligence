# BCCR USD compra collector

The legacy collector requests **BCCR reference USD compra, indicator 317**, in CRC per USD. It is reference context, not an executable bank quote. It does not collect Promerica or MONEX data, store a database, run on a schedule, predict rates, or send alerts.

## Available collectors

- **SDDE REST adapter:** `python -m fx_lag.bccr_sdde`, using the separate `BCCR_SDDE_TOKEN` environment variable. Implemented and tested offline; see [SDDE setup, usage and live-validation limits](BCCR_SDDE.md).
- **Legacy SOAP prototype:** `python -m fx_lag.bccr`, retained intact for historical/testing purposes. Its setup is below. It is not the intended production integration.

The project owner shared successful authenticated SDDE single-date, weekday-range and weekend-range queries on 2026-10-23 and confirmed agreement of the range rates with BCCR's official history; see the [validation record](BCCR_SDDE.md#reported-live-query-2026-10-23). The legacy prototype remains unvalidated. The historical source review below predates that query.

## Status: legacy prototype, not a production integration

**The Python implementation works against offline fixtures and mocks. It is not a verified live integration.** BCCR announced retirement of the legacy Web Service for 2026-06-30. This collector targets that legacy service and is **not the intended production integration**. The separate SDDE adapter targets the officially documented replacement, but broader live validation is still required before production use.

| Capability | Evidence and limit |
| --- | --- |
| Legacy request construction, XML parsing and errors | Implemented and tested offline with synthetic fixtures; no real rates collected. |
| Legacy service retirement | Official announcement verified; actual shutdown not independently confirmed by an authenticated request. |
| Replacement SDDE API | Official technical documentation located and read; separate REST adapter tested offline; owner reported successful single-date, weekday-range and weekend-range queries, plus owner-reported reconciliation of the range rates with official history. |

### Confirmed official information (reviewed 2026-10-22)

[BCCR's own announcement on LinkedIn](https://es.linkedin.com/posts/banco-central-de-costa-rica_el-banco-central-de-costa-rica-informa-a-activity-7475548841979854848-q9oI) states that the Web Service would be disabled on **2026-06-30**, with subsequent access through an API. This confirms the announced policy and date, not an observed successful migration or shutdown.

The [official SDDE technical standard](https://gee.bccr.fi.cr/indicadoreseconomicos/Documentos/DocumentosMetodologiasNotasTecnicas/Estandar_API_SDDE.pdf) identifies the replacement interface:

- Base URL, section 1.3 (page 8): `https://apim.bccr.fi.cr/SDDE/api/Bccr.Ge.SDDE.Publico.Indicadores.API`.
- Indicator series: `GET` with suffix `/indicadoresEconomicos/{codigo}/series` (page 19). Required query parameters: `fechaInicio`, `fechaFin` (`yyyy/mm/dd`), and `idioma` (`ES` or `EN`).
- Indicator metadata: `GET` with suffix `/indicadoresEconomicos/{codigo}/metadata`, with `idioma` (page 17).
- Authentication: register on the Indicators site, generate a token under **Mi Perfil → Generar token**, and send `Authorization: Bearer <token>` (pages 4–8).

These are documented contracts, not verified live responses. The guide varies `Ge`/`GE` capitalization between its base URL and examples; the owner's later query succeeded with `Bccr.GE` (see the validation record). Other variants and case sensitivity remain unverified. Do not assume legacy subscription tokens work with SDDE. No replacement endpoint has been inferred from third-party code.

The [historical XML service guide](https://gee.bccr.fi.cr/indicadoreseconomicos/Documentos/DocumentosMetodologiasNotasTecnicas/Webservices_de_indicadores_economicos.pdf) documents indicator 317, subscription email/token, representative name, no sublevels and date ranges. This is evidence for the legacy prototype only.

### Inaccessible or unverified information

- The announcement's shortened guide link, `https://ow.ly/BaCr50ZfsCa`, was inaccessible through the research tool. The SDDE PDF above was located separately on BCCR's official domain; its identity as that shortened link's destination is unverified.
- The legacy [WSDL](https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx?WSDL) and [operation help page](https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx?op=ObtenerIndicadoresEconomicosXML) returned 503 through the web research tool, including on this review. A 503 does not prove retirement. Indexed copies are not successful current service requests.
- Shell Git access failed to connect to the configured proxy. This is an environment failure, not evidence about BCCR's API.
- **At the original 2026-10-22 review, neither interface had been authenticated in this environment.** The owner's later SDDE success is recorded separately above. Broader runtime availability, raw responses, historical completeness, current limits and token compatibility remain unverified.

## Legacy prototype setup (Python 3.10 or newer)

For offline tests, skip credentials and go directly to [offline validation](#offline-validation). The following credentials and request examples apply only to the legacy prototype, not SDDE. Do not register for a retired interface merely to run the tests.

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

## Legacy request examples: one date or a range

These commands demonstrate the implemented interface. They do not imply that the retired service is operational.

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

Exit codes: **0** = a parsed nonempty result (inspect `missing_dates`); **1** = collection failure; **2** = invalid command-line syntax. Authentication failures mention subscription credentials; an empty response alone is not proof of invalid credentials. HTTP 401/403 may also reflect an intermediary access policy. Network/TLS/timeouts, HTTP failures, unexpected schemas and malformed XML have clear errors. HTTP 500 SOAP faults retain sanitized request/service/authentication categories; unknown codes use a generic SOAP fault message. Classification uses only fault reason/code fields, never echoed request details. Non-SOAP or malformed HTTP 500 bodies remain HTTP failures even if they resemble valid rate data. Error messages never echo the response body or credentials. TLS verification stays enabled; redirects are rejected to avoid forwarding credentials. There is a 30-second default socket timeout and 2 MB response limit; use a smaller range if the response is too large. There are no automatic retries, which avoids repeated credential/service failures.

## Offline validation

Run from the repository folder:

```sh
python -m unittest discover -s tests -v
```

No credentials or network are required. Fixtures are **synthetic**, not recorded authenticated responses. Mocks test request construction, SOAP and direct XML, dates/precision/provenance, missing observations, invalid values/XML, authentication faults, HTTP/network/read failures, redirects, size limits, argument validation and CLI output/exit codes.

## Legacy API assumptions still requiring verification

- SOAP 1.1 POST to the documented endpoint is assumed to accept action/namespace `http://ws.sdde.bccr.fi.cr/ObtenerIndicadoresEconomicosXML`, with fields `Indicador`, `FechaInicio`, `FechaFinal`, `Nombre`, `SubNiveles`, `CorreoElectronico`, `Token`. WSDL access failed; exact current names/action cannot be confirmed. Credentials are sent in the HTTPS request body, never query strings.
- The parser assumes records named `INGC011_CAT_INDICADORECONOMIC` with `COD_INDICADORINTERNO`, `DES_FECHA`, `NUM_VALOR`. SOAP escaped-XML results and direct XML are supported. The official guide describes field meanings, but these exact wire names and wrappers have not been validated against an authenticated response.
- Inclusive date boundaries, decimal-point values, one record per effective date, calendar-date interpretation, error text and no-data wrappers require real-response verification. Auth-related fault reason text uses a keyword heuristic; detail payloads are ignored, and a generic server error may not identify authentication specifically.
- Publication calendar/timezone, weekends/holidays, future effective dates, revisions, historical completeness, limits, supported range size, token lifecycle, current legacy availability, and replacement API access are unverified. The historical 17:30 next-day availability note is not a publication timestamp and is not used by the code.
- Data use and redistribution remain subject to institutional terms described in DATA_SOURCES.md; the repository's MIT license is for code, not a grant of rights to BCCR data.

Owner-reported SDDE single-date, weekday-range and weekend-range queries succeeded, and the owner confirmed the range rates matched BCCR's official history. Before treating broader collection as validated, extend these checks to calendar edge cases and repeated operation; update assumptions with evidence. Never commit credentials or raw responses containing them.
