# =============================================================================
# install.ps1 — MT5 Bridge installer for Windows 10/11
# =============================================================================
# Run as Administrator. The script:
#   1. Verifies Python 3.12 is on PATH (links python.org installer if missing).
#   2. Creates a venv at .\.venv and installs the bridge package.
#   3. Generates a random BRIDGE_TOKEN and writes it to env (machine scope).
#   4. Downloads NSSM if missing and registers `MT5Bridge` as a Windows service.
#   5. Opens TCP/8500 inbound, restricted to a backend IP if you set
#      $BackendIP, otherwise to local subnet only.
#
# Usage:
#   .\install.ps1 -BackendIP 10.0.0.5
#   .\install.ps1 -BackendIP 10.0.0.5 -ServiceAccount NT_AUTHORITY\NetworkService
#
# Re-run is safe — services / firewall rules are upserted.
# =============================================================================

param(
    [string]$BackendIP = "",
    [string]$ServiceAccount = "LocalSystem",
    [int]$Port = 8500,
    [string]$Mt5Path = ""
)

$ErrorActionPreference = "Stop"

function Assert-Admin {
    $current = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($current)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run as Administrator."
    }
}

function Resolve-Python312 {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        $ver = & $py.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($ver -eq "3.12") { return $py.Source }
    }
    # Look for the py launcher.
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $v = & $launcher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
            if ($v) { return $v.Trim() }
        } catch { }
    }
    throw "Python 3.12 not found. Download from https://www.python.org/downloads/release/python-3128/ and re-run."
}

function New-BridgeToken {
    $bytes = New-Object byte[] 48
    (New-Object Security.Cryptography.RNGCryptoServiceProvider).GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd("=")
}

function Set-MachineEnv($name, $value) {
    [Environment]::SetEnvironmentVariable($name, $value, [EnvironmentVariableTarget]::Machine)
}

function Get-MachineEnv($name) {
    return [Environment]::GetEnvironmentVariable($name, [EnvironmentVariableTarget]::Machine)
}

# ---------------------------------------------------------------------------
Assert-Admin

$Root = $PSScriptRoot
Set-Location $Root

Write-Host "[1/6] Resolving Python 3.12..."
$Python = Resolve-Python312
Write-Host "      using $Python"

Write-Host "[2/6] Creating venv at $Root\.venv ..."
if (-not (Test-Path "$Root\.venv")) {
    & $Python -m venv "$Root\.venv"
}
$Venv = "$Root\.venv\Scripts\python.exe"
& $Venv -m pip install --upgrade pip setuptools wheel
& $Venv -m pip install -e .

Write-Host "[3/6] Ensuring BRIDGE_TOKEN..."
$existing = Get-MachineEnv "BRIDGE_TOKEN"
if (-not $existing -or $existing.Length -lt 32) {
    $token = New-BridgeToken
    Set-MachineEnv "BRIDGE_TOKEN" $token
    Write-Host "      generated new BRIDGE_TOKEN (length $($token.Length))"
    Write-Host "      ----------------------------------------------------------"
    Write-Host "      SAVE THIS TOKEN — backend needs it as MT5_BRIDGE_TOKEN:"
    Write-Host "      $token"
    Write-Host "      ----------------------------------------------------------"
} else {
    Write-Host "      BRIDGE_TOKEN already set ($([math]::Min($existing.Length,8))+ chars)"
}

Set-MachineEnv "BRIDGE_BIND" "0.0.0.0:$Port"
if ($Mt5Path) {
    Set-MachineEnv "MT5_PATH" $Mt5Path
    Write-Host "      MT5_PATH = $Mt5Path"
}

Write-Host "[4/6] Installing NSSM..."
$Nssm = "$Root\tools\nssm.exe"
if (-not (Test-Path $Nssm)) {
    New-Item -ItemType Directory -Force -Path "$Root\tools" | Out-Null
    $Tmp = "$env:TEMP\nssm-2.24.zip"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $Tmp
    Expand-Archive -Path $Tmp -DestinationPath "$Root\tools\_nssm" -Force
    Copy-Item -Force "$Root\tools\_nssm\nssm-2.24\win64\nssm.exe" $Nssm
    Remove-Item -Recurse -Force "$Root\tools\_nssm"
    Remove-Item -Force $Tmp
}

Write-Host "[5/6] Registering Windows service MT5Bridge..."
& $Nssm stop MT5Bridge 2>$null | Out-Null
& $Nssm remove MT5Bridge confirm 2>$null | Out-Null
& $Nssm install MT5Bridge $Venv "-m" "mt5_bridge.server"
& $Nssm set MT5Bridge AppDirectory $Root
& $Nssm set MT5Bridge AppStdout "$Root\logs\bridge.out.log"
& $Nssm set MT5Bridge AppStderr "$Root\logs\bridge.err.log"
& $Nssm set MT5Bridge AppRotateFiles 1
& $Nssm set MT5Bridge AppRotateBytes 10485760
& $Nssm set MT5Bridge Start SERVICE_AUTO_START
& $Nssm set MT5Bridge ObjectName $ServiceAccount
New-Item -ItemType Directory -Force -Path "$Root\logs" | Out-Null
& $Nssm start MT5Bridge

Write-Host "[6/6] Configuring firewall..."
$RuleName = "MT5Bridge-In-$Port"
Remove-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($BackendIP) {
    New-NetFirewallRule -DisplayName $RuleName `
        -Direction Inbound -Protocol TCP -LocalPort $Port `
        -RemoteAddress $BackendIP -Action Allow | Out-Null
    Write-Host "      allowed $BackendIP -> :$Port"
} else {
    New-NetFirewallRule -DisplayName $RuleName `
        -Direction Inbound -Protocol TCP -LocalPort $Port `
        -RemoteAddress LocalSubnet -Action Allow | Out-Null
    Write-Host "      allowed LocalSubnet -> :$Port (no -BackendIP given)"
    Write-Host "      RECOMMENDED: re-run with -BackendIP <your backend IP> for tighter scope."
}

Write-Host ""
Write-Host "Done. Verify:"
Write-Host "   curl http://localhost:$Port/healthz"
Write-Host ""
Write-Host "Connect (replace placeholders):"
Write-Host '   curl -X POST -H "Authorization: Bearer <BRIDGE_TOKEN>" -H "Content-Type: application/json" \'
Write-Host "        -d '{\"server\":\"Exness-MT5Real8\",\"login\":1234567,\"password\":\"<password>\"}' \"
Write-Host "        http://localhost:$Port/connect"
