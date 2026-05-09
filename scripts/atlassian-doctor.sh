#!/usr/bin/env bash
set -euo pipefail

cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate
exec python atlassian_mcp_client.py --mode doctor --timeout 8 "$@"
