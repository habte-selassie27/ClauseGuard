# Deployment

This document records the verified state of ClauseGuard, the commands to deploy it
to a live GenLayer network, and the current status of each quality gate.

## Contract pinning

The contract pins a concrete GenVM runner in its first line:

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

Never use `latest` or `test` — all public GenLayer networks reject unversioned or
aliased runners. `GENVM_VERSION=v0.2.12` selects the matching SDK for
`genvm-lint` and the direct test runner.

## Quality gates (status in this environment)

| Gate | Command | Status | Evidence |
|---|---|---|---|
| 1 — lint + validate | `genvm-lint check contracts/clause_guard.py --json` | **PASS** (`ok:true`, 12 methods) | `proof/01_lint_check.json` |
| 1b — schema (ABI) | `genvm-lint schema contracts/clause_guard.py --json` | **PASS** | `proof/02_schema.json`, `artifacts/contract_schema.json` |
| 2 — direct tests | `pytest tests/direct/ -v` | **PASS** (162/162) | `proof/03_direct_tests.txt` |
| 3a — consensus flow (offline GLSim) | `python3 scripts/glsim_consensus_flow.py` | **PASS** (`CONSENSUS_FLOW_OK`, every transaction FINALIZED with 5/5 validators agreeing, incl. the nondeterministic evaluate and re-evaluate rounds) | `proof/04_consensus_flow_glsim.txt` |
| 3b — live-network integration (StudioNet) | `./scripts/run_integration.sh studionet` | **PASS** — 3/3 tests live, including the full register → submit → evaluate (real web + real LLM + consensus) → read flow | `proof/05_integration_collection_and_network.txt`, `proof/06_integration_studionet.txt` |
| 3b — deployed artifact inspection | `genlayer code/schema/call <address>` | **PASS** — deployed code byte-identical to the working tree; ABI includes `allow_any_https_source`; real record read captured | `proof/07_studionet_deploy_and_record.txt` |

Run them all with `./scripts/run_gates.sh`.

### Gate 3b — result on live StudioNet

The integration tests need a reachable GenLayer network whose validators can run a
**real LLM**. That was available for this run:

- **StudioNet (live)**: `./scripts/run_integration.sh studionet` — **3 passed in
  94.89s** (`proof/06_integration_studionet.txt`). The full flow
  `register → submit → evaluate → read record` executed with the real web fetch and
  a real model, reached leader/validator consensus, and the contract recorded a
  deterministic outcome.
- **Deployed artifact verified**: `genlayer code <address>` from StudioNet is
  **byte-identical** to `contracts/clause_guard.py` (54 857 characters), the deployed ABI
  carries the new `allow_any_https_source: bool` parameter, and a live
  `get_latest_record` / `get_record_history` read shows the outcome, digest and
  per-ref provenance (`proof/07_studionet_deploy_and_record.txt`).
- **GLSim (local) live I/O has no usable LLM provider**: `OPENAI_API_KEY` is unset
  and `ANTHROPIC_API_KEY` is a placeholder that returns `401`. The offline Gate 3a
  consensus flow therefore serves web/LLM calls from deterministic in-process
  mocks, which proves multi-validator *agreement* (the property that matters for
  consensus).

What remains unverified is a *broader live sample* rather than a missing
capability: how often a real provider returns the exact JSON schema, real-page
rendering for JS-heavy sites, redirect/error semantics (the SDK exposes no HTTP
status), IDN hosts, and the tuning of `MIN_EVIDENCE_CHARS` / char caps / challenge
limits. See the README section "Verified vs. to-confirm runtime assumptions".

**Known harness quirk (unrelated to the contract)**: `gltest`'s typed-client
`deploy()` path sends the schema request with a named `code` param, while this
GLSim build expects the code positionally, so the integration module loads the
locally generated ABI (`proof/02_schema.json`) instead of fetching it from the
node. The contract itself deploys and executes cleanly on both GLSim and StudioNet
as the proofs show.

The contract's consensus logic (leader/validator equivalence) is directly
exercised in `tests/direct` via the captured validator (`run_validator`: agree /
disagree / optional-tolerance / malformed-leader matrix), and the **whole
lifecycle** — deploy, register, source-policy rejections, submit, evaluate,
challenge, re-evaluate — is proven under 5-validator consensus with the contract's
own equivalence rule re-run by every validator (Gate 3a,
`proof/04_consensus_flow_glsim.txt`). Only live-network reachability and a live
model provider remain unverified here.

### Exact commands to reproduce / deploy

```bash
# hosted, gasless StudioNet (this is what produced proof/06 and proof/07)
./scripts/run_integration.sh studionet
# OR deploy manually:
genlayer network set studionet
genlayer deploy contracts/clause_guard.py            # (constructor takes no args)
genlayer schema <ADDRESS>
genlayer call <ADDRESS> get_obligation --args <OBLIGATION_ID>

# local GLSim with a real provider
pip install "gltest[sim]"
export OPENAI_API_KEY=sk-...            # or ANTHROPIC_API_KEY=...
glsim --port 4000 --validators 5 &
gltest tests/integration/ -v -s --network localnet

# funded testnets
genlayer network set testnet_bradbury   # or testnet_asimov
```

## Deployed address

- **StudioNet — official manual deployment (live, verified)**:

  ```
  0x34c350cdf050137d773A855d12d7B44bF289aAa2
  ```

  - Studio (import): https://studio.genlayer.com/?import-contract=0x34c350cdf050137d773A855d12d7B44bF289aAa2
  - Explorer: https://explorer-studio.genlayer.com/address/0x34c350cdf050137d773A855d12d7B44bF289aAa2

  Deployed manually from `contracts/clause_guard.py` and re-verified afterwards:
  `genlayer code` is content-identical to the local contract (54,872 bytes,
  sha256 `84c2bb2475704363532d44affc96f7e41e9f4a8e436e01cb8d35c18318a9e395`),
  the pinned `Depends` header is intact, and `genlayer schema` matches
  `proof/02_schema.json` exactly (12 methods). Capture:
  `proof/08_studionet_manual_deploy.txt`.
- **StudioNet — earlier automated test deploy**:

  ```
  0x8D9c54Ca588D9fd58486672Ef71A8D7695B69b0e
  ```

  Deployed by `tests/integration/test_clause_guard.py` (gasless) and verified
  byte-identical to `contracts/clause_guard.py`; a live record read is captured in
  `proof/07_studionet_deploy_and_record.txt`. Redeploying produces a new address —
  the integration tests print it as `[studionet] ClauseGuard deployed at: …`.
- **Local GLSim (verified)**: the full-consensus lifecycle finalizes successfully;
  the address is deterministic per run and recorded in
  `proof/04_consensus_flow_glsim.txt`.
