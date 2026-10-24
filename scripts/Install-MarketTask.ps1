# Registers a task only; does not execute a collection request now.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('monex', 'promerica')][string]$Source,
    [string]$PythonPath = '',
    [switch]$Disabled
)
$ErrorActionPreference = 'Stop'
try {
    if ((Get-TimeZone).Id -ne 'Central America Standard Time') {
        throw 'TimezoneMismatch'
    }
    $repository = Split-Path -Parent $PSScriptRoot
    $tokenFile = Join-Path $repository 'data\bccr-token.dpapi'
    if ($Source -eq 'monex' -and -not (Test-Path -LiteralPath $tokenFile -PathType Leaf)) { throw 'TokenNotConfigured' }
    if ([string]::IsNullOrWhiteSpace($PythonPath)) {
        $PythonPath = (& python -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
        if ($LASTEXITCODE -ne 0) { throw 'PythonNotFound' }
    }
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'PythonNotFound' }
    $PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
    if ($PythonPath.Contains('"') -or $PythonPath.Contains("`n") -or $PythonPath.Contains("`r")) { throw 'UnsafePath' }
    $runner = Join-Path $repository 'scripts\Run-MarketScheduled.ps1'
    if ($runner.Contains('"') -or $runner.Contains("`n") -or $runner.Contains("`r")) { throw 'UnsafePath' }
    $taskName = 'FX Lag Intelligence - ' + $Source.ToUpperInvariant()
    # Refuse to silently replace a task or its scheduling preferences.
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'ExistingTask' }
    $action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
        -Argument "-NoProfile -NonInteractive -File `"$runner`" -PythonPath `"$PythonPath`" -Source $Source" `
        -WorkingDirectory $repository
    $days = @('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')
    $triggers = @()
    # 09:00, 09:30, ..., 16:30, 17:00 = 17 weekday trigger times.
    for ($slot = 0; $slot -le 16; $slot++) {
        # Stagger after the BCCR task; final slot remains within the 60s grace.
        $offset = if ($Source -eq 'monex') { 45 } else { 20 }
        $at = (Get-Date).Date.AddHours(9).AddMinutes(30 * $slot).AddSeconds($offset)
        $triggers += New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $at
    }
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    # No StartWhenAvailable, restart-on-failure or wake timers: no catch-up requests.
    $task = New-ScheduledTask -Action $action -Trigger $triggers -Principal $principal -Settings $settings `
        -Description "$Source CSV collection: Mon-Fri 09:00-17:00 Costa Rica time; persistent HTTP 429 pause."
    if ($Disabled) { $task.Settings.Enabled = $false }
    Register-ScheduledTask -TaskName $taskName -InputObject $task | Out-Null
    Write-Output "Task registered: $taskName. Disabled: $Disabled. No request was executed by setup."
} catch {
    switch ($_.Exception.Message) {
        'TimezoneMismatch' { Write-Error 'Set the Windows timezone to Central America Standard Time (Costa Rica) before setup. This script does not change your timezone.' }
        'TokenNotConfigured' { Write-Error 'Run .\scripts\Set-BccrToken.ps1 first under this Windows user.' }
        'ExistingTask' { Write-Error 'This source task already exists. Inspect or remove it explicitly before reinstalling.' }
        default { Write-Error 'Task installation failed. Check PythonPath, Windows Task Scheduler permissions, paths and PowerShell execution policy.' }
    }
    exit 1
}
