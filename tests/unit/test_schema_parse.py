"""Phase 1 task 1.1 — schema declaration parsing and canonicalization."""

import pytest

from lib.schema.parse import (
    Schema,
    SchemaDeclError,
    canonical,
    legal_values,
    parse_schema,
)


# ---------------------------------------------------------------------------
# Canonicalization decides cache-slot sharing — this is the test that matters.
# ---------------------------------------------------------------------------


def test_enum_canonicalization_ignores_case_spacing_order():
    a = canonical(parse_schema("ENUM: Up , down,DEGRADED "))
    b = canonical(parse_schema("ENUM:degraded,down,up"))
    assert a == b == "ENUM:degraded,down,up"


def test_enum_canonicalization_dedupes():
    assert canonical(parse_schema("ENUM:up,UP,Up")) == "ENUM:up"


def test_bool_canonicalization_is_fixed():
    assert canonical(parse_schema("BOOL")) == "BOOL"
    assert canonical(parse_schema(" bool ")) == "BOOL"


def test_date_day_canonicalization_is_fixed():
    assert canonical(parse_schema("DATE_DAY")) == "DATE_DAY"


def test_band_canonicalization_preserves_bounds():
    assert canonical(parse_schema("BAND:0:1000:50")) == "BAND:0:1000:50"


def test_int_canonicalization_preserves_bounds():
    assert canonical(parse_schema("INT:0:100")) == "INT:0:100"


# ---------------------------------------------------------------------------
# parse_schema — valid declarations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "decl,expected",
    [
        ("BOOL", Schema(kind="BOOL")),
        ("bool", Schema(kind="BOOL")),
        (" BOOL ", Schema(kind="BOOL")),
        ("DATE_DAY", Schema(kind="DATE_DAY")),
        ("INT:0:100", Schema(kind="INT", lo=0, hi=100)),
        ("INT:-10:10", Schema(kind="INT", lo=-10, hi=10)),
        ("INT:5:5", Schema(kind="INT", lo=5, hi=5)),  # degenerate but legal
        ("BAND:0:1000:50", Schema(kind="BAND", lo=0, hi=1000, step=50)),
    ],
)
def test_parse_valid_declarations(decl, expected):
    assert parse_schema(decl) == expected


def test_parse_enum_options_sorted_tuple():
    s = parse_schema("ENUM:up,down,degraded")
    assert s.kind == "ENUM"
    assert s.options == ("degraded", "down", "up")


# ---------------------------------------------------------------------------
# parse_schema — malformed declarations, every one raises SchemaDeclError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "decl",
    [
        "",
        "   ",
        "NOT_A_KIND",
        "BOOL:extra",
        "DATE_DAY:extra",
        "ENUM",
        "ENUM:",
        "ENUM: , , ",
        "BAND:0:1000",  # missing step
        "BAND:0:1000:50:extra",
        "BAND:0:1000:0",  # step must be positive
        "BAND:0:1000:-5",  # step must be positive
        "BAND:1000:0:50",  # hi <= lo
        "BAND:0:0:50",  # hi <= lo (equal)
        "BAND:0:1001:50",  # not evenly divisible
        "BAND:zero:1000:50",  # not integers
        "INT:0",  # missing hi
        "INT:0:100:200",  # too many parts
        "INT:100:0",  # hi < lo
        "INT:zero:100",  # not integers
    ],
)
def test_parse_malformed_declarations_raise(decl):
    with pytest.raises(SchemaDeclError):
        parse_schema(decl)


def test_parse_schema_error_never_raises_other_exception_types():
    # Guards against a stray IndexError/KeyError leaking out of the parser.
    garbage_inputs = ["::::", "BAND::::", "ENUM:::::", ":", None]
    for g in garbage_inputs:
        try:
            parse_schema(g)  # type: ignore[arg-type]
        except SchemaDeclError:
            pass
        except Exception as e:  # pragma: no cover - failure path under test
            pytest.fail(
                f"parse_schema({g!r}) raised {type(e).__name__}, not SchemaDeclError: {e}"
            )


# ---------------------------------------------------------------------------
# legal_values — used for prompt injection, must never raise for a valid Schema
# ---------------------------------------------------------------------------


def test_legal_values_bool():
    assert legal_values(parse_schema("BOOL")) == ["true", "false"]


def test_legal_values_enum_matches_options():
    assert legal_values(parse_schema("ENUM:up,down,degraded")) == [
        "degraded",
        "down",
        "up",
    ]


def test_legal_values_band_and_int_and_date_are_descriptive_nonempty():
    for decl in ["BAND:0:1000:50", "INT:0:100", "DATE_DAY"]:
        vals = legal_values(parse_schema(decl))
        assert isinstance(vals, list)
        assert len(vals) == 1
        assert vals[0]
