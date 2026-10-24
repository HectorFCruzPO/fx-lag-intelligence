# MONEX scheduling and Promerica public-rate observation

This feature adds optional Windows tasks for MONEX and Promerica, using the
owner-selected Monday–Friday 09:00–17:00 Costa Rica window and 30-minute slots.
No tasks are installed by fetching code or running tests. The existing BCCR task
name, credentials and triggers are preserved.

## What each task collects

| Task | Source | History |
| --- | --- | --- |
| FX Lag Intelligence - BCCR | SDDE reference compra, 317 | `data/bccr-history.csv` |
| FX Lag Intelligence - MONEX | SDDE closing average, 3323 | `data/monex-history.csv` |
| FX Lag Intelligence - PROMERICA | Public branch USD/CRC compra page | `data/promerica-history.csv` |

MONEX remains the daily closing series. Polling every 30 minutes can detect when
that day's closing value first becomes observable, but cannot turn it into an
intraday transaction feed. If today's value is missing, no previous-date value
is substituted or relabeled. Its state records an error; later eligible slots may
try again. The session statistic 3439 is not enabled.

Promerica uses the public branch rate even if the app differs, as the owner
requested. It reads one fixed public page with an identifiable User-Agent, no
login, cookies, Authorization header or private API. It executes no page scripts.
The parser requires the observed USD/CRC compra/venta labels and currency-price
cells before the accounting-reference boundary. It rejects absent, ambiguous or
changed layouts, invalid prices and all redirects. The accounting reference and
venta are not used as compra. UTF-8 HTML and two-decimal dot-formatted prices are
supported; other layouts/encodings fail rather than guessing.

The page supplied no verified effective date or publication time. JSON therefore
uses `effective_date: null` and CSV uses an empty date field. `retrieved_at` is UTC
observation time, not update time or proof of freshness. The shared CSV column
`indicator` contains local identity `promerica_branch_usd_compra` for this series;
it is **not a BCCR indicator code**. Each distinct retrieval is retained, including
unchanged prices. Incompatible histories are rejected rather than mixed.

## Public-page access decision and limitations

On 2026-10-24 the owner requested a way forward without waiting for a bank reply.
A direct public-page adapter was implemented for
[Promerica's branch-rate page](https://www.promerica.fi.cr/tipo-de-cambio-sucursales/).
The research tool could read its visible rate section. The current
[robots file](https://www.promerica.fi.cr/robots.txt) does not exclude that path;
it does exclude history URLs matching `seccion` and various script routes, which
this collector does not call. Robots guidance is not a license or confirmation
of a permitted polling rate.

No supported Promerica FX API, numeric request limit or automated-use entitlement
was verified. The linked terms PDF remained inaccessible through the research
tool. Bank silence is not permission. The owner selected the public-page approach
with these uncertainties recorded; the implementation does not require a bank
reply, change identity to evade a block, bypass access controls or infer an API.
Reassess terms/robots when they change. If access is rejected, stop and review.
No bank contact was made by the assistant.

**Validation status:** public content was read through the web research tool,
which may cache content. The new Python Promerica collector has synthetic HTML
fixtures and mocked HTTP tests, but its actual HTTP response/DOM has not yet been
validated locally against the live page. Do not enable its task until the manual
command below returns the correct branch compra. Linux shell access to bank hosts
is restricted and no authenticated BCCR token is available in development. MONEX
manual live success is documented in [MONEX_COLLECTOR.md](MONEX_COLLECTOR.md).
Neither new Windows task has been installed or executed in this environment.

## 1. Fetch the branch and run offline tests

From PowerShell in the repository folder:

```powershell
git fetch origin
git switch feat/market-schedules-public-promerica
python -W error::ResourceWarning -m unittest discover -s tests
```

Do not paste `PS C:\...>` prompts. Run one block at a time. Review the PR before
merging; install from your reviewed checkout. Use Python 3.10+ with no new packages.
The existing protected token is reused only by MONEX. No paid services are used.

## 2. Install MONEX's task

Windows must already use `Central America Standard Time`. The protected token
must exist for the current Windows user. Installation itself makes no request:

```powershell
.\scripts\Install-MarketTask.ps1 -Source monex
Get-ScheduledTaskInfo -TaskName 'FX Lag Intelligence - MONEX' | Select-Object NextRunTime, LastRunTime, LastTaskResult
```

The task polls 17 weekday slots at 09:00:45, 09:30:45, ..., 17:00:45, slightly
after the existing BCCR task. MONEX and BCCR use a shared exclusive API lock to
prevent concurrent requests. A long request may make the other task skip a slot;
there is no retry or catch-up. The final slot has only the existing 17:00–17:01
grace, so large launch delays may skip it. This is a polling preference, not a
publication calendar or confirmed quota. Adding MONEX increases BCCR requests to
up to 34 scheduled series queries per weekday across both tasks.

## 3. Validate Promerica manually

No token is required:

```powershell
python -m fx_lag.promerica --csv .\data\promerica-history.csv
```

Compare its `rate` with **Compra** under **USD / CRC** on the official branch
page at about the same time. Do not compare against Venta, Referencia contable,
BCCR 317 or your app quote. A match is a sample check, not a freshness guarantee.
If it fails, share the sanitized error; do not guess another endpoint, use a login
or repeatedly retry. The adapter may need an actual public HTML sample to revise
its currently synthetic layout assumptions.

## 4. Enable Promerica scheduling after a successful sample

```powershell
.\scripts\Install-MarketTask.ps1 -Source promerica
Get-ScheduledTaskInfo -TaskName 'FX Lag Intelligence - PROMERICA' | Select-Object NextRunTime, LastRunTime, LastTaskResult
```

It polls at 09:00:20, 09:30:20, ..., 17:00:20 on weekdays. To register either new
task without enabling it, add `-Disabled`. The installer refuses to replace an
existing task. Both tasks run as the current interactive Windows user without
administrator rights: the computer must be awake, online and the user logged in.
No wake, late catch-up, restart-on-failure or overnight/weekend triggers are added.
Holidays are not separately excluded. See [BCCR_SCHEDULER.md](BCCR_SCHEDULER.md)
for the existing Windows scheduling assumptions.

## Pause, errors and recovery

Each source has separate `data/<source>-schedule.json` and a schedule lock. State
is saved before a request, so an interrupted or corrupt state fails closed.
At most one attempt occurs per slot, with the existing 29-minute minimum between
attempts to tolerate trigger jitter. CSV saving remains atomic with sidecar locks.

An HTTP 429 persists a pause until the next weekday at 09:00 Costa Rica time,
or longer if Retry-After requires it. **BCCR and MONEX honor each other's persisted
pause**, because they share a token and provider; Promerica has its own pause.
A shared `data/sdde-schedule.lock` serializes BCCR/MONEX scheduled attempts. Manual
collectors do not share scheduler pauses: do not bypass a pause with manual calls.
There are no immediate automatic retries.

A Promerica HTTP 401/403 records `access_blocked` and stops future scheduled
requests across days. Do not switch User-Agents, endpoints or credentials to get
around it. Disable that task, review official access guidance and investigate
before resuming. Other transport/parser failures record `error` without adding
CSV rows. Missing source dates remain unknown, never filled from the clock.

Inspect local results:

```powershell
Get-Content .\data\monex-schedule.json
Get-Content .\data\promerica-schedule.json
Import-Csv .\data\promerica-history.csv | Select-Object -Last 5 rate, effective_date, retrieved_at
```

Stop a new task without touching BCCR:

```powershell
Disable-ScheduledTask -TaskName 'FX Lag Intelligence - MONEX'
Disable-ScheduledTask -TaskName 'FX Lag Intelligence - PROMERICA'
```

Only remove stale lock files after confirming no runner owns them. Back up state
before manual recovery and retain Retry-After pauses; never delete a state file
just to retry a blocked request. For `access_blocked`, leave the task disabled
until access has been resolved; then archive the reviewed state before a fresh
start. Local CSV, state, locks and protected credentials are ignored by Git.

No alert or financial decision is inferred from these samples. The next research
step is aligning observations with their actual availability and quantifying
sampling uncertainty, including unchanged and no-follow-through cases.
