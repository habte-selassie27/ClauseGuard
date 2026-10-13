# Gate evidence summary

Captured by `./scripts/run_gates.sh`. Interpreter: Python 3.12, `GENVM_VERSION=v0.2.12`
(the SDK that matches the contract's pinned runner `py-genlayer:1jb45aa8…`).

| Gate | File | Result |
|---|---|---|
| 1 — `genvm-lint check` | `01_lint_check.json` | **PASS** — `ok:true`, lint `ok`, validate `ok`, 12 methods (5 write / 7 view) |
| 1b — `genvm-lint schema` | `02_schema.json` | **PASS** — authoritative ABI |
| 2 — direct tests | `03_direct_tests.txt` | **PASS** — 32/32 |
| 3a — GLSim consensus deploy | `04_consensus_deploy_glsim.txt` | **PASS** — FINALIZED, leader + 5 validators agreed, no error |

Gate 3b (live-network integration) is blocked by the environment, not the
contract — see `DEPLOYMENT.md` (StudioNet RPC 502; no GLSim LLM provider key;
gltest↔GLSim schema RPC param mismatch). The contract's consensus logic is
directly exercised in the direct tests via the captured validator (`run_validator`
→ agree / disagree / optional-tolerance), and the deploy path is proven under
full multi-validator consensus (Gate 3a).
