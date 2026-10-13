# Evaluation rules (outcome derivation)

The LLM produces **per-criterion** judgments only. The **overall outcome is
derived in deterministic code** — never decided by the model.

## Normalized per-criterion status

Exactly one of:

- `met` — the evidence clearly satisfies the criterion.
- `not_met` — the evidence clearly lacks or contradicts it.
- `unclear` — the evidence is insufficient, ambiguous, missing, or
  self-contradictory (also the fallback for unknown/absent model statuses).

## Derivation table (over **required** criteria)

| Condition | Outcome | reason_code |
|---|---|---|
| any required criterion `unclear` | `inconclusive` | `REQUIRED_CRITERION_UNCLEAR` |
| else any required criterion `not_met` | `not_satisfied` | `REQUIRED_CRITERION_NOT_MET` |
| else (all required `met`) | `satisfied` | `ALL_REQUIRED_MET` |

- **Non-required** criteria are recorded but **never decide the outcome alone**.
- **Mixed cases prefer the conservative `inconclusive`**: if any required
  criterion is `unclear`, the result is `inconclusive` even when another required
  criterion is `not_met`. (Rationale: an unresolved required item means we cannot
  confidently assert failure either.)

## Special evidence situations

- **Incomplete evidence** — fewer than `min_evidence` items, a missing required
  type, a bad/duplicate URL, or oversize refs are rejected **deterministically at
  submission** (`[EXPECTED]`), before any LLM/web work. Evidence that is present
  but insufficient for a criterion → the model marks it `unclear` →
  `inconclusive` (never `not_satisfied` on absence alone).
- **Contradictory evidence** — sources that disagree on a **required** criterion →
  the criterion is `unclear` → `inconclusive`.
- **Ambiguous requirement** — an unclear/unverifiable requirement → `unclear` →
  `inconclusive`. The remedy is a better-written obligation, not a guess.
- **Non-required only failing** — an optional criterion that is `not_met` or
  `unclear` does **not** change a `satisfied` outcome.
- **Missing / unusable evidence (empty-evidence guard)** — two layers prevent a
  positive judgment without real content:
  1. `min_evidence >= 1` is enforced at registration, so an obligation can never
     be created that accepts zero evidence.
  2. If the fetched pages yield fewer than `MIN_EVIDENCE_CHARS` usable
     characters (empty/whitespace-only page), `leader_fn` **skips the model**
     and returns `unclear` for every criterion → `inconclusive`. A model primed
     to answer `met` is never reached, so it cannot fabricate `satisfied`.

## Defensive parsing (what the model returns never fully trusted)

- JSON requested via `exec_prompt(..., response_format="json")`, then sanitized:
  code fences stripped, first `{…}` block extracted, trailing commas repaired.
- Unknown statuses → `unclear`; missing criteria → `unclear`; unknown criterion
  ids → ignored; key aliases (`results`/`assessments`/…) accepted.
- Unparseable / non-dict / missing `criteria` → `[LLM_ERROR]`.
- Prompt-injection stance: evidence is framed as untrusted data, and injected
  prose cannot fabricate a `satisfied` outcome (it fails to parse, or only parsed
  per-criterion statuses count).

These rules are exercised by `tests/direct/test_clause_guard.py` (every row of the
table, parsing edge cases, and injection fixtures).
