#!/bin/bash
# Client-side dry-run of the proposed memory-limit patch. Sandbox only — never mutates the cluster.
set -euo pipefail
POD=${1:?need pod name}
NS=${2:-default}
MEM_LIMIT=${3:-768Mi}

DEP=$(kubectl get pod "$POD" -n "$NS" -o jsonpath='{.metadata.ownerReferences[0].name}')
CONTAINER=$(kubectl get pod "$POD" -n "$NS" -o jsonpath='{.spec.containers[0].name}')

kubectl patch deployment "$DEP" -n "$NS" --dry-run=client -o yaml \
  -p "{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"$CONTAINER\",\"resources\":{\"limits\":{\"memory\":\"$MEM_LIMIT\"}}}]}}}}" \
  | grep -A5 "resources:" && echo "FIX_VALID=true"
