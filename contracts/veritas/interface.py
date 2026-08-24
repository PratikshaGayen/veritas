# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Typed cross-contract interface for Veritas.

GenLayer contracts cannot import code from other files at deploy time —
`genlayer deploy --contract <path>` ships exactly the bytes of one file
(confirmed in docs/BUILD-PLAN.md phase 3). This file therefore serves two
purposes, not one:

1. Local development / IDE type-checking against a deployed Veritas
   address (import it in your own dev environment for autocomplete).
2. THE CANONICAL COPY-PASTE BLOCK. Copy the `VeritasIface` class below —
   and only that class — into your own contract file to get a typed
   handle on a deployed Veritas contract. See examples/ for three worked
   patterns, and README.md for the quickest copy-paste path.

Usage inside your own contract:

    iface = VeritasIface(veritas_address)
    fact = iface.view().get_fact(key, u256(3600))
    iface.emit(on="finalized").request_fact(url, question, schema)
"""

from genlayer import *


@gl.contract_interface
class VeritasIface:
    class View:
        def compute_key(self, url: str, question: str, schema: str) -> str: ...
        def get_fact(self, key: str, max_age: u256) -> dict: ...
        def has_fresh(self, key: str, max_age: u256) -> bool: ...
        def stats(self) -> dict: ...

    class Write:
        def request_fact(self, url: str, question: str, schema: str) -> None: ...
        def refresh(self, key: str) -> None: ...
