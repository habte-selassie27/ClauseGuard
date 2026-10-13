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
                             min_ev=1, max_ev=1, trusted_hosts=None, allow_any=None):
    """Register the documentation obligation. owner is the sender.

    Source policy is explicit in the contract: either a non-empty
    ``trusted_hosts`` allowlist or ``allow_any_https_source=True``. When
    ``allow_any`` is not given it is derived from ``trusted_hosts`` so callers
    keep the old "no list means any host" ergonomics while the ABI stays
    fail-closed.
    """
    hosts = trusted_hosts if trusted_hosts is not None else []
    if allow_any is None:
        allow_any = not hosts
    vm.sender = owner
    return contract.register_obligation(
        "Provide documentation covering installation, configuration and troubleshooting.",
        to_hex(obligor),
        json.dumps(criteria if criteria is not None else DOCS_CRITERIA),
        min_ev,
        max_ev,
        json.dumps(types if types is not None else DOCS_TYPES),
        json.dumps(hosts),
        allow_any,
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


def load_contract_module():
    """Return the live GenVM-loaded contract module (gltest names it
    ``_contract_clause_guard``). Deploy the contract first."""
    import sys

    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and path.endswith("contracts/clause_guard.py") and hasattr(
            module, "_parse_https_url"
        ):
            return module
    raise AssertionError("contract module not loaded: deploy the contract first")
