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

## Contents

- [Contract API](#contract-api)
- [Source authorization (explicit, fail-closed)](#source-authorization-explicit-fail-closed)
- [Evaluation rules (outcome derivation)](#evaluation-rules-outcome-derivation)
- [Evidence provenance and auditability](#evidence-provenance-and-auditability)
- [Equivalence design (the four answers)](#equivalence-design-the-four-answers)
- [Handling of incomplete / contradictory / ambiguous evidence](#handling-of-incomplete--contradictory--ambiguous-evidence)
- [Dispute flow and relation to GenLayer appeals](#dispute-flow-and-relation-to-genlayer-appeals)
- [Payment separation](#payment-separation)
- [Threat model](#threat-model)
- [Verified vs. to-confirm runtime assumptions](#verified-vs-to-confirm-runtime-assumptions)
- [How to run the gates](#how-to-run-the-gates)
- [Network + deployed address](#network--deployed-address)
- [Worked example](#worked-example-installation--configuration--troubleshooting)
- [Layout](#layout)

---

## Contract API

Deployed class: `ClauseGuard`. All state-changing methods are writes; reads are
views. Errors use fixed, deterministic prefixes.

### Writes

| Method | Args | Returns | Notes |
|---|---|---|---|
| `register_obligation` | `description, obligor, criteria_json, min_evidence, max_evidence, allowed_types_json, trusted_hosts_json, allow_any_https_source` | `obligation_id: str` | Caller becomes the owner. `min_evidence >= 1`. Source policy is explicit: a non-empty `trusted_hosts_json` **or** `allow_any_https_source=true` (never both, never neither). |
| `close_obligation` | `obligation_id` | — | Owner only. Stops new submissions; does not change criteria. |
| `submit_evidence` | `obligation_id, evidence_json` | `submission_id: str` | Obligor only, obligation must be active. **HTTPS-only**, strict URL syntax, trusted-host policy enforced, duplicates rejected after host normalization, host provenance recorded. |
| `evaluate_submission` | `submission_id` | `outcome: str` | Runs the non-deterministic block; derives + stores the record. Allowed only from `submitted` (first round) or `challenged` (review round). Permissionless trigger: evidence is frozen at submission time. |
| `open_challenge` | `submission_id, grounds` | `challenge_id: str` | Owner or obligor, on an evaluated submission, bounded by `MAX_CHALLENGES_PER_SUBMISSION = 3`, one open challenge at a time. |

### Views

| Method | Args | Returns |
|---|---|---|
| `get_obligation` | `obligation_id` | dict (incl. `trusted_hosts_json`, `allow_any_https_source`) |
| `get_submission` | `submission_id` | dict (evidence items carry their normalized `host`) |
| `get_challenge` | `challenge_id` | dict (incl. `challenged_round`) |
| `get_record` | `submission_id, evaluation_round` | dict |
| `get_latest_record` | `submission_id` | dict |
| `get_record_history` | `submission_id` | dict of round → record |
| `list_submissions` | `obligation_id, offset, limit` | list (paginated) |

A `ComplianceRecord` surfaces: `outcome`, `criteria_results_json`, `reason_code`,
`evaluation_round`, `evidence_json`, `review_grounds_json`, `evidence_digest`,
`evidence_chars`, `evidence_provenance_json`, `evidence_changed`.

### Input shapes (JSON strings — validated deterministically before any LLM/web work)

- `criteria_json`: `[{"id":"c1","text":"…","required":true}, …]` (1..20 items,
  unique ids, at least one `required`).
- `allowed_types_json`: `["documentation", …]`.
- `trusted_hosts_json`: `["docs.python.org", …]` — **bare** hostnames only
  (lowercase-normalized; no scheme, path, port, user-info, wildcard, trailing
  dot, or single-label entry). A ref host matches an entry when it is equal to it
  or a subdomain of it.
- `evidence_json`: `[{"type":"documentation","ref":"https://…"}, …]` (count in
  `[min_evidence, max_evidence]`, **https://** refs only, no duplicates).
  Each item stores its normalized `host` for provenance.

### Error prefixes (deterministic across validators)

- `[EXPECTED]` — bad input, unauthorized, closed obligation, invalid state.
- `[EXTERNAL]` — web fetch failure (no record written; submission stays retryable).
- `[TRANSIENT]` — retryable external failure.
- `[LLM_ERROR]` — unusable model output (schema violation, non-JSON, missing fields).

No timestamps, random ids, or raw model prose appear in error strings.

---

## Source authorization (explicit, fail-closed)

Evidence-source policy is a first-class, per-obligation decision, and there is no
silent default:

| `trusted_hosts_json` | `allow_any_https_source` | Result |
|---|---|---|
| non-empty | `false` | **High-assurance**: each ref host must equal an entry or be a subdomain of one. |
| `[]` | `false` | **Rejected** (`[EXPECTED] trusted_hosts must be non-empty…`). |
| non-empty | `true` | **Rejected** (`… must be empty when allow_any_https_source is true`) — no ambiguous policy state. |
| `[]` | `true` | Any well-formed https host (explicit opt-in, recorded on-chain). |

URL **syntax** validation is deliberately separate from source **authorization**:

- `[EXPECTED] evidence ref must be an https URL` — scheme is not `https://`.
- `[EXPECTED] evidence ref is not a well-formed https URL` — ambiguous authority.
- `[EXPECTED] evidence host not in trusted sources` — syntactically fine, but off-policy.

The parser is a conservative, pure-string check (no DNS, no `urllib`). It rejects
user-info (`user@host`), IPv6 and IPv4 literals, ports other than `443`,
trailing-dot hosts, whitespace, empty authorities, single-label hosts,
all-numeric labels, non-ASCII/malformed labels, and over-long hosts. Matching is
label-boundary exact, so `example.com` never authorizes `fakeexample.com` and
`example.com.evil.net` is not a subdomain of `example.com`.

**This is syntax and policy, not authenticity.** Passing it proves nothing about
the remote content; fetched bytes are treated as untrusted data (see
[threat model](docs/threat-model.md)).

---

## Evaluation rules (outcome derivation)

The LLM produces **per-criterion** judgments only (`met` / `not_met` /
`unclear`). The **overall outcome is derived deterministically in code**, never by
the model.

Before derivation, the accepted leader result is re-shaped in deterministic code
(**canonicalization**) onto the obligation's criteria: a missing, duplicated,
malformed, or unknown-status entry becomes `unclear`, and unknown criterion ids
are dropped. Derivation then runs on that canonical list:

| Condition (over **required** criteria) | Outcome | `reason_code` |
|---|---|---|
| empty/malformed result, or no required criterion evaluated | `inconclusive` | `NO_VALID_EVALUATION` |
| any required criterion `unclear` | `inconclusive` | `REQUIRED_CRITERION_UNCLEAR` |
| else any required criterion `not_met` | `not_satisfied` | `REQUIRED_CRITERION_NOT_MET` |
| else every required criterion `met` | `satisfied` | `ALL_REQUIRED_MET` |

- **Non-required** criteria are recorded but never decide the outcome alone.
- **Mixed cases prefer the conservative `inconclusive`** (unclear wins over not_met).
- Only three explicit `met` statuses on required criteria can ever produce
  `satisfied`; an unrecognized status is normalized to `unclear`, so malformed
  input cannot be laundered into a positive verdict.
- **Missing / unusable evidence can never be positive.** Evidence must be present
  at submission (`min_evidence >= 1`), and if the fetched pages contain fewer than
  `MIN_EVIDENCE_CHARS` usable characters, the contract **does not call the model at
  all** — every criterion is forced to `unclear` → `inconclusive`.
- **Incomplete evidence** (below `min_evidence`, missing an allowed type) is
  rejected at submission (`[EXPECTED]`). Evidence that is present but insufficient
  → `unclear` → `inconclusive`.
- **Contradictory evidence** → the disputed criterion is `unclear` → `inconclusive`.
- **Ambiguous requirement** → `unclear` → `inconclusive`. The fix is a better
  obligation, not a guess.

See `docs/evaluation-rules.md`.

---

## Evidence provenance and auditability

Every evaluation round records which evidence informed it:

- **Per-ref provenance** (`evidence_provenance_json`): `{ref, host, chars}` for
  each declared ref, in submission order — including `chars: 0` for refs that fell
  outside the truncation budget. `evidence_chars` is the total usable characters.
- **Content digest** (`evidence_digest`): SHA-256 hex of the exact
  **normalized evidence text the leader judged**. Precisely defined as: for each
  declared ref in submission order, the rendered text with leading/trailing
  whitespace stripped, truncated to `MAX_EVIDENCE_CHARS_PER_REF = 4000`, then to
  the remaining global budget (`MAX_EVIDENCE_CHARS_TOTAL = 12000`); the included
  pieces are joined with `"\n\n"` and hashed as UTF-8. Nothing else is hashed.
- **Change detection** (`evidence_changed`): `true` when a later round's digest
  differs from the previous round's. Earlier rounds are never overwritten
  (`get_record_history`), so a prior fingerprint cannot be silently replaced.
- **Review grounds** (`review_grounds_json`): the challenge grounds considered in
  that round (empty for rounds with no open challenge).
- **Criterion outcomes** (`criteria_results_json`) and the derived `outcome` /
  `reason_code`.

An evidence item is *inaccessible* only when the fetch fails, which aborts the
round as `[EXTERNAL]` with no record (retryable) — partial fetches are never
judged. Evidence that is retrieved but *insufficient* is distinguishable by
`chars` and yields `unclear` → `inconclusive`.

**Limitations (by design, not oversights):** the pinned SDK's
`gl.nondet.web.render` returns only rendered text — it exposes **no reliable
retrieval timestamp and no HTTP status**, so ClauseGuard records none rather than
inventing them. Validators independently re-fetch, so a mutable page can differ
byte-wise between the leader and a validator; equivalence is therefore defined on
*criteria judgments*, not on the digest, and the digest is recorded as
"what the leader judged", not as a claim of immutable external content.

---

## Equivalence design (the four answers)

Consensus uses a **custom validator function** (`gl.vm.run_nondet_unsafe`), never
`strict_eq` on free-form text.

**1. What does the leader produce?**
A normalized, prose-free structure: `{criteria: [{id, status, required}, …], evidence_digest, evidence_chars, evidence_provenance}`.
The consensus-critical part is `criteria`: exactly one entry per obligation
criterion id, statuses from `{met, not_met, unclear}`. No prose and no model-written
verdict. The overall outcome is derived afterwards in code.

**2. What does a validator check?**
The validator **independently re-runs the same task** — re-fetch the evidence, run
its own per-criterion LLM evaluation, parse/normalize with the same defensive
parser — and then compares the two results. It never trusts the leader's answer.

**3. What counts as equivalent?** — deterministic `_equivalent(leader, validator, criteria_meta)`:

- **Both** criteria lists must be well-formed against the obligation's **exact**
  criterion id set: a list of objects, each with a string `id` and a `status`
  field, no missing/duplicated/unknown ids. Malformed data is **never** equivalent.
- The **derived overall outcome** must match, **and**
- **Every required criterion status** must match exactly.
- Order is irrelevant and status aliases are normalized before comparison, so two
  agreeing evaluations always compare equal regardless of key order or wording.
- Non-required criteria are **not** compared (they cannot affect the outcome), so a
  validator tolerates differences there — including a definite-vs-`unclear` split.

**4. What happens on disagreement or failure?**

- Evidence unreachable → `[EXTERNAL]`; no record written; submission stays
  retryable.
- Unusable model output (non-JSON, wrong shape, entry without `id`/`status`) →
  `[LLM_ERROR]`; no record.
- Validators disagree → the protocol handles rotation/appeal; the contract never
  overrides locally. A validator that hits an unexpected shape or exception
  returns *disagree*, which is treated as "cannot verify".

See `docs/equivalence-design.md`.

---

## Handling of incomplete / contradictory / ambiguous evidence

| Situation | Handling |
|---|---|
| Incomplete (too few items, disallowed type, duplicate, off-policy or malformed URL) | Rejected deterministically at submission with `[EXPECTED]`. |
| Inaccessible (fetch fails, any ref) | Whole round aborts `[EXTERNAL]`, no record, retryable — never judged on partial evidence. |
| Retrieved but insufficient (< `MIN_EVIDENCE_CHARS`, or model says `unclear`) | `unclear` → `inconclusive`. |
| Contradictory sources | Disputed required criterion `unclear` → `inconclusive`. |
| Ambiguous requirement text | `unclear` → `inconclusive`; improve the obligation. |
| Model output that violates the schema | `[LLM_ERROR]`, no record. |
| Prompt injection in evidence or grounds | Ignored as data; cannot alter criteria, statuses, or the derivation. |

---

## Dispute flow and relation to GenLayer appeals

`ReviewChallenge` is a **contract-level** dispute path that **complements** (never
bypasses) GenLayer's protocol-level transaction appeals:

- A party (`open_challenge`) disputes an evaluated submission on stated grounds
  (bounded, non-blank, ≤ 1000 chars, max 3 per submission, one open at a time).
  The challenge records the `challenged_round` it disputes.
- The stored **grounds are actually used**: on the next `evaluate_submission` the
  open grounds are injected into the evaluation prompt as review points to weigh
  (framed so they cannot override the criteria), then persisted on the new
  `ComplianceRecord` as `review_grounds_json`.
- A re-evaluation runs in a **new evaluation round** (`evaluation_round`
  increments); prior rounds are preserved (`get_record_history`), and any open
  challenge is marked `resolved` only after the new record is written.
- A challenge can never *set* an outcome: the new verdict is derived by the same
  deterministic rule from a fresh, consensus-validated evaluation.
- Closing an obligation stops new submissions but does **not** moot a dispute.

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

## Threat model

Summary — the full table lives in [`docs/threat-model.md`](docs/threat-model.md):

- **Malicious submitter** — bounded counts/lengths, strict URL syntax, explicit
  host allowlist, duplicate rejection, no obligation mutation after registration,
  no fund handling in this contract.
- **Challenge abuse** — party-only, evaluated-only, one open challenge at a time,
  hard limit of 3 per submission, bounded grounds; a challenge cannot force an
  outcome.
- **Prompt injection** (evidence, criterion-adjacent text, grounds, fetched page) —
  untrusted-data framing, an output schema the injected text cannot satisfy, strict
  post-parse validation, canonicalization, and a deterministic derivation that
  ignores any model-written verdict or extra keys.
- **Unreliable external evidence** — any fetch failure fails closed (`[EXTERNAL]`,
  retryable, no record); retrieved-but-insufficient content cannot be positive;
  validators re-fetch independently.
- **Malformed model output** — `[LLM_ERROR]` and no record; unknown statuses →
  `unclear`; the outcome can never be `satisfied` from malformed input.
- **Consensus disagreement** — strict equivalence rule (exact id set, required
  statuses, derived outcome); malformed or unverifiable results vote *disagree*;
  the contract never overrides consensus locally.

---

## Verified vs. to-confirm runtime assumptions

Verified against the **pinned SDK** (`py-genlayer:1jb45aa8…`, GenVM `v0.2.12`)
source in this environment, and exercised by the gates:

| API | Verified behaviour |
|---|---|
| `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` | Leader runs with no args; the validator receives the leader `Result` (`Return[T] | VMError | UserError`); both are serialized with cloudpickle; on agreement the leader value is returned, on disagreement the VM terminates; a leader `UserError` propagates when the validator reproduces the same message. Docs note the validator is **not** sandboxed here — so the validator catches every exception and returns `False` (disagree) instead of raising. |
| `gl.vm.Return.calldata`, `gl.vm.UserError.message`, `gl.vm.VMError.message` | Confirmed dataclass fields; all three result kinds are handled explicitly. |
| `gl.nondet.exec_prompt(prompt, response_format="json")` | Declared `dict` for the json format, decoded through calldata; the parser defends against both `dict` and `str`. |
| `gl.nondet.web.render(url, mode="text")` | Keyword-only `mode`; returns rendered text (`str`). |
| `gl.message.sender_address`, `Address(str)`, `u256`, `TreeMap`, `@allow_storage`, `bool` fields | Confirmed; all validation and storage in the contract uses them. |
| Determinism boundary | No `gl.*` nondet calls outside the leader/validator closures; all comparison, canonicalization, derivation and storage are deterministic. |

Verified on a **live network with a real model** (StudioNet, `proof/06` / `proof/07`):

- The full `register → submit → evaluate → read record` flow passes with a real
  web fetch and a real model, reaching leader/validator consensus under the
  equivalence rule and recording a deterministic outcome.
- The deployed bytecode is identical to this source, and the recorded round states
  the evidence it judged (digest + per-ref provenance, with the per-ref char cap
  visibly applied: `evidence_chars = 4000`).

To confirm with a broader live sample (no code change implied):

- **Live model shape fidelity** — how often a real provider returns the exact JSON
  schema (schema violations become `[LLM_ERROR]` and are retryable, not wrong).
- **Real-world rendering** — whether JS-heavy pages regularly exceed
  `MIN_EVIDENCE_CHARS = 10` usable characters through `web.render`.
- **Redirect/error semantics** — the SDK exposes no HTTP status here, so every
  fetch problem maps to the single `[EXTERNAL]` class (no 404-vs-timeout split).
- **IDN evidence hosts** — non-ASCII labels are rejected; punycode (`xn--…`) is
  required and untested against real IDN sources.
- **Cost/latency** of `run_nondet_unsafe` versus the sandboxed `gl.vm.run_nondet`
  (which would catch validator errors for us at the price of an extra sandbox).
  The current choice is deliberate: the validator is fully defensive in code.
- **Threshold tuning** — `MIN_EVIDENCE_CHARS`, char caps, and challenge limits are
  policy heuristics chosen for safety, not measured optima.

---

## How to run the gates

```bash
# everything (captures proof/, fails loudly if any gate fails)
./scripts/run_gates.sh

# individually
GENVM_VERSION=v0.2.12 genvm-lint check contracts/clause_guard.py --json
GENVM_VERSION=v0.2.12 genvm-lint schema contracts/clause_guard.py --json
python3.12 -m pytest tests/direct/ -v                      # 162 tests
python3.12 scripts/glsim_consensus_flow.py                  # full-consensus flow (offline)

# optional live-network integration (needs network egress + an LLM provider)
./scripts/run_integration.sh studionet
```

The contract pins a concrete GenVM runner (`# { "Depends": "py-genlayer:1jb45aa8…" }`);
never use `latest`/`test`. `GENVM_VERSION=v0.2.12` selects the matching SDK for
the linter and the direct/glsim runners.`tests/direct/` covers URL and source security, evidence handling, consensus and
malformed-result handling, lifecycle transitions, and outcome derivation (mock web
+ LLM, real pinned SDK). `scripts/glsim_consensus_flow.py` additionally runs
deploy → register → submit → evaluate → challenge → re-evaluate under **5-validator
consensus**, with the contract's own equivalence rule re-run by every validator.
The live gate (`./scripts/run_integration.sh studionet`) runs the same flow against
StudioNet with a real model and real web fetch.

---

## Network + deployed address

- **StudioNet (official manual deployment, live, verified)**:

  ```
  0x34c350cdf050137d773A855d12d7B44bF289aAa2
  ```

  - Studio: https://studio.genlayer.com/?import-contract=0x34c350cdf050137d773A855d12d7B44bF289aAa2
  - Explorer: https://explorer-studio.genlayer.com/address/0x34c350cdf050137d773A855d12d7B44bF289aAa2

  Verified post-deploy: `genlayer code` is content-identical to
  `contracts/clause_guard.py` (54,872 bytes, sha256 `84c2bb24…`), the pinned
  `Depends` header is present, and `genlayer schema` matches
  `proof/02_schema.json` — 12 methods, all signatures identical. See
  `proof/08_studionet_manual_deploy.txt`.
- **StudioNet (earlier automated test deploy)** —
  `0x8D9c54Ca588D9fd58486672Ef71A8D7695B69b0e`. Deployed by the integration
  suite, which passed 3/3 (`proof/06`), and a
  live record read is captured in `proof/07`: obligation requiring
  installation/configuration/troubleshooting docs, evidence =
  `https://docs.python.org/3/tutorial/introduction.html` →
  `not_satisfied` / `REQUIRED_CRITERION_NOT_MET`, `evaluation_round=0`,
  `evidence_chars=4000`, 64-hex `evidence_digest`.
- **Local (GLSim)**: full-consensus lifecycle verified — see
  `proof/04_consensus_flow_glsim.txt` (address is deterministic per run).
- **Bradbury / Asimov**: not deployed; use `genlayer network set
  testnet_bradbury|testnet_asimov` with a funded account (see `DEPLOYMENT.md`).

---

## Worked example (installation / configuration / troubleshooting)

**Obligation** (high-assurance: explicit allowlist, no "any host" opt-in):

```python
register_obligation(
    description="Provide documentation covering installation, configuration and troubleshooting.",
    obligor="0x…obligor…",
    criteria_json='[{"id":"c1","text":"documents installation steps","required":true},'
                  '{"id":"c2","text":"documents configuration options","required":true},'
                  '{"id":"c3","text":"documents troubleshooting guidance","required":true}]',
    min_evidence=1,
    max_evidence=3,
    allowed_types_json='["documentation"]',
    trusted_hosts_json='["docs.python.org"]',   # bare hostname(s)
    allow_any_https_source=False,               # explicit: allowlist only
)
```

**Sample evidence refs** (submitted by the obligor):

```json
[
  {"type": "documentation", "ref": "https://docs.python.org/3/using/index.html"},
  {"type": "documentation", "ref": "https://docs.python.org/3/using/cmdline.html"}
]
```

Accepted refs must be well-formed `https://` URLs whose host is `docs.python.org`
or a subdomain of it; each stored item gains `"host": "docs.python.org"`.
`https://example.com/docs`, `https://docs.python.org.evil.net/x`, or
`https://docs.python.org./x` are all rejected at submission with `[EXPECTED]`.

**Example evaluation flow**

1. `submit_evidence(obligation_id, evidence_json)` → `submission_id` (state `submitted`).
2. `evaluate_submission(submission_id)` → leader fetches both refs, judges each
   criterion, returns normalized statuses + provenance + digest; every validator
   independently re-fetches and re-judges, then compares. The accepted result is
   canonicalized and the outcome derived.
3. `get_latest_record(submission_id)` → e.g. `outcome="not_satisfied"`,
   `reason_code="REQUIRED_CRITERION_NOT_MET"`, `criteria_results_json` showing
   `c1 met, c2 met, c3 not_met`, `evidence_provenance_json` with both refs and
   their usable char counts, and a 64-hex `evidence_digest`.
4. `open_challenge(submission_id, "the guide has since added a troubleshooting page")`
   → `challenge_id`, submission moves to `challenged`.
5. `evaluate_submission(submission_id)` → round 1, grounds injected into the
   prompt and persisted; new record (`evaluation_round=1`) with its own digest and
   `evidence_changed=true` if the page changed; the challenge is marked `resolved`.
6. `get_record_history(submission_id)` → `{"0": …, "1": …}` — the earlier verdict
   is preserved, never overwritten.

**Passing submission** — the document covers all three: `c1 met, c2 met, c3 met`
→ **`satisfied`** (`ALL_REQUIRED_MET`).

**Failing submission** — it covers installation and configuration but **not**
troubleshooting: `c3 not_met` → **`not_satisfied`** (`REQUIRED_CRITERION_NOT_MET`).
It is never `satisfied` merely because "a file exists".

**Ambiguous submission** — the troubleshooting section is vague: `c3 unclear` →
**`inconclusive`**.

**Real on-chain run** (StudioNet, `0x8D9c…9b0e`, `proof/07`): the same obligation
with a single evidence ref that documents neither installation, configuration nor
troubleshooting returned `c1/c2/c3 = not_met` and the contract recorded
`not_satisfied` / `REQUIRED_CRITERION_NOT_MET` in round 0 — with the evidence it
judged recorded as `evidence_chars = 4000` and
`evidence_digest = 86d00c7d9bf4fc392508248434d3a080b12a9465e6d4236913ca7a7573aea4b4`.

**Unreachable or empty evidence** — fetch failure → `[EXTERNAL]` (no record,
retryable); a successfully fetched but empty/whitespace page → every criterion
`unclear` → **`inconclusive`**, and the model is never called.

These outcomes are exercised in `tests/direct/` and in the consensus flow script.

---

## Layout

```
contracts/clause_guard.py              the intelligent contract
tests/direct/test_clause_guard.py      core behaviour (outcome table, parsing, lifecycle)
tests/direct/test_security_hardening.py URL/source policy, evidence, consensus, state, derivation
tests/integration/                     live-network consensus tests (gltest)
scripts/run_gates.sh                   lint + schema + direct tests + consensus flow
scripts/glsim_consensus_flow.py        offline 5-validator consensus lifecycle
scripts/run_integration.sh             optional live-network integration
proof/                                 captured gate evidence
docs/                                  architecture, equivalence, rules, disputes, payments, threat model
artifacts/                             generated schema / deploy artifacts
```
