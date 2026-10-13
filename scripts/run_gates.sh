#!/usr/bin/env bash
# Run all quality gates in order and capture evidence into proof/.
#   Gate 1  genvm-lint check   (lint + validate)
#   Gate 1b genvm-lint schema  (authoritative ABI)
#   Gate 2  pytest direct tests
#   Gate 3  glsim consensus deploy (offline)  [network integration optional]
set -u
cd "$(dirname "$0")/.."
export GENVM_VERSION="${GENVM_VERSION:-v0.2.12}"
# GenLayer tooling (genlayer-test / glsim / the pinned SDK) requires Python 3.12+
# (collections.abc.Buffer is 3.12+). Prefer python3.12.
PY="${PY:-python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
mkdir -p proof

echo "== Gate 1: genvm-lint check =="
genvm-lint check contracts/clause_guard.py --json | tee proof/01_lint_check.json
echo

echo "== Gate 1b: genvm-lint schema =="
genvm-lint schema contracts/clause_guard.py --json | tee proof/02_schema.json
echo

echo "== Gate 2: direct tests =="
"$PY" -m pytest tests/direct/ -v | tee proof/03_direct_tests.txt
echo

echo "== Gate 3a: glsim consensus deploy =="
"$PY" scripts/glsim_consensus_deploy.py | tee proof/04_consensus_deploy_glsim.txt
echo

# gltest clears artifacts/ on startup, so refresh the ABI artifact last.
mkdir -p artifacts
cp proof/02_schema.json artifacts/contract_schema.json

echo "All local gates executed. See proof/ for captured evidence."
