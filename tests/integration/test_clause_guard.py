"""Integration tests — full leader+validator consensus against a live GenLayer
network (AGENTS.md Section 9.2).

Run with:
    ./scripts/run_integration.sh studionet     # hosted, gasless
    ./scripts/run_integration.sh localnet      # local glsim

These use the environment's REAL LLM (no mocks). They are intentionally kept
close to the deterministic surface so they are not flaky against a live model:
the consensus-critical assertions are (a) the transaction reaches consensus and
(b) the recorded outcome is a valid value. Subjective-outcome equality is
covered deterministically in tests/direct via the captured validator.
"""

import json
from pathlib import Path

import pytest
from gltest import get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded, tx_execution_failed
from gltest.contracts.contract import Contract
from gltest.utils import extract_contract_address

DEFAULT = get_default_account()

DOCS_CRITERIA = [
    {"id": "c1", "text": "documents installation steps", "required": True},
    {"id": "c2", "text": "documents configuration options", "required": True},
    {"id": "c3", "text": "documents troubleshooting guidance", "required": True},
]
DOCS_TYPES = ["documentation"]
DOCS_URL = "https://docs.python.org/3/tutorial/introduction.html"
# Explicit, non-empty trusted-source allowlist (no "any host" opt-in): the
# evidence URL below must match one of these entries.
DOCS_TRUSTED_HOSTS = ["docs.python.org"]
ALLOW_ANY_SOURCE = False

VALID_OUTCOMES = {"satisfied", "not_satisfied", "inconclusive"}


def _return_value(receipt):
    """Decode a write method's returned value from the transaction receipt.

    The leader receipt carries ``result.payload.readable`` as a JSON-encoded
    value (e.g. ``'"obl_0"'``), so no separate calldata decoder is required.
    """
    for entry in receipt["consensus_data"]["leader_receipt"]:
        result = entry.get("result")
        if isinstance(result, dict) and result.get("status") == "return":
            readable = result.get("payload", {}).get("readable")
            if readable is None:
                continue
            try:
                return json.loads(readable)
            except Exception:
                return readable
    raise AssertionError(
        "no returned value in receipt (status=%r)" % receipt.get("status_name")
    )


def _local_schema():
    """Load the authoritative ABI produced by `genvm-lint schema` (Gate 1b).

    StudioNet does not expose `gen_getContractSchemaForCode` (localnet-only), so
    gltest's `factory.deploy()` cannot fetch the schema from the node. We deploy
    the transaction ourselves and build the typed client from the local artifact
    instead. `./scripts/run_gates.sh` regenerates proof/02_schema.json from the
    current contract source.
    """
    path = Path(__file__).resolve().parents[2] / "proof" / "02_schema.json"
    data = json.loads(path.read_text())
    schema = data.get("schema", data)
    if "methods" not in schema or not schema["methods"]:
        raise RuntimeError("proof/02_schema.json missing methods; run ./scripts/run_gates.sh")
    return schema


@pytest.fixture(scope="module")
def deployed():
    factory = get_contract_factory("ClauseGuard")
    receipt = factory.deploy_contract_tx(wait_interval=5000, wait_retries=60)
    address = extract_contract_address(receipt)
    print("\n[studionet] ClauseGuard deployed at: %s" % address)
    return Contract.new(address=address, schema=_local_schema(), account=DEFAULT)


def _register(contract):
    return contract.register_obligation(
        args=[
            "Provide documentation covering installation, configuration and troubleshooting.",
            DEFAULT.address,
            json.dumps(DOCS_CRITERIA),
            1,
            1,
            json.dumps(DOCS_TYPES),
            json.dumps(DOCS_TRUSTED_HOSTS),
            ALLOW_ANY_SOURCE,
        ],
    ).transact()


@pytest.mark.integration
def test_register_returns_obligation_id(deployed):
    contract = deployed
    rec = _register(contract)
    assert tx_execution_succeeded(rec)
    oid = _return_value(rec)
    assert oid.startswith("obl_")
    # read it back
    assert contract.get_obligation(args=[oid]).call()["status"] == "active"


@pytest.mark.integration
def test_full_flow_register_submit_evaluate_read(deployed):
    """register -> submit -> evaluate (consensus) -> read record."""
    contract = deployed
    rec = _register(contract)
    assert tx_execution_succeeded(rec)
    oid = _return_value(rec)

    sub = contract.submit_evidence(
        args=[oid, json.dumps([{"type": "documentation", "ref": DOCS_URL}])]
    ).transact()
    assert tx_execution_succeeded(sub)
    sid = oid + "#0"

    # evaluate: real LLM + real web, full consensus. Success => leader and
    # validators agreed under the contract's equivalence rule.
    ev = contract.evaluate_submission(args=[sid]).transact(
        wait_interval=15000, wait_retries=60
    )
    assert tx_execution_succeeded(ev)

    outcome = _return_value(ev)
    assert outcome in VALID_OUTCOMES

    record = contract.get_latest_record(args=[sid]).call()
    assert record["outcome"] == outcome
    assert record["evaluation_round"] == 0
    results = json.loads(record["criteria_results_json"])
    assert [r["id"] for r in results] == ["c1", "c2", "c3"]
    assert json.loads(record["review_grounds_json"]) == []
    # auditability: the round records which evidence informed it, and the
    # digest of the exact normalized evidence text the leader used.
    assert record["evidence_changed"] is False
    provenance = json.loads(record["evidence_provenance_json"])
    assert len(provenance) == 1
    assert provenance[0]["host"] == "docs.python.org"
    assert len(record["evidence_digest"]) == 64


@pytest.mark.integration
def test_submission_validation_reverts(deployed):
    """Deterministic rejections need no LLM; verify access control on-chain."""
    contract = deployed
    rec = _register(contract)
    assert tx_execution_succeeded(rec)
    oid = _return_value(rec)
    # empty evidence (min_evidence=1) must fail deterministically
    bad = contract.submit_evidence(args=[oid, json.dumps([])]).transact()
    assert tx_execution_failed(bad)
    # off-policy host must fail deterministically (trusted-host allowlist)
    off_policy = contract.submit_evidence(
        args=[
            oid,
            json.dumps([{"type": "documentation", "ref": "https://example.com/doc"}]),
        ]
    ).transact()
    assert tx_execution_failed(off_policy)
