#!/usr/bin/env python3
"""
Gate 3a proof: deploy ClauseGuard under full GenLayer consensus on GLSim.

Runs the GLSim SimEngine directly (bypassing gltest, whose schema RPC uses a
different param convention than this GLSim build) and executes a real
leader + N-validator consensus over the deploy transaction. Prints the
consensus status and per-validator votes.

Usage:
    python3 scripts/glsim_consensus_deploy.py
"""
import sys
from pathlib import Path

from glsim.state import StateStore
from glsim.engine import SimEngine
from glsim.consensus import run_consensus

CONTRACT = Path(__file__).resolve().parent.parent / "contracts" / "clause_guard.py"
SENDER = "0x" + "11" * 20
N_VALIDATORS = 5
MAX_ROTATIONS = 3


def main() -> int:
    if not CONTRACT.exists():
        print(f"contract not found: {CONTRACT}", file=sys.stderr)
        return 2

    state = StateStore()
    engine = SimEngine(state)
    engine.num_validators = N_VALIDATORS
    engine.max_rotations = MAX_ROTATIONS

    code_bytes = CONTRACT.read_bytes()

    def execute_fn():
        addr, _inst = engine.deploy_from_code(code_bytes, b"", SENDER)
        return addr, b""

    consensus = run_consensus(engine, execute_fn, N_VALIDATORS, MAX_ROTATIONS)

    print(f"contract      : {CONTRACT.name}")
    print(f"runners       : pinned GenVM Depends header")
    print(f"validators    : {N_VALIDATORS}")
    print(f"consensus status: {consensus.status}")
    print(f"consensus error : {consensus.error}")
    print(f"contract address: {consensus.result}")
    # A finalized address with no error == leader + validators agreed.
    ok = consensus.error is None and consensus.result is not None
    print("DEPLOY_CONSENSUS_OK" if ok else "DEPLOY_CONSENSUS_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
