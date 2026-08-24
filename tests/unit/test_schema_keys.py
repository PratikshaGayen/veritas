"""Phase 1 task 1.3 — off-chain content-addressed key derivation.

The golden vectors below were computed by actually running veritas_key()
(see the git history / session log), not hand-typed. If this test ever needs
to change, regenerate the vectors the same way and note why in the commit —
changing key derivation after deployment orphans every cached fact.
"""

from lib.schema.keys import canonical_url, veritas_key

# ---------------------------------------------------------------------------
# Golden vectors — must never change silently.
# ---------------------------------------------------------------------------

GOLDEN = {
    ("https://example.com/status", "Is it up?", "BOOL"):
        "904b39eba1bef6267859172410e755ab0cfec39f1bf5838c2485138b935bb230"[:64],
    ("https://flightaware.com/live/flight/AI302",
     "Is this flight delayed more than 3 hours?", "BOOL"):
        "4ea094b8185fb71a64ad3f48858dacacc372390f105ee12b91c7416e6a3c409b"[:64],
    ("https://example.com/Status", "Is it up?", "ENUM:degraded,down,up"):
        "d5dece676d59514c641ba2fd536268ec5b015ad3241c07608f04e7dbe3f7aa0e"[:64],
    ("https://example.com/funding", "What is the funding rate?", "BAND:0:1000:50"):
        "4c05caeeeb5c3d5cbae31bdee4fc7375ff911394731a9b659452244acd6d06b1"[:64],
}


def test_golden_vectors_are_stable():
    for (url, question, schema_decl), expected in GOLDEN.items():
        assert len(expected) == 64, "sanity check on the fixture itself"
        assert veritas_key(url, question, schema_decl) == expected


# ---------------------------------------------------------------------------
# URL canonicalization — the properties that decide cache-slot sharing
# ---------------------------------------------------------------------------


def test_key_stable_across_scheme_and_host_case():
    a = veritas_key("HTTPS://EXAMPLE.COM/Status", "Is it up?", "BOOL")
    b = veritas_key("https://example.com/Status", "Is it up?", "BOOL")
    assert a == b


def test_key_differs_across_path_case():
    a = veritas_key("https://Example.com/Status", "Is it up?", "BOOL")
    b = veritas_key("https://example.com/status", "Is it up?", "BOOL")
    assert a != b  # path case is preserved, by design


def test_key_stable_across_default_port():
    a = veritas_key("https://example.com/status", "Is it up?", "BOOL")
    b = veritas_key("https://example.com:443/status", "Is it up?", "BOOL")
    assert a == b


def test_key_stable_across_trailing_slash():
    a = veritas_key("https://example.com/status", "Is it up?", "BOOL")
    b = veritas_key("https://example.com/status/", "Is it up?", "BOOL")
    assert a == b


def test_key_stable_across_fragment():
    a = veritas_key("https://example.com/status", "Is it up?", "BOOL")
    b = veritas_key("https://example.com/status#ignored", "Is it up?", "BOOL")
    assert a == b


def test_key_differs_across_query_string():
    a = veritas_key("https://example.com/status", "Is it up?", "BOOL")
    b = veritas_key("https://example.com/status?x=1", "Is it up?", "BOOL")
    assert a != b  # query string is preserved, by design


def test_key_stable_across_question_whitespace():
    a = veritas_key("https://example.com/status", "Is it up?", "BOOL")
    b = veritas_key("https://example.com/status", "  Is it up?  ", "BOOL")
    assert a == b


def test_key_stable_across_equivalent_schema_declarations():
    a = veritas_key("https://example.com/status", "Is it up?", "ENUM: Up , down,DEGRADED ")
    b = veritas_key("https://example.com/status", "Is it up?", "ENUM:degraded,down,up")
    assert a == b


def test_key_differs_for_different_questions():
    a = veritas_key("https://example.com/status", "Is it up?", "BOOL")
    b = veritas_key("https://example.com/status", "Is it down?", "BOOL")
    assert a != b


def test_key_differs_for_different_schemas():
    a = veritas_key("https://example.com/status", "What is the state?", "BOOL")
    b = veritas_key("https://example.com/status", "What is the state?", "ENUM:up,down")
    assert a != b


def test_key_differs_for_different_band_precision():
    # Two callers needing different precision get different cache slots on purpose.
    a = veritas_key("https://example.com/rate", "What is the rate?", "BAND:0:1000:50")
    b = veritas_key("https://example.com/rate", "What is the rate?", "BAND:0:1000:100")
    assert a != b


def test_key_is_hex_sha256_length():
    k = veritas_key("https://example.com/status", "Is it up?", "BOOL")
    assert len(k) == 64
    int(k, 16)  # raises if not valid hex


# ---------------------------------------------------------------------------
# canonical_url unit-level checks
# ---------------------------------------------------------------------------


def test_canonical_url_strips_default_port_and_trailing_slash():
    assert canonical_url("https://Example.com:443/Status/") == "https://example.com/Status"


def test_canonical_url_preserves_nondefault_port():
    assert canonical_url("https://example.com:8443/status") == "https://example.com:8443/status"


def test_canonical_url_strips_fragment_preserves_query():
    assert canonical_url("https://example.com/status?x=1#frag") == "https://example.com/status?x=1"
