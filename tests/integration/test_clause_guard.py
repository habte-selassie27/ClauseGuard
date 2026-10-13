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

import base64
import json

import pytest
from gltest import get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded, tx_execution_failed

DEFAULT = get_default_account()

DOCS_CRITERIA = [
    {"id": "c1", "text": "documents installation steps", "required": True},
    {"id": "c2", "text": "documents configuration options", "required": True},
    {"id": "c3", "text": "documents troubleshooting guidance", "required": True},
]
DOCS_TYPES = ["documentation"]
DOCS_URL = "https://docs.python.org/3/tutorial/introduction.html"

VALID_OUTCOMES = {"satisfied", "not_satisfied", "inconclusive"}


def _return_value(receipt):
    """Decode the write method's returned string from the receipt."""
    import genlayer.py.calldata as calldata

    leader = receipt["consensus_data"]["leader_receipt"][0]
    raw = base64.b64decode(leader["result"])
    return calldata.decode(raw)


@pytest.fixture(scope="module")
def deployed():
    factory = get_contract_factory("ClauseGuard")
    return factory.deploy()


def _register(contract):
    return contract.register_obligation(
        args=[
            "Provide documentation covering installation, configuration and troubleshooting.",
            default_account.address,
            json.dumps(DOCS_CRITERIA),
            1,
            1,
            json.dumps(DOCS_TYPES),
        ],
        wait_interval=3000,
        wait_retries=40,
    )


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
        args=[oid, json.dumps([{"type": "documentation", "ref": DOCS_URL}])],
        wait_interval=3000,
        wait_retries=40,
    )
    assert tx_execution_succeeded(sub)
    sid = oid + "#0"

    # evaluate: real LLM + real web, full consensus. Success => leader and
    # validators agreed under the contract's equivalence rule.
    ev = contract.evaluate_submission(args=[sid], wait_interval=15000, wait_retries=40)
    assert tx_execution_succeeded(ev)

    outcome = _return_value(ev)
    assert outcome in VALID_OUTCOMES

    record = contract.get_latest_record(args=[sid]).call()
    assert record["outcome"] == outcome
    assert record["evaluation_round"] == 0
    results = json.loads(record["criteria_results_json"])
    assert [r["id"] for r in results] == ["c1", "c2", "c3"]


@pytest.mark.integration
def test_submission_validation_reverts(deployed):
    """Deterministic rejections need no LLM; verify access control on-chain."""
    contract = deployed
    rec = _register(contract)
    assert tx_execution_succeeded(rec)
    oid = _return_value(rec)
    # empty evidence (min_evidence=1) must fail deterministically
    from gltest.assertions import tx_execution_failed

    bad = contract.submit_evidence(
        args=[oid, json.dumps([])], wait_interval=3000, wait_retries=40
    )
    assert tx_execution_failed(bad)
