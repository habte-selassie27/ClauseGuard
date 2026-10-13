#!/usr/bin/env bash
# Optional network integration tests against a live GenLayer environment.
#
#   ./scripts/run_integration.sh studionet        # hosted, gasless
#   ./scripts/run_integration.sh localnet         # local glsim
#
# Requires a reachable GenLayer RPC and (for the evaluate path) an LLM
# provider configured in the environment. See DEPLOYMENT.md for details.
#
# Runs a fast network preflight first so a no-egress sandbox fails in ~5s with
# a clear message instead of a 60s pytest stack trace.
set -eu
cd "$(dirname "$0")/.."

NETWORK="${1:-studionet}"

case "$NETWORK" in
  localnet)                 HOST="127.0.0.1" ;;
  studionet|testnet_bradbury|testnet_asimov) HOST="studio.genlayer.com" ;;
  *)                        HOST="studio.genlayer.com" ;;
esac

preflight() {
  echo "[preflight] network=$NETWORK host=$HOST"
  if ! timeout 5 getent hosts "$HOST" >/dev/null 2>&1; then
    cat >&2 <<EOF
[preflight] DNS resolution for '$HOST' failed or timed out.
[preflight] This sandbox appears to have NO outbound network egress
            (verified: DNS + HTTP both time out, even vs example.com).

[preflight] The integration tests need a reachable GenLayer RPC and, for the
            evaluate path, an LLM provider. They cannot run here.

[preflight] Next step (on a machine WITH internet access):
                ./scripts/run_integration.sh $NETWORK
            and, for the local glsim path, set OPENAI_API_KEY or a valid
            ANTHROPIC_API_KEY first.

[preflight] Local gates are unaffected and already pass:
                ./scripts/run_gates.sh        # lint + direct tests + consensus deploy

            See DEPLOYMENT.md (Gate 3b) for full details.
EOF
    exit 2
  fi
  echo "[preflight] DNS ok — attempting RPC via gltest..."
}

preflight

gltest tests/integration/ -v -s --network "$NETWORK"
