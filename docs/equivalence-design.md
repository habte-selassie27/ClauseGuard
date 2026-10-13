# Equivalence design

This is the consensus-critical decision for ClauseGuard. It is implemented with a
**custom validator function** (`gl.vm.run_nondet_unsafe`), never `strict_eq` over
free-form text (the LLM output is non-deterministic prose/JSON).

## 1. What does the leader produce?

A **normalized, prose-free structure**, one entry per criterion:

```python
{"criteria": [{"id": "c1", "status": "met",    "required": True},
              {"id": "c2", "status": "unclear","required": False},
              {"id": "c3", "status": "not_met","required": True}]}
```

- `status` is exactly one of `met | not_met | unclear`.
- There is **no prose** and **no model-written outcome** in the consensus output.
- The overall outcome is **not** produced here — it is derived afterwards in
  deterministic code (Section "Evaluation rules" in the README).

This structure is calldata-encodable (`dict[str, list[dict]]` of str/bool), so it
survives the leader→validator calldata round-trip cleanly.

## 2. What does a validator check?

The validator **independently re-runs the same task** — it does **not** merely
inspect the leader's answer:

1. Re-fetch the same evidence URLs (its own web calls).
2. Run its own per-criterion LLM evaluation against the same obligation.
3. Parse/normalize its own output with the same defensive parser.
4. Derive its own outcome from its own per-criterion statuses.
5. Compare with the leader's result via the rule below.

This is genuine independent verification (rerun + independent derivation), not
leader-output-only validation.

## 3. What counts as equivalent?

Deterministic function `_equivalent(leader_result, validator_result, required_ids)`:

```
equivalent  ⇔  derived_outcome(leader)   == derived_outcome(validator)
          AND  every required criterion status is equal
```

- **Every required criterion status must match exactly.** Any disagreement on a
  required criterion → not equivalent.
- **Non-required criteria are not compared** — they cannot affect the derived
  outcome, so a validator *tolerates* differences (including definite-vs-`unclear`)
  on optional criteria.
- **Derived outcomes must match** is enforced explicitly as a guard (it is implied
  by matching required statuses, but checked directly for clarity and safety).

Borderline definite-vs-`unclear` splits on **required** criteria are **not**
tolerated locally: the derived outcomes differ, so the validator votes *disagree*
and GenLayer's consensus/appeal machinery resolves it. ClauseGuard never
overrides consensus locally.

## 4. What happens on disagreement or failure?

- **Evidence unreachable / empty** → the leader raises `[EXTERNAL]`. The validator
  independently tries to fetch; if it also fails with the same deterministic
  message, they agree and the leader's error propagates — **no record is written**
  and the submission stays `submitted` (retryable).
- **Unusable model output** → `[LLM_ERROR]` (unparseable, or non-dict, or missing
  `criteria`). Disagreement forces a retry/leader rotation; it never locks bad
  state.
- **Validators disagree** (on values) → the validator returns `False` → GenLayer
  consensus fails → the protocol handles rotation/appeal. The contract does not
  locally override.

The validator never raises on the happy path; on any unexpected internal error it
returns `False` (disagree), which the protocol treats as "cannot verify".

## Why this shape (and not `prompt_comparative` / `strict_eq`)

- `strict_eq` on LLM output always fails consensus (non-deterministic prose).
- `prompt_comparative` would re-judge via NLP, but our equivalence rule is already
  **exactly expressible in code** (outcome + required statuses), so a custom
  validator is cheaper, more precise, and more auditable than an LLM comparison.
- The rule is stable because the leader output is normalized to enums — two
  agreeing evaluations produce **identical** structures, so genuine agreement is
  byte-identical, and only real disagreements diverge.
