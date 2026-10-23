[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$PythonPath)
$ErrorActionPreference = 'Stop'
$previousToken = $env:BCCR_SDDE_TOKEN
$exitCode = 1
try {
    if ((Get-TimeZone).Id -ne 'Central America Standard Time') { throw 'TimezoneMismatch' }
    $repository = Split-Path -Parent $PSScriptRoot
    $tokenFile = Join-Path $repository 'data\bccr-token.dpapi'
    $encrypted = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
    $secret = ConvertTo-SecureString -String $encrypted
    $credential = [System.Management.Automation.PSCredential]::new('bccr', $secret)
    $env:BCCR_SDDE_TOKEN = $credential.GetNetworkCredential().Password
    Push-Location -LiteralPath $repository
    try {
        # Paths, not credentials, appear in task arguments. No transcript/debug logs.
        & $PythonPath -m fx_lag.scheduled_bccr --data-dir (Join-Path $repository 'data')
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} catch {
    Write-Error 'Scheduled collection could not start. Check the Costa Rica Windows timezone, Python, repository location and protected token for this Windows user.'
    $exitCode = 1
} finally {
    $env:BCCR_SDDE_TOKEN = $previousToken
    Remove-Variable secret, encrypted, credential, previousToken -ErrorAction SilentlyContinue
}
exit $exitCode
