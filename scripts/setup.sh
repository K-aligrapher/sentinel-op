#!/usr/bin/env bash
# Idempotent local scaffold: folders, virtualenv, dependencies, .env.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p agent/core agent/subagents agent/utils \
         config mcp skills scripts scripts/diagnostics \
         tools security session ui deploy deploy/k8s-manifests deploy/helm \
         tests/unit tests/integration tests/e2e \
         logs logs/approvals logs/archive docs .github/workflows
touch logs/.gitkeep

python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
pip install --upgrade pip
pip install -r requirements.txt

[ -f .env ] || cp .env.example .env
grep -qxF '.env' .gitignore || echo '.env' >> .gitignore

echo "✅ setup complete — edit .env, then: python -m agent.main"
