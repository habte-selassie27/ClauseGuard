# Evaluation rules (outcome derivation)

The LLM produces **per-criterion** judgments only. The **overall outcome is
derived in deterministic code** — never decided by the model.

## Normalized per-criterion status

Exactly one of:

- `met` — the evidence clearly satisfies the criterion.
- `not_met` — the evidence clearly lacks or contradicts it.
- `unclear` — the evidence is insufficient, ambiguous, missing, or
  self-contradictory (also the fallback for unknown/absent model statuses).

## Canonicalization (before derivation)

The result that consensus accepted is **never** fed to the derivation as-is. In
`_canonical_results` (deterministic code, never raises) it is re-shaped onto the
obligation's criteria:

- one entry per obligation criterion id, in obligation order;
- a **missing** criterion entry → `unclear`;
- a **duplicated** id → `unclear` (ambiguous judgment);
- an unknown status value (or a non-string status) → `unclear`;
- **unknown** criterion ids → dropped;
- a non-list / absent criteria value → *all* criteria `unclear`.

Derivation therefore only ever sees the obligation's ids and the three enums. An
empty, malformed, or duplicated result cannot be laundered into `satisfied`.

## Derivation table (over **required** criteria)

| Condition | Outcome | reason_code |
|---|---|---|
| empty/malformed result, or no required criterion evaluated | `inconclusive` | `NO_VALID_EVALUATION` |
| any required criterion `unclear` | `inconclusive` | `REQUIRED_CRITERION_UNCLEAR` |
| else any required criterion `not_met` | `not_satisfied` | `REQUIRED_CRITERION_NOT_MET` |
| else (all required `met`) | `satisfied` | `ALL_REQUIRED_MET` |

- **Non-required** criteria are recorded but **never decide the outcome alone**.
- **Mixed cases prefer the conservative `inconclusive`**: if any required
  criterion is `unclear`, the result is `inconclusive` even when another required
  criterion is `not_met`. (Rationale: an unresolved required item means we cannot
  confidently assert failure either.)
- Only explicit `met` statuses on required criteria can produce `satisfied`: the
derivation re-normalizes every status, and any value that is not one of the three
enums becomes `unclear`.

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
- Unknown statuses → `unclear`; missing criteria → `unclear`; duplicated ids →
  `unclear`; unknown criterion ids → ignored; key aliases (`results`/
  `assessments`/…) accepted.
- **Schema violations are `[LLM_ERROR]`** (and write no record): unparseable
  output, a non-object result, a missing criteria list, a recognizable key holding
  the wrong type, an entry that is not an object, and an entry without a string
  `id` or without a `status` field.
- Prompt-injection stance: evidence and review grounds are framed as untrusted
  data, the schema has no verdict field, and injected prose cannot fabricate a
  `satisfied` outcome (it fails to parse, or only parsed per-criterion statuses
  count, after canonicalization).

These rules are exercised by `tests/direct/test_clause_guard.py` and
`tests/direct/test_security_hardening.py` (every row of the table, parsing edge
cases, malformed-result matrix, and injection fixtures).
