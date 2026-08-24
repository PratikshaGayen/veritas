"""Phase 3/4 — on-chain vs off-chain key derivation parity.

The on-chain compute_key() (contracts/veritas/veritas.py) is a hand-kept
lock-step copy of the off-chain veritas_key() (lib/schema/keys.py). This
test proves they haven't drifted, using the same golden vectors as
tests/unit/test_schema_keys.py. If this test ever fails, every cached fact
in the deployed contract is orphaned for callers using the off-chain
helper — see docs/ARCHITECTURE.md section 3.
"""

from lib.schema.keys import veritas_key

CASES = [
    ("https://example.com/status", "Is it up?", "BOOL"),
    ("https://flightaware.com/live/flight/AI302", "Is this flight delayed more than 3 hours?", "BOOL"),
    ("https://example.com/Status", "Is it up?", "ENUM:degraded,down,up"),
    ("https://example.com/funding", "What is the funding rate?", "BAND:0:1000:50"),
    ("https://Example.com:443/Status/", "Is it up?", "ENUM: Up , down,DEGRADED "),
]


def test_compute_key_matches_off_chain_derivation(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/veritas/veritas.py")
    direct_vm.sender = direct_alice

    for url, question, schema in CASES:
        onchain = contract.compute_key(url, question, schema)
        offchain = veritas_key(url, question, schema)
        assert onchain == offchain, f"parity broken for {(url, question, schema)!r}"
