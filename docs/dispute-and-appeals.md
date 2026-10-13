# Dispute handling and relation to GenLayer appeals

ClauseGuard has **two independent** dispute/appeal layers. They complement each
other; neither bypasses or re-implements the other.

## Layer 1 — Protocol-level (GenLayer, not in this contract)

GenLayer transactions follow a **decided → finalized** lifecycle:

- A write transaction is first **decided** by the leader + validators
  (post-execution consensus on the non-deterministic block).
- It becomes **finalized** after the protocol's challenge/finality window.
- Validators can **appeal** a transaction at the protocol level; the protocol
  re-runs/rotates accordingly.
- Storage reads can target the latest **decided** (`StorageView.LATEST_DECIDED`)
  or latest **finalized** (`StorageView.LATEST_FINALIZED`) state.

This machinery is entirely a property of the protocol. ClauseGuard neither
changes nor depends on its internals. A freshly **accepted/decided** result is
**not** treated as final by this contract or its docs — consumers must require
finality before acting on a payout.

## Layer 2 — Contract-level `ReviewChallenge` (this contract)

`ReviewChallenge` is a **content-level** dispute about *the compliance judgment
itself* — separate from whether the transaction executed correctly. It exists so a
party can contest the substantive assessment (e.g. "the evidence does not actually
cover troubleshooting") and obtain a **second, independent evaluation round**.

Flow:

1. **Open** — the obligation owner or obligor calls
   `open_challenge(submission_id, grounds)` on an **evaluated** submission.
   The submission moves `evaluated → challenged`.
2. **Re-evaluate** — `evaluate_submission` on a `challenged` submission runs the
   non-deterministic block again in a **new evaluation round**
   (`evaluation_round` increments). The leader/validators independently re-judge;
   the deterministic outcome derivation runs again.
3. **Grounds are used, not just stored** — before that round, every `open`
   challenge's `grounds` are collected and injected into the evaluation prompt as
   "REVIEW GROUNDS: re-check these specific points". The prompt tells the
   evaluator to treat them as arguments to weigh against the evidence, not as
   instructions (so a ground cannot force `met`). They are then written to the
   new round's `ComplianceRecord.review_grounds_json`, making the dispute trail
   auditable on-chain. A round with no open challenge records `[]`.
4. **Preserve history** — prior rounds are never overwritten;
   `get_record_history` returns all rounds. The `ComplianceRecord` for the new
   round becomes the latest.
5. **Resolve** — once a new record is written, any open challenge(s) for that
   submission are marked `resolved` and the submission returns to `evaluated`.

Constraints: a challenge requires an evaluated submission, a party caller, and is
bounded by `MAX_CHALLENGES_PER_SUBMISSION` (3). This bounds dispute spam.

## What `ReviewChallenge` is NOT

- It does **not** re-run or replace the protocol's appeal process.
- It does **not** let a party unilaterally overwrite a result — a challenge only
  triggers a fresh evaluation; the new outcome is again subject to leader/validator
  consensus under the same equivalence rule.
- It does **not** bypass finality: a challenge-driven re-evaluation is itself a new
  write transaction with its own decided→finalized lifecycle.

## Consumer guidance

- Treat `get_latest_record` as the current assessment; use
  `get_record_history` to see the dispute trail.
- Before acting on a result (e.g. releasing a milestone), wait for **finality** and
  check whether a challenge is open (`get_challenge`) or a later round supersedes
  an earlier one.
