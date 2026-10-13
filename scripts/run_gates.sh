#!/usr/bin/env bash
# Run all quality gates in order and capture evidence into proof/.
#   Gate 1  genvm-lint check   (lint + validate)
#   Gate 1b genvm-lint schema  (authoritative ABI)
#   Gate 2  pytest direct tests
#   Gate 3  glsim consensus flow (offline)  [network integration optional]
#
# Exits non-zero if any gate fails (pipefail + explicit status), so CI and
# reviewers cannot mistake a failing gate for a passing one.
set -u
set -o pipefail
cd "$(dirname "$0")/.."
export GENVM_VERSION="${GENVM_VERSION:-v0.2.12}"
# GenLayer tooling (genlayer-test / glsim / the pinned SDK) requires Python 3.12+
# (collections.abc.Buffer is 3.12+). Prefer python3.12.
PY="${PY:-python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
mkdir -p proof

status=0

echo "== Gate 1: genvm-lint check =="
genvm-lint check contracts/clause_guard.py --json | tee proof/01_lint_check.json || status=1
# The linter's exit code alone is not proof: assert the reported verdict too.
"$PY" -c '
import json, sys
data = json.load(open("proof/01_lint_check.json"))
ok = bool(data.get("ok")) and bool(data.get("lint", {}).get("ok")) and bool(data.get("validate", {}).get("ok"))
print("lint verdict: ok=%s methods=%s" % (ok, data.get("validate", {}).get("methods")))
sys.exit(0 if ok else 1)
' || status=1
echo

echo "== Gate 1b: genvm-lint schema =="
genvm-lint schema contracts/clause_guard.py --json | tee proof/02_schema.json || status=1
echo

echo "== Gate 2: direct tests =="
"$PY" -m pytest tests/direct/ -v | tee proof/03_direct_tests.txt || status=1
echo

echo "== Gate 3a: glsim consensus flow =="
"$PY" scripts/glsim_consensus_flow.py | tee proof/04_consensus_flow_glsim.txt || status=1
echo

# gltest clears artifacts/ on startup, so refresh the ABI artifact last.
mkdir -p artifacts
cp proof/02_schema.json artifacts/contract_schema.json

if [ "$status" -ne 0 ]; then
  echo "GATES FAILED — see the output above and proof/ for details."
  exit 1
fi
echo "All local gates executed and passed. See proof/ for captured evidence."
