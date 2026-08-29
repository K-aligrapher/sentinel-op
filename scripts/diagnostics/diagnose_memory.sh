#!/bin/bash
# Read-only memory diagnostics for a pod. Runs inside the Daytona sandbox only.
set -euo pipefail
POD=${1:?need pod name}
NS=${2:-default}

kubectl top pod "$POD" -n "$NS" --no-headers 2>/dev/null || echo "top unavailable"
kubectl get pod "$POD" -n "$NS" -o jsonpath='{.spec.containers[0].resources}' | python3 -m json.tool
kubectl describe pod "$POD" -n "$NS" | grep -E "Limits:|Requests:|OOMKilled|Exit Code" || true
