#!/usr/bin/env bash
# Optional network integration tests against a live GenLayer environment.
#
#   ./scripts/run_integration.sh studionet        # hosted, gasless
#   ./scripts/run_integration.sh localnet         # local glsim
#
# Requires a reachable GenLayer RPC and (for the evaluate path) an LLM
# provider configured in the environment. See DEPLOYMENT.md for details.
set -eu
cd "$(dirname "$0")/.."
NETWORK="${1:-studionet}"
gltest tests/integration/ -v -s --network "$NETWORK"
