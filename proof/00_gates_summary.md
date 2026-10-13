# Gate evidence summary

Captured by `./scripts/run_gates.sh` (which now exits non-zero if any gate fails:
`pipefail` on every captured command plus an explicit verdict assertion on the lint
JSON). Interpreter: Python 3.12, `GENVM_VERSION=v0.2.12` (the SDK that matches the
contract's pinned runner `py-genlayer:1jb45aa8…`).

| Gate | File | Result |
|---|---|---|
| 1 — `genvm-lint check` | `01_lint_check.json` | **PASS** — `ok:true`, lint `ok`, validate `ok`, 12 methods (5 write / 7 view) |
| 1b — `genvm-lint schema` | `02_schema.json` | **PASS** — authoritative ABI (includes `allow_any_https_source: bool`) |
| 2 — direct tests | `03_direct_tests.txt` | **PASS** — 162/162 (core behaviour + security hardening) |
| 3a — GLSim consensus flow | `04_consensus_flow_glsim.txt` | **PASS** — `CONSENSUS_FLOW_OK`; deploy, register, source-policy rejections, submit, evaluate, challenge and re-evaluate all FINALIZED with 5/5 validators agreeing, including the nondeterministic rounds (the contract's own equivalence rule is re-run by every validator) |
| 3b — live-network integration (StudioNet) | `05_integration_collection_and_network.txt`, `06_integration_studionet.txt` | **PASS** — integration module collects cleanly (3 tests) and all 3 tests **PASS live on StudioNet**, including the full `register → submit → evaluate (real web + real LLM + leader/validator consensus) → read record` flow |
| 3b — deployed artifact inspection | `07_studionet_deploy_and_record.txt` | **PASS** — deployed code is byte-identical to `contracts/clause_guard.py`, the deployed ABI carries `allow_any_https_source: bool`, and a real record read shows the recorded outcome, digest and per-ref provenance |

Gate 3b ran live at address `0x8D9c54Ca588D9fd58486672Ef71A8D7695B69b0e`
(StudioNet, gasless). The nondeterministic `evaluate_submission` transaction
reached consensus with the real model and real web fetch, and the recorded outcome
was derived deterministically from the accepted per-criterion statuses.

Still unverified (needs a broader live sample, not a code change): how often a real
provider returns the exact JSON schema (schema violations surface as `[LLM_ERROR]`
and are retryable), real-page rendering for JS-heavy sites, redirect/error
semantics (the SDK exposes no HTTP status), IDN (punycode) hosts, and the tuning of
`MIN_EVIDENCE_CHARS` / char caps / challenge limits. See the README section
"Verified vs. to-confirm runtime assumptions".

The equivalence rule's failure modes (malformed leader results, required-criterion
disagreement, optional tolerance, validator exceptions) are covered in
`tests/direct` via the captured validator, and the full lifecycle is additionally
exercised under 5-validator consensus offline in Gate 3a.
