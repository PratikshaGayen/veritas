"""Off-chain content-addressed fact key derivation.

Pure Python, no GenLayer imports. Must produce byte-identical output to the
on-chain compute_key() in contracts/veritas/veritas.py (phase 3/4) — see
docs/ARCHITECTURE.md section 3. This is the single most load-bearing function
in the project: if this ever diverges from the on-chain version, every caller
silently misses the shared cache.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit, urlunsplit

from lib.schema.parse import parse_schema, canonical

_DEFAULT_PORTS = {"http": 80, "https": 443}


def canonical_url(url: str) -> str:
    """Lowercase scheme/host, strip default port, strip trailing slash and
    fragment. Query string and path case are preserved.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()

    host = parts.hostname or ""
    host = host.lower()

    port = parts.port
    if port is not None and _DEFAULT_PORTS.get(scheme) == port:
        port = None

    netloc = host
    if port is not None:
        netloc = f"{host}:{port}"
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo += f":{parts.password}"
        netloc = f"{userinfo}@{netloc}"

    path = parts.path
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, parts.query, ""))


def veritas_key(url: str, question: str, schema_decl: str) -> str:
    """sha256(canonical_url || 0x00 || question || 0x00 || canonical_schema), hex."""
    schema = parse_schema(schema_decl)
    payload = "\x00".join(
        [canonical_url(url), question.strip(), canonical(schema)]
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
