#!/usr/bin/env bash
# Local dev helper: wipe the studio database and all generated workspaces.
set -euo pipefail
cd "$(dirname "$0")/.."
pkill -f "uvicorn app.main:app" || true
pkill -f "generated_projects" || true
sleep 1
rm -rf generated_projects nexora.db
echo "reset complete"
