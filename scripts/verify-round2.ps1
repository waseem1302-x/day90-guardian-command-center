[CmdletBinding()]
param(
  [string]$BackendUrl = 'http://127.0.0.1:8001',
  [string]$FrontendUrl = 'http://127.0.0.1:3001'
)

$ErrorActionPreference = 'Stop'

function Get-Json($url, $Method = 'Get') {
  (Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 -Method $Method $url).Content | ConvertFrom-Json
}

function Wait-ForEndpoint($url, $attempts = 12) {
  for ($attempt = 1; $attempt -le $attempts; $attempt++) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 $url
      if ($response.StatusCode -eq 200) { return }
    } catch {
      if ($attempt -eq $attempts) { throw }
    }
    Start-Sleep -Seconds 2
  }
  throw "Endpoint did not become ready: $url"
}

Write-Host 'Day90 Guardian Round 2 verification' -ForegroundColor Cyan
Wait-ForEndpoint "$BackendUrl/api/health"
$health = Get-Json "$BackendUrl/api/health"
$ready = Get-Json "$BackendUrl/api/ready"
if ($health.status -ne 'ok' -or $ready.status -ne 'ready') { throw 'Health/readiness check failed.' }
Write-Host 'PASS health/readiness'

$integrations = Get-Json "$BackendUrl/api/day90/integrations"
$secretFields = @($integrations.integrations | ForEach-Object { $_.safe_config.psobject.Properties | Where-Object { $_.Name -match 'KEY|TOKEN' } })
if (@($secretFields | Where-Object { $_.Value -notin @('configured', 'missing') }).Count -gt 0) { throw 'Integration endpoint exposed a secret fragment.' }
Write-Host ("PASS secret-safe integrations ({0} ready)" -f @($integrations.integrations | Where-Object status -eq 'ready').Count)

$trigger = Get-Json "$BackendUrl/api/day90/runs/trigger" 'Post'
if (@($trigger.external_actions).Count -ne 0 -or $trigger.message -notmatch 'approve') { throw 'Trigger bypassed the Workbench approval gate.' }
Write-Host 'PASS trigger is approval-gated'

$workbench = Get-Json "$BackendUrl/api/day90/workbench"
$routes = $workbench.cases | Group-Object route | ForEach-Object { "$($_.Name)=$($_.Count)" }
Write-Host ("PASS workbench cases: {0}" -f ($routes -join ', '))

$frontend = Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 $FrontendUrl
if ($frontend.StatusCode -ne 200) { throw 'Frontend health check failed.' }
Write-Host 'PASS frontend responds'

Write-Host 'Running container tests...' -ForegroundColor Yellow
docker compose exec backend pytest -q
if ($LASTEXITCODE -ne 0) { throw "Container tests failed with exit code $LASTEXITCODE." }
Write-Host 'All Round 2 checks passed.' -ForegroundColor Green
