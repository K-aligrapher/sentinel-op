<#
.SYNOPSIS
  Stand up the full SENTINEL demo stack on Windows: Minikube + kube-prometheus-stack +
  a CrashLoopBackOff demo pod + the 3 MCP servers + TrueForge.

.DESCRIPTION
  Run from the sentinel/ directory with Docker Desktop running and .env filled in.
  Safe to re-run. Use -SkipInfra / -SkipMcp / -SkipTrueForge to do only parts.
#>
[CmdletBinding()]
param(
  [switch]$SkipInfra,
  [switch]$SkipMcp,
  [switch]$SkipTrueForge,
  [int]$MinikubeMemory = 4096,
  [int]$MinikubeCpus = 4
)

$ErrorActionPreference = "Stop"
function Step($m) { Write-Host ""; Write-Host "=== $m ===" -ForegroundColor Cyan }
function Need($cmd) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Warning "$cmd not on PATH - the step that uses it will likely fail. Open a fresh terminal or add its folder to PATH."
  }
}

# pick up a manual install in ~\tools even if this session's PATH is stale
$localTools = Join-Path $env:USERPROFILE "tools"
if ((Test-Path $localTools) -and (";$env:Path;" -notlike "*;$localTools;*")) { $env:Path += ";$localTools" }

# --- load .env into the process so $env:GITHUB_TOKEN etc. are available -------
if (Test-Path .env) {
  Get-Content .env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process")
  }
}

$scenario = Join-Path $env:TEMP "k8s-scenarios"
$issueYaml = Join-Path $scenario "scenarios\crashloopbackoff\issue.yaml"

Need docker

if (-not $SkipInfra) {
  Need minikube; Need kubectl; Need helm

  Step "Minikube"
  # $ErrorActionPreference=Stop + PS 5.1 turns any native-command stderr into a
  # terminating error, so probe commands must be wrapped in try/catch and judged
  # by exit code, never by whether they wrote to stderr.
  $mkRunning = $false
  try { $mkRunning = ((minikube status --format '{{.Host}}' 2>$null) -eq 'Running') } catch {}
  if (-not $mkRunning) {
    # --base-image without an @sha256 digest: skips minikube's remote digest check
    # against gcr.io, which hangs indefinitely here on "Pulling base image v0.0.50 ...".
    minikube start --memory=$MinikubeMemory --cpus=$MinikubeCpus --driver=docker `
      --base-image=gcr.io/k8s-minikube/kicbase:v0.0.50
  } else { Write-Host "already running" }
  kubectl cluster-info | Out-Host

  Step "kube-prometheus-stack (Helm)"
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>$null | Out-Null
  helm repo update 2>$null | Out-Null
  $promInstalled = $false
  try { helm status prometheus -n monitoring 2>$null | Out-Null; $promInstalled = ($LASTEXITCODE -eq 0) } catch {}
  if (-not $promInstalled) {
    helm install prometheus prometheus-community/kube-prometheus-stack --set alertmanager.enabled=true --set grafana.enabled=false --namespace monitoring --create-namespace
  } else { Write-Host "already installed" }

  Step "Prometheus port-forward :9090 (background job)"
  Get-Job -Name prom-pf -ErrorAction SilentlyContinue | Remove-Job -Force
  Start-Job -Name prom-pf -ScriptBlock {
    kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring
  } | Out-Null

  Step "CrashLoopBackOff demo pod"
  if (-not (Test-Path $scenario)) {
    git clone https://github.com/vellankikoti/troubleshoot-kubernetes-like-a-pro $scenario
  }
  kubectl apply -f $issueYaml
}

if (-not $SkipMcp) {
  Step "MCP servers (docker + npx)"
  try { docker rm -f k8s-mcp github-mcp 2>$null | Out-Null } catch {}
  docker run -d --name k8s-mcp -v "$HOME\.kube:/home/appuser/.kube:ro" -e K8S_MCP_TRANSPORT=streamable-http -p 8000:8000 ghcr.io/containers/kubernetes-mcp-server:latest | Out-Null
  docker run -d --name github-mcp -e "GITHUB_PERSONAL_ACCESS_TOKEN=$env:GITHUB_TOKEN" -p 8002:8080 ghcr.io/github/github-mcp-server:latest | Out-Null

  Get-Job -Name prom-mcp -ErrorAction SilentlyContinue | Remove-Job -Force
  Start-Job -Name prom-mcp -ScriptBlock {
    $env:PROMETHEUS_URL = "http://host.docker.internal:9090"
    & npx 'prometheus-mcp@latest' http --port 8001
  } | Out-Null

  Start-Sleep -Seconds 5
  python scripts\verify_mcp.py
}

if (-not $SkipTrueForge) {
  Step "TrueForge :8790 (background job)"
  Get-Job -Name trueforge -ErrorAction SilentlyContinue | Remove-Job -Force
  Start-Job -Name trueforge -ScriptBlock { & npx '@truefoundry/trueforge' } | Out-Null
  Write-Host "TrueForge starting. Open http://localhost:8790 then import config/, skills/, and config/mcp-connectors.yaml"
}

Step "Verify infra"
try { python scripts\verify_infra.py } catch { Write-Warning "verify_infra reported issues: $_" }

Step "Next"
Write-Host "1. TrueForge: add the Groq model, import config/agent.yaml, register config/mcp-connectors.yaml, import skills/, add the Daytona key."
Write-Host "2. Start the agent:   python -m agent.main"
Write-Host "3. Fire an incident:  python scripts\trigger_alert.py crashloop"
Write-Host "Background jobs: Get-Job   -   stop everything: .\scripts\stop_stack.ps1"
