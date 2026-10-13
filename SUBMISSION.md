# Submission — ClauseGuard

**ClauseGuard** is a reusable obligation-compliance primitive for GenLayer. A party
registers an obligation with explicit per-item acceptance criteria; the obligor
submits evidence; validators independently judge whether the evidence satisfies
**every** criterion; the contract records a deterministic outcome —
`satisfied` / `not_satisfied` / `inconclusive`. It **never moves funds**.

Scope: **contract + tests + evidence** (no frontend).

## What's here

| Path | Contents |
|---|---|
| `contracts/clause_guard.py` | The intelligent contract (pinned GenVM runner). |
| `tests/direct/` | 38 fast in-memory tests (real pinned SDK; web + LLM mocked). |
| `tests/integration/` | Live-network consensus tests (gltest; real LLM). |
| `scripts/` | `run_gates.sh`, `run_integration.sh`, `glsim_consensus_deploy.py`. |
| `proof/` | Captured evidence for every gate that ran. |
| `docs/` | Architecture, equivalence design, evaluation rules, disputes, payments. |
| `artifacts/` | Generated ABI (`contract_schema.json`). |

## Gates and results

| Gate | Result | Evidence |
|---|---|---|
| 1 — `genvm-lint check` | **PASS** — `ok:true`, 12 methods (5 write, 7 view) | `proof/01_lint_check.json` |
| 1b — `genvm-lint schema` | **PASS** | `proof/02_schema.json` |
| 2 — direct tests | **PASS** — 38/38 | `proof/03_direct_tests.txt` |
| 3a — GLSim consensus deploy | **PASS** — FINALIZED, leader + 5 validators agreed | `proof/04_consensus_deploy_glsim.txt` |
| 3b — live-network integration | **BLOCKED (no network egress)** — test module collects 3/3 cleanly; sandbox has no outbound DNS/HTTP (verified vs `example.com`); GLSim path also has no LLM key. Contract is not the cause (see `DEPLOYMENT.md`). | `proof/05_integration_collection_and_network.txt` |

## Key design commitments (per AGENTS.md)

- The **LLM only produces per-criterion judgments**; the overall outcome is
  **derived in deterministic code**.
- Consensus uses a **custom validator function**; validators **independently
  re-run the task** and compare via a documented deterministic rule
  (derived-outcome match + every required criterion status match; non-required
  criteria tolerated).
- **Input validation runs before any LLM/web work**; cheap garbage is rejected
  with `[EXPECTED]`.
- **No positive judgment without evidence** — `min_evidence >= 1`, and an
  empty/unusable fetched page forces every criterion to `unclear` (model never
  called) → `inconclusive`.
- **Evidence sources are hardened** — HTTPS-only refs, optional per-obligation
  trusted-host allowlist, and normalized `host` provenance recorded on every
  evidence item.
- **Challenge grounds are used** — injected into the re-evaluation prompt as
  review points and persisted on the new record (`review_grounds_json`).
- **Deterministic error prefixes** (`[EXPECTED]`, `[EXTERNAL]`, `[TRANSIENT]`,
  `[LLM_ERROR]`).
- **Obligations immutable once evidence is submitted**; no edit method.
- **GenLayer storage types only** (TreeMap / dataclass / sized ints); no raw
  dict/list in storage.
- **Defensive LLM handling + prompt-injection stance**; fetched evidence is
  untrusted and deterministically truncated.
- **No fund handling** in this contract; payment is a separate concern.

## Equivalence design (summary)

1. Leader → normalized `{criteria:[{id,status,required}]}` (no prose, no outcome).
2. Validator → independently re-runs fetch + LLM + parse, derives its own result.
3. Equivalent ⇔ derived outcomes match **and** every **required** criterion status
   matches (non-required tolerated).
4. Disagreement/failure → `[EXTERNAL]` (no record, retryable) / `[LLM_ERROR]` /
   protocol-level disagreement (never overridden locally).

## Reproduce

```bash
./scripts/run_gates.sh              # all local gates → proof/
./scripts/run_integration.sh studionet   # optional live network
```

See `DEPLOYMENT.md` for network setup and the exact commands to deploy.
