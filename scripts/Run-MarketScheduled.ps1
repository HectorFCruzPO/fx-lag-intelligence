[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [Parameter(Mandatory = $true)][ValidateSet('monex', 'promerica')][string]$Source
)
$ErrorActionPreference = 'Stop'
$previousToken = $env:BCCR_SDDE_TOKEN
$exitCode = 1
try {
    if ((Get-TimeZone).Id -ne 'Central America Standard Time') { throw 'TimezoneMismatch' }
    $repository = Split-Path -Parent $PSScriptRoot
    if ($Source -eq 'monex') {
        $tokenFile = Join-Path $repository 'data\bccr-token.dpapi'
        $encrypted = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
        $secret = ConvertTo-SecureString -String $encrypted
        $credential = [System.Management.Automation.PSCredential]::new('bccr', $secret)
        $env:BCCR_SDDE_TOKEN = $credential.GetNetworkCredential().Password
    } else {
        # Public-page collection has no need for the BCCR token.
        Remove-Item Env:BCCR_SDDE_TOKEN -ErrorAction SilentlyContinue
    }
    Push-Location -LiteralPath $repository
    try {
        # Paths, not credentials, appear in task arguments. No transcript/debug logs.
        & $PythonPath -m fx_lag.scheduled_bccr --source $Source --data-dir (Join-Path $repository 'data')
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
