<#
.SYNOPSIS
  Tear down what start_stack.ps1 created: background jobs, MCP containers, the demo pod.
  Leaves Minikube running unless -DeleteCluster is given.
#>
[CmdletBinding()]
param([switch]$DeleteCluster)

function Step($m) { Write-Host ""; Write-Host "=== $m ===" -ForegroundColor Cyan }

Step "Background jobs"
"prom-pf", "prom-mcp", "trueforge" | ForEach-Object {
  Get-Job -Name $_ -ErrorAction SilentlyContinue | Stop-Job -PassThru | Remove-Job -Force
}

Step "MCP containers"
docker rm -f k8s-mcp github-mcp 2>$null | Out-Null

Step "Demo workload"
$issueYaml = Join-Path $env:TEMP "k8s-scenarios\scenarios\crashloopbackoff\issue.yaml"
if ((Get-Command kubectl -ErrorAction SilentlyContinue) -and (Test-Path $issueYaml)) {
  kubectl delete -f $issueYaml --ignore-not-found 2>$null | Out-Null
}

if ($DeleteCluster) {
  Step "minikube delete"
  minikube delete
} else {
  Write-Host ""
  Write-Host "Minikube left running. Use -DeleteCluster to remove it."
}
