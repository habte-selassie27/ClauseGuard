"""Shared helpers for ClauseGuard direct-mode tests.

Direct mode runs the contract against the real pinned GenVM runner + SDK
(via gltest), with web and LLM operations mocked.
"""

import json


def to_hex(addr):
    """Return checksummed hex for an Address-like test value."""
    if hasattr(addr, "as_hex"):
        return addr.as_hex
    from genlayer.py.types import Address

    return Address(addr).as_hex


# The worked example from AGENTS.md: documentation must cover installation,
# configuration and troubleshooting.
DOCS_CRITERIA = [
    {"id": "c1", "text": "documents installation steps", "required": True},
    {"id": "c2", "text": "documents configuration options", "required": True},
    {"id": "c3", "text": "documents troubleshooting guidance", "required": True},
]
DOCS_TYPES = ["documentation"]
DOCS_URL = "https://example.com/docs"

LLM_MATCH = r"You are evaluating whether submitted evidence"


def register_docs_obligation(contract, vm, owner, obligor, criteria=None, types=None,
                             min_ev=1, max_ev=1):
    """Register the documentation obligation. owner is the sender."""
    vm.sender = owner
    return contract.register_obligation(
        "Provide documentation covering installation, configuration and troubleshooting.",
        to_hex(obligor),
        json.dumps(criteria if criteria is not None else DOCS_CRITERIA),
        min_ev,
        max_ev,
        json.dumps(types if types is not None else DOCS_TYPES),
    )


def mock_evidence(vm, url=DOCS_URL, text="Some documentation content."):
    vm.mock_web(url, {"status": 200, "body": text})


def mock_llm_statuses(vm, statuses, raw=None):
    """Mock the LLM to return per-criterion statuses.

    `statuses` is a dict id->status. `raw` (optional) is returned verbatim
    instead, for malformed / fenced / injection outputs.
    """
    if raw is not None:
        vm.mock_llm(LLM_MATCH, raw)
        return
    payload = {"criteria": [{"id": k, "status": v} for k, v in statuses.items()]}
    vm.mock_llm(LLM_MATCH, json.dumps(payload))


def mock_llm_raw_dict(vm, obj):
    vm.mock_llm(LLM_MATCH, json.dumps(obj))


def submit_docs(contract, vm, obligor, url=DOCS_URL, obligation_id=None, oid=None):
    vm.sender = obligor
    evidence = json.dumps([{"type": "documentation", "ref": url}])
    return contract.submit_evidence(oid, evidence)
