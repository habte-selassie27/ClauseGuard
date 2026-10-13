# ClauseGuard

ClauseGuard is a reusable **obligation-compliance primitive** for
[GenLayer](https://docs.genlayer.com). A party registers an obligation with
explicit, per-item acceptance criteria. The obligor submits evidence against it.
Validators independently judge whether the evidence satisfies **every** criterion,
and the contract records a deterministic outcome — `satisfied`, `not_satisfied`,
or `inconclusive`. It records a compliance outcome and **never holds or transfers
funds**.

Example: an agreement requires documentation covering **installation**,
**configuration**, and **troubleshooting**. ClauseGuard evaluates the submitted
documentation against all three criteria, not just "a file exists".

Uses: milestone acceptance, SLAs, grant deliverables, performance-based
conditions.

Task classification: **contract only** (+ tests + evidence). No frontend.

---

## Contract API

Deployed class: `ClauseGuard`. All state-changing methods are writes; reads are
views. Errors use fixed, deterministic prefixes.

### Writes

| Method | Args | Returns | Notes |
|---|---|---|---|
| `register_obligation` | `description, obligor, criteria_json, min_evidence, max_evidence, allowed_types_json` | `obligation_id: str` | Caller becomes the owner. Validates all bounds. |
| `close_obligation` | `obligation_id` | — | Owner only. |
| `submit_evidence` | `obligation_id, evidence_json` | `submission_id: str` | Obligor only, obligation must be active. |
| `evaluate_submission` | `submission_id` | `outcome: str` | Runs the non-deterministic block; derives + stores the record. |
| `open_challenge` | `submission_id, grounds` | `challenge_id: str` | Owner or obligor; on an evaluated submission. |

### Views

| Method | Args | Returns |
|---|---|---|
| `get_obligation` | `obligation_id` | dict |
| `get_submission` | `submission_id` | dict |
| `get_challenge` | `challenge_id` | dict |
| `get_record` | `submission_id, evaluation_round` | dict |
| `get_latest_record` | `submission_id` | dict |
| `get_record_history` | `submission_id` | dict of round → record |
| `list_submissions` | `obligation_id, offset, limit` | list (paginated) |

### Input shapes (JSON strings — validated deterministically before any LLM/web work)

- `criteria_json`: `[{"id":"c1","text":"…","required":true}, …]` (1..20 items,
  unique ids, at least one `required`).
- `allowed_types_json`: `["documentation", …]`.
- `evidence_json`: `[{"type":"documentation","ref":"https://…"}, …]` (count in
  `[min_evidence, max_evidence]`, http(s) refs, no duplicates).

### Error prefixes (deterministic across validators)

- `[EXPECTED]` — bad input, unauthorized, closed obligation.
- `[EXTERNAL]` — web fetch failure (no record written; submission stays retryable).
- `[TRANSIENT]` — retryable external failure.
- `[LLM_ERROR]` — unusable model output.

No timestamps, random ids, or raw model prose appear in error strings.

---

## Evaluation rules (outcome derivation)

The LLM produces **per-criterion** judgments only (`met` / `not_met` /
`unclear`). The **overall outcome is derived deterministically in code**, never by
the model:

| Condition (over **required** criteria) | Outcome |
|---|---|
| any required criterion `unclear` | `inconclusive` |
| else any required criterion `not_met` | `not_satisfied` |
| else (all required `met`) | `satisfied` |

- **Non-required** criteria are recorded but never decide the outcome alone.
- **Mixed cases prefer the conservative `inconclusive`** (unclear wins over not_met).
- **Incomplete evidence** (below `min_evidence`, missing a required type) is
  rejected at submission (`[EXPECTED]`). Evidence that is present but
  insufficient → the model marks the criterion `unclear` → `inconclusive`.
- **Contradictory evidence** → the disputed criterion is `unclear` → `inconclusive`.
- **Ambiguous requirement** → `unclear` → `inconclusive`. The fix is a better
  obligation, not a guess.

A deterministic `reason_code` (`ALL_REQUIRED_MET`, `REQUIRED_CRITERION_NOT_MET`,
`REQUIRED_CRITERION_UNCLEAR`) is derived alongside the outcome.

---

## Equivalence design (the four answers)

Consensus uses a **custom validator function** (`gl.vm.run_nondet_unsafe`), never
`strict_eq` on free-form text.

**1. What does the leader produce?**
A normalized, prose-free structure: `{criteria: [{id, status, required}, …]}` —
one entry per criterion id, statuses from `{met, not_met, unclear}`. No prose in
the consensus-critical output. The overall outcome is derived afterwards in code.

**2. What does a validator check?**
The validator **independently re-runs the same task** (re-fetch the evidence, run
its own per-criterion LLM evaluation, parse/normalize) and compares against the
leader's result. Validators never trust the leader's answer alone.

**3. What counts as equivalent?**
Deterministic `_equivalent(leader, validator, required_ids)`:
- The **derived overall outcome** must match, **and**
- **Every required criterion status** must match exactly.
- Non-required criteria are **not** compared (they cannot affect the outcome), so a
  validator tolerates differences there.
- Any disagreement on a required criterion → not equivalent.

**4. What happens on disagreement or failure?**
- Evidence unreachable / empty → `[EXTERNAL]`; no record written; submission stays
  retryable.
- Unusable model output → `[LLM_ERROR]`.
- Validators disagree → GenLayer's consensus/appeal machinery handles it; the
  contract never overrides locally.

See `docs/equivalence-design.md` for the full design and `proof/` for captured
evidence.

---

## Handling of incomplete / contradictory / ambiguous evidence

- **Incomplete** — rejected deterministically at submission (count/type/URL), or
  judged `unclear` → `inconclusive`.
- **Contradictory** — the conflicting required criterion is `unclear` →
  `inconclusive` (conservative).
- **Ambiguous** — `unclear` → `inconclusive`; improve the obligation.
- **Prompt-injection stance** — fetched evidence is untrusted data. The prompt
  explicitly instructs the model to ignore instructions embedded in the evidence,
  and the output schema leaves injected text no way to fabricate a `satisfied`
  outcome (injected prose fails to parse → `LLM_ERROR`; only parsed per-criterion
  statuses count). Fetched text is deterministically truncated.

---

## Dispute flow and relation to GenLayer appeals

`ReviewChallenge` is a **contract-level** dispute path that **complements** (never
bypasses) GenLayer's protocol-level transaction appeals:

- A party (`open_challenge`) disputes an evaluated submission on stated grounds.
- A re-evaluation runs in a **new evaluation round** (`evaluation_round`
  increments); prior rounds are preserved (`get_record_history`).
- Challenges are bounded (`MAX_CHALLENGES_PER_SUBMISSION`) and must be on an
  evaluated submission.

Protocol-level: GenLayer transactions move through a **decided → finalized**
lifecycle; validators can appeal a transaction at the protocol level, and storage
reads can target `LATEST_DECIDED` vs `LATEST_FINALIZED`. That mechanism is
independent of, and unchanged by, `ReviewChallenge`. A freshly accepted result is
**not** presented as final — consumers should require finality.

See `docs/dispute-and-appeals.md`.

---

## Payment separation

ClauseGuard **never holds or transfers funds**. It exposes the compliance record
via read methods (`get_latest_record`, `get_record_history`) so a **separate**
contract can consume it. If a payout is wired to a result:

- require **finality**, not mere acceptance;
- handle protocol appeals;
- use independent, reliable transfer handling in that separate contract.

ClauseGuard does not move funds itself. See `docs/payment-separation.md`.

---

## How to run the gates

```bash
# everything (captures proof/)
./scripts/run_gates.sh

# individually
GENVM_VERSION=v0.2.12 genvm-lint check contracts/clause_guard.py --json
GENVM_VERSION=v0.2.12 genvm-lint schema contracts/clause_guard.py --json
pytest tests/direct/ -v
python3 scripts/glsim_consensus_deploy.py       # full-consensus deploy (offline)

# optional live-network integration
./scripts/run_integration.sh studionet
```

The contract pins a concrete GenVM runner (`# { "Depends": "py-genlayer:1jb45aa8…" }`);
never use `latest`/`test`. `GENVM_VERSION=v0.2.12` selects the matching SDK for
the linter and direct runner.

---

## Network + deployed address

- **Local (GLSim)**: full-consensus deploy verified — see
  `proof/04_consensus_deploy_glsim.txt` (address is deterministic-per-run).
- **StudioNet / testnets**: see `DEPLOYMENT.md` for current status and the exact
  commands to deploy. No committed on-chain address is claimed here because live
  deployment was not completed in this environment (see `DEPLOYMENT.md`).

---

## Worked example (installation / configuration / troubleshooting)

Obligation: *documentation covering installation, configuration and
troubleshooting*, all three criteria `required`.

**Passing submission** — evidence document describes all three. The model marks
`c1 met, c2 met, c3 met` → outcome **`satisfied`**
(`reason_code = ALL_REQUIRED_MET`).

**Failing submission** — the document covers installation and configuration but
**not** troubleshooting. The model marks `c1 met, c2 met, c3 not_met` → outcome
**`not_satisfied`** (`reason_code = REQUIRED_CRITERION_NOT_MET`). It is never
`satisfied` merely because "a file exists".

**Ambiguous submission** — the troubleshooting section is vague → `c3 unclear` →
outcome **`inconclusive`**.

These exact outcomes are exercised in `tests/direct/test_clause_guard.py`.

---

## Layout

```
contracts/clause_guard.py        the intelligent contract
tests/direct/                    fast in-memory tests (mock web + LLM)
tests/integration/               live-network consensus tests (gltest)
scripts/                         run_gates.sh, run_integration.sh, glsim_consensus_deploy.py
proof/                           captured gate evidence
docs/                            design notes (architecture, equivalence, rules, disputes, payments)
artifacts/                       generated schema / deploy artifacts
```
