# Run as the same Windows user who will run the scheduled task.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
try {
    $repository = Split-Path -Parent $PSScriptRoot
    $data = Join-Path $repository 'data'
    New-Item -ItemType Directory -Path $data -Force | Out-Null
    $secret = Read-Host 'BCCR SDDE token (hidden)' -AsSecureString
    if ($secret.Length -eq 0) { throw 'Empty token' }
    $protectedToken = ConvertFrom-SecureString -SecureString $secret
    # Without -Key, Windows DPAPI protects this for this user/machine.
    Set-Content -LiteralPath (Join-Path $data 'bccr-token.dpapi') -Value $protectedToken -Encoding ASCII
    Write-Output 'Protected token saved locally. Do not commit or share the token file.'
} catch {
    Write-Error 'Could not save the protected token. Run this script under the Windows account that will run the task.'
    exit 1
} finally {
    Remove-Variable secret, protectedToken -ErrorAction SilentlyContinue
}
