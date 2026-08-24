# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""examples/request_then_settle.py - the canonical Veritas caller pattern.

Demonstrates all three branches a real caller needs (docs/ARCHITECTURE.md
section 7): request when there's nothing cached yet, wait when a
resolution is already in flight or stale, and refuse to guess when the
fact resolved to anything other than OK.

The VeritasIface block below is copy-pasted verbatim from
contracts/veritas/interface.py - that file is the canonical source.
"""

from genlayer import *


@gl.contract_interface
class VeritasIface:
    class View:
        def compute_key(self, url: str, question: str, schema: str) -> str: ...
        def get_fact(self, key: str, max_age: u256) -> dict: ...

    class Write:
        def request_fact(self, url: str, question: str, schema: str) -> None: ...


class RequestThenSettle(gl.Contract):
    veritas_addr: Address
    url: str
    question: str
    schema: str
    settled: bool
    outcome: bool

    def __init__(self, veritas_addr: Address, url: str, question: str, schema: str):
        self.veritas_addr = veritas_addr
        self.url = url
        self.question = question
        self.schema = schema
        self.settled = False
        self.outcome = False

    @gl.public.write
    def settle(self) -> None:
        iface = VeritasIface(self.veritas_addr)
        key = iface.view().compute_key(self.url, self.question, self.schema)
        fact = iface.view().get_fact(key, u256(3600))

        if fact["status"] == "PENDING" or not fact["is_fresh"]:
            # request_fact is idempotent - safe to call even if a
            # resolution is already in flight. Come back and call
            # settle() again once it resolves.
            iface.emit(on="finalized").request_fact(self.url, self.question, self.schema)
            return

        if fact["status"] != "OK":
            # UNAVAILABLE or SCHEMA_VIOLATION - wait, don't guess.
            return

        self.settled = True
        self.outcome = fact["answer"] == "true"
