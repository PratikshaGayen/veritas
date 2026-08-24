# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""examples/read_only.py — the simplest Veritas integration.

Reads a cached fact and settles based on it. Never calls request_fact
itself — this pattern assumes some other caller (or a one-off CLI call)
has already requested the fact. Good for a contract that only cares about
a fact someone else is already keeping fresh.

The VeritasIface block below is copy-pasted verbatim from
contracts/veritas/interface.py — that file is the canonical source.
"""

from genlayer import *


@gl.contract_interface
class VeritasIface:
    class View:
        def get_fact(self, key: str, max_age: u256) -> dict: ...

    class Write:
        pass


class ReadOnlyConsumer(gl.Contract):
    veritas_addr: Address
    fact_key: str
    max_age: u256
    settled: bool
    outcome: bool

    def __init__(self, veritas_addr: Address, fact_key: str, max_age: u256):
        self.veritas_addr = veritas_addr
        self.fact_key = fact_key
        self.max_age = max_age
        self.settled = False
        self.outcome = False

    @gl.public.view
    def check(self) -> dict:
        iface = VeritasIface(self.veritas_addr)
        return iface.view().get_fact(self.fact_key, self.max_age)

    @gl.public.write
    def settle(self) -> None:
        iface = VeritasIface(self.veritas_addr)
        fact = iface.view().get_fact(self.fact_key, self.max_age)

        if fact["status"] != "OK" or not fact["is_fresh"]:
            # Wait, don't guess. See docs/ARCHITECTURE.md section 1.
            raise gl.vm.UserError("[EXPECTED] fact not ready")

        self.settled = True
        self.outcome = fact["answer"] == "true"
