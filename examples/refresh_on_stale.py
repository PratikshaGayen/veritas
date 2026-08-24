# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""examples/refresh_on_stale.py - pay to keep your own fact fresh.

Unlike request_fact (idempotent no-op if already fresh or already in
flight), refresh() unconditionally re-resolves - the right call when you
specifically want the newest possible answer and are willing to pay for
it. See docs/ARCHITECTURE.md section 8: "refresh is caller-driven" is a
deliberate design choice, not a missing feature - cost falls on whoever
needs freshness.

The VeritasIface block below is copy-pasted verbatim from
contracts/veritas/interface.py - that file is the canonical source.
"""

from genlayer import *


@gl.contract_interface
class VeritasIface:
    class View:
        def get_fact(self, key: str, max_age: u256) -> dict: ...

    class Write:
        def refresh(self, key: str) -> None: ...


class RefreshOnStale(gl.Contract):
    veritas_addr: Address
    fact_key: str
    max_age: u256

    def __init__(self, veritas_addr: Address, fact_key: str, max_age: u256):
        self.veritas_addr = veritas_addr
        self.fact_key = fact_key
        self.max_age = max_age

    @gl.public.write
    def poll(self) -> None:
        iface = VeritasIface(self.veritas_addr)
        fact = iface.view().get_fact(self.fact_key, self.max_age)
        if not fact["is_fresh"]:
            iface.emit(on="finalized").refresh(self.fact_key)
