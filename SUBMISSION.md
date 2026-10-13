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
| `tests/direct/` | 162 fast in-memory tests (real pinned SDK; web + LLM mocked). |
| `tests/integration/` | Live-network consensus tests (gltest; real LLM). |
| `scripts/` | `run_gates.sh`, `run_integration.sh`, `glsim_consensus_flow.py`. |
| `proof/` | Captured evidence for every gate that ran. |
| `docs/` | Architecture, equivalence design, evaluation rules, disputes, payments, threat model. |
| `artifacts/` | Generated ABI (`contract_schema.json`). |

## Gates and results

| Gate | Result | Evidence |
|---|---|---|
| 1 — `genvm-lint check` | **PASS** — `ok:true`, 12 methods (5 write, 7 view) | `proof/01_lint_check.json` |
| 1b — `genvm-lint schema` | **PASS** | `proof/02_schema.json` |
| 2 — direct tests | **PASS** — 162/162 | `proof/03_direct_tests.txt` |
| 3a — GLSim consensus flow | **PASS** — `CONSENSUS_FLOW_OK`; deploy, register, policy rejections, submit, evaluate, challenge, re-evaluate all FINALIZED with 5/5 validators agreeing (incl. the nondeterministic rounds) | `proof/04_consensus_flow_glsim.txt` |
| 3b — live-network integration | **PASS** — 3/3 tests live on StudioNet (94.89s), including register → submit → **evaluate with a real model and real web fetch under full leader/validator consensus** → read record | `proof/06_integration_studionet.txt` |
| 3b — deployed artifact inspection | **PASS** — deployed code byte-identical to the working tree (54 857 characters), ABI includes `allow_any_https_source`, live record read captured | `proof/07_studionet_deploy_and_record.txt` |

The gates script now fails loudly (`pipefail` + an explicit verdict assertion on
the lint JSON), so a passing exit code cannot hide a failing gate.

## Hardening changes in this revision

**Security / architecture**

- **Explicit, fail-closed source policy.** `register_obligation` takes
  `allow_any_https_source`; an empty allowlist is **rejected** instead of silently
  meaning "any host", and allowlist + opt-in together is rejected as ambiguous.
  Allowlist entries are validated as bare hostnames (no scheme/path/port/user-info/
  wildcard/trailing dot/single label) and deduplicated.
- **Strict URL parser.** `https://` only, no user-info, no IP literals, no port
  other than 443, no trailing dot, no whitespace or ambiguous authority, ASCII LDH
  labels with ≥ 2 labels. Ambiguity is rejected, never normalized away. URL
  *syntax* is a separate step from source *authorization*; neither claims
  authenticity.
- **Deterministic canonicalization before derivation.** The accepted leader result
  is re-shaped onto the obligation's criteria (missing/duplicated/unknown status →
  `unclear`, unknown ids dropped) and the outcome is derived only from that. An
  empty, malformed, duplicated, or unknown-enum result can no longer yield
  `satisfied` (`NO_VALID_EVALUATION` is reported instead).
- **Stricter consensus validation.** `_equivalent` requires both results to be
  well-formed against the obligation's **exact** criterion id set, plus matching
  derived outcomes and matching statuses on every required criterion. Malformed
  leader data, `VMError`, unknown result types, or any validator exception vote
  *disagree* — never a silent pass.
- **Schema violations are `[LLM_ERROR]`.** Unparseable output, wrong container type,
  or an entry without a string `id`/`status` now fails the round with no record
  rather than degrading to a vague `unclear`.
- **Evidence provenance & auditability.** Each round records per-ref
  `{ref, host, chars}`, a SHA-256 digest of the exact normalized evidence text the
  leader judged (semantics documented byte-for-byte), and `evidence_changed`
  relative to the previous round. Prior rounds are never overwritten. Missing
  retrieval timestamps/HTTP status are documented as SDK limitations rather than
  invented.
- **Challenge lifecycle.** Grounds must be non-blank and bounded; challenges record
  `challenged_round`; one open challenge at a time and max 3 per submission;
  closing an obligation no longer implies the dispute path is closed (verified).
- **No funds, ever** — unchanged: no transfer, balance, or value-bearing method.

**Tests** — a new adversarial suite (`tests/direct/test_security_hardening.py`)
covers URL/source security (user-info, ports, trailing dots, IP literals, label
and subdomain matching), evidence handling (counts, duplicates, partial fetch
failure, insufficient content, contradiction, injection, digest change),
consensus/malformed results, lifecycle transitions, and outcome derivation
(including “empty/malformed never satisfies”). The offline consensus gate
(`scripts/glsim_consensus_flow.py`) now drives the whole lifecycle through real
leader+validator consensus instead of a bare deploy.

## Key design commitments

- The **LLM only produces per-criterion judgments**; the overall outcome is
  **derived in deterministic code**.
- Consensus uses a **custom validator function**; validators **independently
  re-run the task** and compare via a documented deterministic rule.
- **Input validation runs before any LLM/web work**; cheap garbage is rejected
  with `[EXPECTED]`.
- **No positive judgment without evidence** — `min_evidence >= 1`, and an
  empty/unusable fetched page forces every criterion to `unclear` (model never
  called) → `inconclusive`.
- **Deterministic error prefixes** (`[EXPECTED]`, `[EXTERNAL]`, `[TRANSIENT]`,
  `[LLM_ERROR]`) with no timestamps or random ids.
- **Obligations immutable once registered**; no edit method.
- **GenLayer storage types only** (TreeMap / dataclass / sized ints / bool).
- **Prompt-injection stance enforced in code**, not only in prose.
- **No fund handling** in this contract; payment is a separate concern.

## Equivalence design (summary)

1. Leader → normalized `{criteria:[{id,status,required}], evidence_digest, evidence_chars, evidence_provenance}`.
2. Validator → independently re-runs fetch + LLM + parse, derives its own result.
3. Equivalent ⇔ both results are well-formed against the exact criterion id set,
   derived outcomes match, and every **required** criterion status matches
   (non-required tolerated; order- and alias-insensitive; malformed never passes).
4. Disagreement/failure → `[EXTERNAL]` (no record, retryable) / `[LLM_ERROR]` /
   protocol-level disagreement (never overridden locally).

## Deployed address (StudioNet) — official manual deployment

```
0x34c350cdf050137d773A855d12d7B44bF289aAa2
```

- Studio (import): https://studio.genlayer.com/?import-contract=0x34c350cdf050137d773A855d12d7B44bF289aAa2
- Explorer: https://explorer-studio.genlayer.com/address/0x34c350cdf050137d773A855d12d7B44bF289aAa2

Re-verified after deployment: `genlayer code` is content-identical to
`contracts/clause_guard.py` (54,872 bytes, sha256 `84c2bb24…`), and
`genlayer schema` matches `proof/02_schema.json` exactly (12 methods) — see
`proof/08_studionet_manual_deploy.txt`.

An earlier automated deploy of the same contract
(`0x8D9c54Ca588D9fd58486672Ef71A8D7695B69b0e`, by the integration suite) carried a
live evaluation: obligation requiring installation/configuration/troubleshooting
docs, evidence = `https://docs.python.org/3/tutorial/introduction.html` recorded
`not_satisfied` / `REQUIRED_CRITERION_NOT_MET`, `evaluation_round=0`,
`evidence_chars=4000` (per-ref cap applied) and a 64-hex `evidence_digest` — see
`proof/07_studionet_deploy_and_record.txt`.

## Reproduce

```bash
./scripts/run_gates.sh                   # all local gates → proof/ (fails loudly)
./scripts/run_integration.sh studionet   # live StudioNet (real web + real model)
```

See `DEPLOYMENT.md` for network setup and exact deploy commands, and
`docs/threat-model.md` for the threat model.
