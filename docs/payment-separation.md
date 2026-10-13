# Payment separation

**ClauseGuard never holds or transfers funds.** It records a compliance outcome
and nothing else. There is no balance logic, no transfer, no value-bearing
method in the contract.

## Why separation matters

A GenLayer transaction moves through **decided → finalized** and is appealable at
the protocol level. A freshly accepted result is **not** final. Wiring a payout
directly to a freshly accepted ClauseGuard result would risk paying out on a
judgment that is later appealed or reversed. ClauseGuard therefore exposes the
record as **data** and keeps all money movement out of scope.

## How to consume the result from a separate contract

ClauseGuard exposes read methods a separate contract can call:

- `get_latest_record(submission_id)` → the current outcome
- `get_record_history(submission_id)` → all rounds (dispute trail)
- `get_challenge(challenge_id)` → challenge status

A separate payout contract should:

1. **Require finality**, not mere acceptance — read the record at the finalized
   storage view and/or wait for the ClauseGuard transaction to be finalized before
   paying.
2. **Handle appeals** — if the compliance transaction can be appealed and reversed,
   the payout contract needs its own clawback/reversal path.
3. **Use independent, reliable transfer handling** — the payout contract owns its
   own balance/transfer logic, retries, and failure handling. ClauseGuard is not a
   payment primitive and does not guarantee transfer reliability.
4. **Gate on the derived outcome** — pay only on `outcome == "satisfied"`, and
   decide your own policy for `inconclusive` and `not_satisfied`.

## Non-goals

- ClauseGuard does not escrow, hold, or move GEN/native tokens.
- ClauseGuard does not emit transfer messages.
- ClauseGuard does not decide payout amounts or timing.

This separation is deliberate: **evaluation is not payment.**
