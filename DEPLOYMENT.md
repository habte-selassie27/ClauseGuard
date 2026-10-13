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
| 2 — direct tests | `pytest tests/direct/ -v` | **PASS** (32/32) | `proof/03_direct_tests.txt` |
| 3a — consensus deploy (offline GLSim) | `python3 scripts/glsim_consensus_deploy.py` | **PASS** (FINALIZED, leader + 5 validators agreed) | `proof/04_consensus_deploy_glsim.txt` |
| 3b — live-network integration | `gltest tests/integration/ --network <net>` | **BLOCKED** (environment — see below) | — |

Run them all with `./scripts/run_gates.sh`.

### Gate 3b — why it is blocked here (environment, not the contract)

The integration tests need a reachable GenLayer network whose validators can run a
**real LLM**. In this environment:

- **StudioNet RPC is down**: `eth_getTransactionByHash` returns a
  `502 Bad Gateway` (the hosted Studio gateway is unreachable).
- **GLSim (local) has no usable LLM provider**: `OPENAI_API_KEY` is unset and
  `ANTHROPIC_API_KEY` is a placeholder that returns `401`. Without a provider,
  `evaluate_submission`'s LLM call cannot execute on validators.
- **gltest↔GLSim schema RPC mismatch**: `gltest` sends the schema request with a
  named `code` param, but this GLSim build expects the code **positionally**
  (`params: [<code>]`), so `gltest` cannot build a typed client. This is a harness
  version quirk, independent of ClauseGuard (the contract itself loads and deploys
  cleanly — see the standalone proof and `tests/direct` which run against the real
  pinned SDK).

The contract's consensus logic (leader/validator equivalence) is directly
exercised in `tests/direct` via the captured validator (`run_validator`), and the
deploy path is proven under full consensus (Gate 3a).

### Exact commands to complete Gate 3b / deploy

Once a network + LLM are available:

```bash
# hosted, gasless StudioNet
./scripts/run_integration.sh studionet
# OR deploy manually:
genlayer network set studionet
genlayer deploy contracts/clause_guard.py            # (constructor takes no args)
genlayer schema <ADDRESS>
genlayer call <ADDRESS> get_obligation <OBLIGATION_ID>

# local GLSim with a real provider
pip install "gltest[sim]"
export OPENAI_API_KEY=sk-...            # or ANTHROPIC_API_KEY=...
glsim --port 4000 --validators 5 &
gltest tests/integration/ -v -s --network localnet

# funded testnets
genlayer network set testnet_bradbury   # or testnet_asimov
```

## Deployed address

- **Local GLSim (verified)**: full-consensus deploy finalizes successfully; the
  address is deterministic per run and recorded in
  `proof/04_consensus_deploy_glsim.txt`.
- **No public on-chain address is claimed** in this submission because live
  deployment (StudioNet/testnet) was not completed in this environment. Once
  deployed, record the address here and commit it to `artifacts/`.
