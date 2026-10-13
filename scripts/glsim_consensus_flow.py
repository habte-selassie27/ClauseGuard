#!/usr/bin/env python3
"""
Gate 3a proof: run ClauseGuard under full GenLayer consensus on GLSim.

Runs the GLSim SimEngine directly (bypassing gltest, whose schema RPC uses a
different param convention than this GLSim build) and executes real
leader + N-validator consensus over a full lifecycle transaction set:

  1. deploy
  2. register an obligation (explicit trusted-host allowlist)
  3. rejected registrations (empty allowlist, allowlist + any-host opt-in)
  4. rejected submissions (off-policy host, malformed https URL)
  5. accepted submission
  6. evaluate_submission  -> real run_nondet_unsafe block with the contract's
     own custom validator, run once by the leader and re-run by every validator
  7. open_challenge -> re-evaluate (round 1, grounds injected)
  8. reads: latest record, round history, provenance, challenge status

Web and LLM calls inside the nondeterministic block are served from deterministic
in-process mocks (this sandbox has no network egress), so the consensus being
proven here is the *agreement* property: every validator independently re-runs
the same task and must agree under the contract's equivalence rule. Live-network
and live-model behaviour is covered by tests/integration/ on a real network.

Usage:
    python3 scripts/glsim_consensus_flow.py
"""
import json
import sys
from pathlib import Path

from glsim.state import StateStore
from glsim.engine import SimEngine
from glsim.consensus import run_consensus

CONTRACT = Path(__file__).resolve().parent.parent / "contracts" / "clause_guard.py"
SENDER = "0x" + "11" * 20
N_VALIDATORS = 5
MAX_ROTATIONS = 3

DOCS_URL = "https://docs.example.com/guide"
OFF_POLICY_URL = "https://evil.example.net/doc"
MALFORMED_URL = "https://docs.example.com./guide"

CRITERIA = [
    {"id": "c1", "text": "documents installation steps", "required": True},
    {"id": "c2", "text": "documents configuration options", "required": True},
    {"id": "c3", "text": "documents troubleshooting guidance", "required": True},
]
DESCRIPTION = "Provide documentation covering installation, configuration and troubleshooting."
LLM_MATCH = "You are evaluating whether submitted evidence"

EVIDENCE_TEXT = (
    "Installation is covered in chapter 1. Configuration options are listed in "
    "chapter 2. Troubleshooting guidance is in chapter 3."
)

FAILURES = []


def report(ok, label, detail=""):
    print("%-6s %s%s" % ("PASS" if ok else "FAIL", label, (" — " + detail) if detail else ""))
    if not ok:
        FAILURES.append(label)


def tx(engine, address, method, args=None, label="", expect_error=None):
    """Run one transaction under leader + N-validator consensus."""

    def execute_fn():
        return engine.call_method(address, method, args=args or [], sender=SENDER), b""

    consensus = run_consensus(engine, execute_fn, N_VALIDATORS, MAX_ROTATIONS)
    votes = "%d/%d agree" % (
        sum(1 for v in consensus.votes if v == "agree"),
        len(consensus.votes),
    )
    if expect_error is None:
        ok = consensus.error is None and consensus.result is not None
    else:
        ok = consensus.error is not None and expect_error in consensus.error
    report(
        ok,
        label,
        "status=%s votes=%s%s"
        % (
            consensus.status,
            votes,
            (" error=%s" % consensus.error) if consensus.error else "",
        ),
    )
    return consensus


def read(engine, address, method, args=None):
    return engine.call_method(address, method, args=args or [], sender=SENDER)


def main() -> int:
    if not CONTRACT.exists():
        print("contract not found: %s" % CONTRACT, file=sys.stderr)
        return 2

    state = StateStore()
    engine = SimEngine(state)
    # activate() installs the in-process WASI bridge (storage + gl_call fd
    # plumbing). Without it, mocked web/LLM responses cannot be read back from
    # the contract and every nondet fetch fails with a bad file descriptor.
    engine.activate()
    engine.num_validators = N_VALIDATORS
    engine.max_rotations = MAX_ROTATIONS
    code_bytes = CONTRACT.read_bytes()

    print("contract        : %s" % CONTRACT.name)
    print("runners         : pinned GenVM Depends header")
    print("validators      : %d" % N_VALIDATORS)
    print("nondet mocks    : deterministic web + LLM (no network egress here)")
    print()

    # ---- 1. deploy -------------------------------------------------------
    deploy = run_consensus(
        engine, lambda: engine.deploy_from_code(code_bytes, b"", SENDER), N_VALIDATORS, MAX_ROTATIONS
    )
    print("deploy          : status=%s address=%s error=%s" % (deploy.status, deploy.result, deploy.error))
    if deploy.error is not None or deploy.result is None:
        report(False, "deploy reaches consensus")
        return 1
    report(True, "deploy reaches consensus", "%d validators, no error" % N_VALIDATORS)
    address = deploy.result

    # ---- 2. register (explicit allowlist) --------------------------------
    reg = tx(
        engine,
        address,
        "register_obligation",
        [
            DESCRIPTION,
            SENDER,
            json.dumps(CRITERIA),
            1,
            1,
            json.dumps(["documentation"]),
            json.dumps(["docs.example.com"]),
            False,
        ],
        label="register_obligation (trusted-host allowlist)",
    )
    obligation_id = reg.result
    if obligation_id is None:
        return 1
    obligation = read(engine, address, "get_obligation", [obligation_id])
    report(
        obligation["trusted_hosts_json"] == '["docs.example.com"]'
        and obligation["allow_any_https_source"] is False,
        "obligation stores the explicit source policy",
        obligation["trusted_hosts_json"],
    )

    # ---- 3. rejected registrations ---------------------------------------
    tx(
        engine,
        address,
        "register_obligation",
        [
            DESCRIPTION,
            SENDER,
            json.dumps(CRITERIA),
            1,
            1,
            json.dumps(["documentation"]),
            json.dumps([]),
            False,
        ],
        label="reject empty allowlist without any-host opt-in",
        expect_error="trusted_hosts must be non-empty",
    )
    tx(
        engine,
        address,
        "register_obligation",
        [
            DESCRIPTION,
            SENDER,
            json.dumps(CRITERIA),
            1,
            1,
            json.dumps(["documentation"]),
            json.dumps(["docs.example.com"]),
            True,
        ],
        label="reject allowlist combined with any-host opt-in",
        expect_error="must be empty when allow_any_https_source is true",
    )

    # ---- 4. rejected submissions -----------------------------------------
    tx(
        engine,
        address,
        "submit_evidence",
        [obligation_id, json.dumps([{"type": "documentation", "ref": OFF_POLICY_URL}])],
        label="reject off-policy evidence host",
        expect_error="not in trusted sources",
    )
    tx(
        engine,
        address,
        "submit_evidence",
        [obligation_id, json.dumps([{"type": "documentation", "ref": MALFORMED_URL}])],
        label="reject malformed https evidence URL",
        expect_error="not a well-formed https URL",
    )

    # ---- 5. accepted submission ------------------------------------------
    sub = tx(
        engine,
        address,
        "submit_evidence",
        [obligation_id, json.dumps([{"type": "documentation", "ref": DOCS_URL}])],
        label="submit evidence (policy-compliant https host)",
    )
    submission_id = sub.result
    if submission_id is None:
        return 1

    # ---- 6. evaluate under consensus (real run_nondet_unsafe) -------------
    engine.vm.mock_web(r"https://docs\.example\.com/guide", {"status": 200, "body": EVIDENCE_TEXT})
    engine.vm.mock_llm(
        LLM_MATCH,
        json.dumps({"criteria": [{"id": "c1", "status": "met"}, {"id": "c2", "status": "met"}, {"id": "c3", "status": "met"}]}),
    )
    ev = tx(engine, address, "evaluate_submission", [submission_id], label="evaluate_submission (leader + validators)")
    report(ev.result == "satisfied", "round 0 outcome derived deterministically", str(ev.result))

    record = read(engine, address, "get_latest_record", [submission_id])
    report(
        record["outcome"] == "satisfied"
        and record["reason_code"] == "ALL_REQUIRED_MET"
        and record["evaluation_round"] == 0
        and len(record["evidence_digest"]) == 64,
        "round 0 record (outcome, reason_code, digest)",
        "digest=%s… chars=%s" % (record["evidence_digest"][:16], record["evidence_chars"]),
    )
    provenance = json.loads(record["evidence_provenance_json"])
    report(
        len(provenance) == 1 and provenance[0]["host"] == "docs.example.com",
        "evidence provenance recorded",
        str(provenance),
    )

    # ---- 7. challenge -> re-evaluation -----------------------------------
    ch = tx(engine, address, "open_challenge", [submission_id, "the guide no longer covers troubleshooting"],
            label="open_challenge (party, bounded)")
    challenge_id = ch.result
    engine.vm.clear_mocks()
    engine.vm.mock_web(r"https://docs\.example\.com/guide", {"status": 200, "body": "Installation only."})
    engine.vm.mock_llm(
        "the guide no longer covers troubleshooting",
        json.dumps({"criteria": [{"id": "c1", "status": "met"}, {"id": "c2", "status": "met"}, {"id": "c3", "status": "not_met"}]}),
    )
    re_ev = tx(engine, address, "evaluate_submission", [submission_id], label="re-evaluate challenged submission (round 1)")
    report(re_ev.result == "not_satisfied", "round 1 outcome derived deterministically", str(re_ev.result))

    history = read(engine, address, "get_record_history", [submission_id])
    report(
        sorted(history) == ["0", "1"]
        and history["0"]["outcome"] == "satisfied"
        and history["1"]["outcome"] == "not_satisfied",
        "history preserves the earlier round",
    )
    report(
        history["1"]["evidence_changed"] is True
        and json.loads(history["1"]["review_grounds_json"]) == ["the guide no longer covers troubleshooting"],
        "review round records grounds + evidence change",
    )
    if challenge_id is not None:
        challenge = read(engine, address, "get_challenge", [challenge_id])
        report(
            challenge["status"] == "resolved" and challenge["challenged_round"] == 0,
            "challenge resolved after review round",
            "%s (round %s)" % (challenge["status"], challenge["challenged_round"]),
        )

    # ---- 8. verification block -------------------------------------------
    print()
    if FAILURES:
        print("CONSENSUS_FLOW_FAILED (%d): %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("CONSENSUS_FLOW_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
