# Weekday BCCR collection on Windows

This optional setup collects BCCR SDDE indicator 317 into `data/bccr-history.csv` every **30 minutes, Monday–Friday, 09:00 through 17:00 inclusive, Costa Rica time**. The times are 09:00, 09:30, …, 16:30, 17:00: at most 17 scheduled queries per weekday before errors or skips. There is no night/weekend collection or backfill of missed launches. Each run requests the **current Costa Rica effective date**, preserving each response's retrieval timestamp even if the rate is unchanged.

These hours are the owner's preference, **not a verified market calendar or BCCR publication window**. The owner already retrieved weekend-dated BCCR reference values. Data can be published or revised outside this collection window; the schedule may miss those changes. Holidays are not excluded unless they fall on a weekend. No schedule or alert can guarantee avoiding losses. BCCR reference compra is not a guaranteed executable Promerica quote.

**BCCR's numeric request limit and approved polling interval remain unconfirmed.** The owner selected this interval despite that open question. Handling HTTP 429 does not prove that 30-minute polling is officially permitted. No rate-limit probing is performed. No dip detection, notifications, database or predictions are included.

## What happens after HTTP 429

HTTP 429 (Too Many Requests) stops the scheduled collector for the rest of that day. It resumes no earlier than **09:00 the next weekday**:

- Monday–Thursday 429 → next weekday at 09:00.
- Friday 429 → Monday at 09:00.
- A longer valid `Retry-After` from the response takes precedence. Collection then waits for the first eligible scheduled slot after that deadline.

The pause is saved in `data/bccr-schedule.json`, so restarting Python, rebooting or reinstalling the task does not clear it. No immediate retries occur. Another 429 after resumption starts a new pause. Each 30-minute slot permits at most one attempt, including failed attempts, with a minimum 29-minute gap between actual attempts (one minute of scheduling-jitter tolerance around the half-hour target). A substantially delayed launch can therefore cause the next nominal slot to be skipped. Other API/authentication/network/CSV failures may try again at the next slot; they do not trigger a rapid retry loop.

Use the **scheduled runner** for automation. The standalone `python -m fx_lag.bccr_sdde` command does not read this schedule state; do not use manual queries or a different data directory to work around a 429 pause.

## Requirements and limitations

- Windows with Windows PowerShell 5.1 and Task Scheduler, plus Python 3.10 or newer.
- Be logged into the Windows account that creates the task, with the laptop **awake and online**. Locking the screen is okay; logging out, sleeping or shutting down can miss runs. The task does not wake the laptop and does not catch up missed runs.
- Windows timezone ID must be **`Central America Standard Time`** (Costa Rica, UTC−06:00). Installer and wrapper reject other timezone settings instead of changing your computer's clock. The Python guard independently uses UTC−06:00 year-round. If Costa Rica changes its timezone policy, the code must be updated.
- The repository must stay at the installed location. Reinstall if you move the repository, change Python paths, or change Windows timezone.
- These PowerShell scripts were reviewed against [Microsoft's task trigger documentation](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasktrigger) and [task principal documentation](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskprincipal). **Windows registration, DPAPI and scheduled execution have not been run in the Linux development environment. They require validation on your laptop.** The schedule/429 logic is covered by offline Python tests; no authenticated scheduled request was made here.

## Step-by-step setup

Run these from the repository folder in PowerShell, one step at a time. Review the scripts before execution. No administrator account or Windows password is requested; the task runs with your logged-in user's limited privileges. Managed Windows policies may require IT assistance.

1. Download this feature branch and run the complete tests:

   ```powershell
   git fetch origin
   git switch feat/bccr-weekday-scheduler
   python -m unittest discover -s tests -v
   ```

2. Check the timezone and Python:

   ```powershell
   Get-TimeZone | Select-Object Id, DisplayName
   python --version
   ```

   If the timezone is not `Central America Standard Time`, stop and choose the correct schedule/timezone configuration before installing. The scripts will not change your Windows timezone automatically.

3. Save a protected token for unattended execution:

   ```powershell
   .\scripts\Set-BccrToken.ps1
   ```

   Enter your legitimate SDDE token at the hidden prompt. Your earlier `$env:BCCR_SDDE_TOKEN` setting belongs to that terminal and is not reliable for Task Scheduler. The script stores a Windows DPAPI-protected value in `data/bccr-token.dpapi`; only the same Windows user/machine can normally decrypt it. A process running as you can still access it. Keep the file private; do not share it or commit it. `data/` and `*.dpapi` are ignored by Git. To rotate an expired token, rerun this step as the same user.

   The wrapper decrypts it only for the child process, sets `BCCR_SDDE_TOKEN` in that process environment, then restores the previous environment value. The token is not placed in task arguments, JSON state or output. No PowerShell transcript is enabled by these scripts.

4. Register the task:

   ```powershell
   .\scripts\Install-BccrTask.ps1
   ```

   This enables the requested schedule but **does not execute a query immediately**. It refuses to silently overwrite an existing task. To prepare a task without activating it, use `-Disabled` instead. If Python discovery fails, supply the full executable path with `-PythonPath 'C:\path\to\python.exe'`.

   If Windows blocks unsigned scripts, stop and share the sanitized policy error; do not disable organization policies or paste tokens into commands. Local trusted Git files and your Windows policy determine whether they can execute.

5. Inspect registration:

   ```powershell
   Get-ScheduledTask -TaskName 'FX Lag Intelligence - BCCR' | Select-Object TaskName, State
   Get-ScheduledTask -TaskName 'FX Lag Intelligence - BCCR' | Select-Object -ExpandProperty Triggers
   Get-ScheduledTaskInfo -TaskName 'FX Lag Intelligence - BCCR'
   ```

   There should be 17 weekly triggers, all Monday–Friday. The task uses the current user's interactive logon, ignores overlapping task instances, has a five-minute maximum execution time, and has no automatic restart or missed-trigger catch-up setting. No registration is claimed until these commands confirm it.

## Validate a scheduled run

During the chosen weekday window, you can start the registered task once:

```powershell
Start-ScheduledTask -TaskName 'FX Lag Intelligence - BCCR'
```

This is an actual collection attempt when eligible. It obeys the persisted pause and same-slot guard. Then inspect:

```powershell
Get-ScheduledTaskInfo -TaskName 'FX Lag Intelligence - BCCR'
Get-Content .\data\bccr-schedule.json
Import-Csv .\data\bccr-history.csv | Select-Object -Last 5 effective_date, rate, retrieved_at
```

`LastTaskResult` 0 means completed/safely skipped, 1 means a runner/startup/storage error, and 2 means a new HTTP 429 pause. Inspect the JSON state to distinguish saved observations from skips; a later paused trigger can exit 0 without a new query. The result field is meaningful only after the task finishes. Task Scheduler's History tab may need to be enabled for Windows operational history; no credentials should be included in shared screenshots.

The runner records the latest actual attempt (`last_attempt`, `last_slot`, `status`, `blocked_until`) in state; it is not a complete log of all failures. Outside-window, too-soon and already-attempted skips do not create observations or reset pause state. The CSV records successful observations only. `partial` and `error` statuses signal data health problems; there are no actionable notifications yet.

The final 17:00 launch has a one-minute grace (17:00:00 through 17:00:59). A launch after 17:01 is skipped. Delayed runs within the window use their current half-hour slot rather than backfilling earlier slots. Attempts never start before 09:00; a response already in flight may finish just after 17:00.

## Pause, remove and recover

Disable/enable future triggers without changing the 429 pause:

```powershell
Disable-ScheduledTask -TaskName 'FX Lag Intelligence - BCCR'
Enable-ScheduledTask -TaskName 'FX Lag Intelligence - BCCR'
```

Disabling triggers does not stop an in-flight request. To remove registration:

```powershell
Unregister-ScheduledTask -TaskName 'FX Lag Intelligence - BCCR' -Confirm
```

Keep `data/bccr-schedule.json` and the CSV when reinstalling. **Do not delete/edit the state or change data directories to bypass a cooldown.** Python and CSV writers use separate locks to prevent concurrent changes. A stale `data/bccr-schedule.lock`, corrupt state, or a `started` state left by an interrupted attempt stops collection rather than risking another request. After a forced process termination, the lock can remain, even across the next day; manual recovery is intentionally required.

For recovery, first disable the task, confirm no collection process is running, back up state/history, and inspect the error. Restore a trusted state that preserves any 429 deadline. If an interrupted attempt has unknown outcome, do not immediately reset it; determine a safe restart time before repairing state. Share sanitized status/errors for help, never the token or DPAPI file. Disk-write failures can leave a `.tmp` file. The runner persists `started` before contacting BCCR so failure to save a later 429 state remains fail-closed.

Use the same schedule state/CSV paths for every scheduled launch. The state/locks are intended for one local computer and cooperating processes, not shared network storage or protection against deliberate manual modification. Credential decryption and Windows task registration still need local end-to-end verification before claiming unattended operation works.
