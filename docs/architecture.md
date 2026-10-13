# Architecture

## Boundary (who owns what)

**External sources own** the raw facts/documents. They are treated as untrusted:
validators re-fetch, normalize, and compare. A source is never trusted on faith.

**ClauseGuard (the contract) owns** the minimum state transition that needs
consensus:

- the structured obligation (criteria + evidence policy),
- evidence submissions,
- the non-deterministic evaluation (web fetch + LLM per-criterion judgment),
- the validator comparison (equivalence) rule,
- the deterministic outcome derivation + compliance record,
- a contract-level dispute path (ReviewChallenge).

**Frontends/backends own** UI, auth, indexing, non-authoritative previews, and
convenience analytics. They read the record; they do not decide it.

## State transition flow

```
user action (register / submit)      [deterministic write, validated first]
        |
        v
evidence submission recorded
        |
        v
evaluate_submission                 [non-deterministic block]
  leader_fn:   fetch evidence (web) -> prompt LLM -> parse+normalize ->
               per-criterion statuses only
  validator_fn: independently re-runs leader_fn, then compares via the
               deterministic equivalence rule
  consensus:    agree => agreed statuses; disagree => protocol appeal/retry
        |
        v
derive outcome + reason_code        [deterministic code, in the write method]
        |
        v
ComplianceRecord stored (round r); challenge (if any) resolved
```

## Storage model (GenLayer storage types only)

All persisted state uses GenLayer types — **no raw `dict`/`list` in storage**:

- `obligations: TreeMap[str, Obligation]`
- `submissions: TreeMap[str, Submission]`
- `records: TreeMap[str, ComplianceRecord]` — key `"<submission_id>:<round>"`
- `latest_record_key: TreeMap[str, str]`
- `num_rounds: TreeMap[str, u256]`
- `challenges: TreeMap[str, Challenge]`
- `challenge_count: TreeMap[str, u256]`
- `next_obligation_num: u256`

`Obligation` / `Submission` / `ComplianceRecord` / `Challenge` are
`@allow_storage` dataclasses. Nested lists (criteria, evidence refs,
per-criterion results) are stored as JSON **strings** (the documented GenLayer
storage pattern) so the persisted model stays flat and robust.

Obligations are **immutable once evidence is submitted** — there is no edit
method; changing an obligation means creating a new one (new `obligation_id`).

## Determinism boundary

- Everything outside the `gl.vm.run_nondet_unsafe` block is deterministic:
  validation, parsing/normalization, outcome derivation, storage writes.
- Only the leader/validator block touches the network and the LLM.
- The `leader_fn`/`validator_fn` closures capture **plain data only** (never
  `self`), so they are serializable by cloudpickle for post-execution.
