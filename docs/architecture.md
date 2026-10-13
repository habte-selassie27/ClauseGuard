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
  leader_fn:   fetch every declared ref (web)
               -> any fetch failure: [EXTERNAL] (no record, retryable,
                  partial evidence is never judged)
               -> unusable page (< MIN_EVIDENCE_CHARS): all criteria unclear,
                  model skipped (outcome will be inconclusive)
               -> else prompt LLM -> parse+normalize -> per-criterion statuses
               returns: criteria + digest + per-ref provenance
               (open challenge grounds are included in the prompt)
  validator_fn: independently re-runs leader_fn, then compares via the
               deterministic equivalence rule; UserError is agreed only if
               reproduced, VMError / unexpected type / any internal error
               => disagree
  consensus:    agree => accepted result; disagree => protocol appeal/retry
        |
        v
canonicalize accepted result         [deterministic code: exact criterion ids,
                                      missing/duplicate/unknown -> unclear]
        |
        v
derive outcome + reason_code        [deterministic code, in the write method]
        |
        v
ComplianceRecord stored (round r); challenge (if any) resolved
```

## Storage model (GenLayer storage types only)

All persisted state uses GenLayer types — **no raw `dict`/`list` in storage**:

- `obligations: TreeMap[str, Obligation]` (includes `allow_any_https_source`)
- `submissions: TreeMap[str, Submission]`
- `records: TreeMap[str, ComplianceRecord]` — key `"<submission_id>:<round>"`
- `latest_record_key: TreeMap[str, str]`
- `num_rounds: TreeMap[str, u256]`
- `challenges: TreeMap[str, Challenge]` (includes `challenged_round`)
- `challenge_count: TreeMap[str, u256]`
- `next_obligation_num: u256`

`Obligation` / `Submission` / `ComplianceRecord` / `Challenge` are
`@allow_storage` dataclasses. Nested lists (criteria, evidence refs,
per-criterion results) are stored as JSON **strings** (the documented GenLayer
storage pattern) so the persisted model stays flat and robust.

Obligations are **immutable once evidence is submitted** — there is no edit
method; changing an obligation means creating a new one (new `obligation_id`).

## Evidence source handling

Two separate concerns, deliberately not conflated:

**1. URL syntax** (`_parse_https_url`, rejects rather than normalizes): scheme must
be `https://`; user-info, IPv6/IPv4 literals, ports other than `443`, trailing
dots, whitespace, empty authorities, single-label hosts, all-numeric labels, and
non-ASCII/malformed labels are all invalid.

**2. Source authorization** (per obligation, explicit and fail-closed): a
non-empty `trusted_hosts_json` allowlist (bare hostnames) **or** an explicit
`allow_any_https_source=true` opt-in — never both, never neither. Matching is
exact-host or explicit subdomain at a label boundary, so `example.com` does not
authorize `fakeexample.com`.

- Every evidence item stores its normalized **`host`** alongside `type`/`ref`, and
  duplicates are detected on the canonicalized URL, so provenance is auditable
  on-chain (`submission.evidence_json` and each `ComplianceRecord` carry it).
- Syntactic validity is still not authenticity — fetch content is treated as
  untrusted, normalized (trimmed), truncated deterministically, and only ever
  judged as data.

## Determinism boundary

- Everything outside the `gl.vm.run_nondet_unsafe` block is deterministic:
  validation, canonicalization, parsing/normalization, outcome derivation,
  storage writes.
- Only the leader/validator block touches the network and the LLM.
- The `leader_fn`/`validator_fn` closures capture **plain data only** (never
  `self`), so they are serializable by cloudpickle for post-execution.
- The validator never raises: a `UserError` is agreed only when independently
  reproduced, and a `VMError`, an unexpected result type, or any internal
  exception is a *disagree* (the pinned `run_nondet_unsafe` documents that it does
  not sandbox the validator, so the validator defends itself in code).
