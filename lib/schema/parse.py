"""Schema declaration parsing and canonicalization.

Pure Python, no GenLayer imports. See docs/BUILD-PLAN.md phase 1 and
docs/ARCHITECTURE.md section 2 for the design rationale: the tolerance for a
fact lives in the declared schema, not in the validator, so canonicalization
here decides which callers share a cache slot.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


class SchemaDeclError(ValueError):
    """Raised when a schema declaration string is malformed.

    Plain exception — this module has no GenLayer imports. The contract layer
    (phase 3) is responsible for wrapping this in a gl.vm.UserError with the
    appropriate [EXPECTED]/[EXTERNAL] prefix.
    """


KNOWN_KINDS = frozenset({"BOOL", "ENUM", "BAND", "DATE_DAY", "INT"})


class Schema(NamedTuple):
    kind: str
    options: tuple[str, ...] = ()
    lo: Optional[int] = None
    hi: Optional[int] = None
    step: Optional[int] = None


def _split(decl: str) -> list[str]:
    return [p.strip() for p in decl.split(":")]


def parse_schema(decl: str) -> Schema:
    """Parse a schema declaration string into a Schema. Raises SchemaDeclError."""
    if not isinstance(decl, str) or not decl.strip():
        raise SchemaDeclError("empty schema declaration")

    parts = _split(decl)
    kind = parts[0].strip().upper()

    if kind not in KNOWN_KINDS:
        raise SchemaDeclError(f"unknown schema kind: {parts[0]!r}")

    if kind == "BOOL":
        if len(parts) != 1:
            raise SchemaDeclError(f"BOOL takes no arguments, got: {decl!r}")
        return Schema(kind="BOOL")

    if kind == "DATE_DAY":
        if len(parts) != 1:
            raise SchemaDeclError(f"DATE_DAY takes no arguments, got: {decl!r}")
        return Schema(kind="DATE_DAY")

    if kind == "ENUM":
        if len(parts) < 2 or not parts[1]:
            raise SchemaDeclError(f"ENUM requires options, got: {decl!r}")
        # Options may themselves contain further colons only if malformed input
        # rejoins them; canonical form has exactly one colon, so anything past
        # index 1 is treated as part of the options list (defensive, not
        # expected in well-formed input).
        raw_options = ":".join(parts[1:])
        options = tuple(
            sorted({o.strip().lower() for o in raw_options.split(",") if o.strip()})
        )
        if not options:
            raise SchemaDeclError(f"ENUM requires at least one option, got: {decl!r}")
        return Schema(kind="ENUM", options=options)

    if kind == "BAND":
        if len(parts) != 4:
            raise SchemaDeclError(f"BAND requires lo:hi:step, got: {decl!r}")
        lo, hi, step = _parse_ints(parts[1], parts[2], parts[3], decl_hint=decl)
        if step <= 0:
            raise SchemaDeclError(f"BAND step must be positive, got: {decl!r}")
        if hi <= lo:
            raise SchemaDeclError(f"BAND hi must be greater than lo, got: {decl!r}")
        if (hi - lo) % step != 0:
            raise SchemaDeclError(
                f"BAND range must be evenly divisible by step, got: {decl!r}"
            )
        return Schema(kind="BAND", lo=lo, hi=hi, step=step)

    if kind == "INT":
        if len(parts) != 3:
            raise SchemaDeclError(f"INT requires lo:hi, got: {decl!r}")
        lo, hi = _parse_ints(parts[1], parts[2], decl_hint=decl)
        if hi < lo:
            raise SchemaDeclError(f"INT hi must be >= lo, got: {decl!r}")
        return Schema(kind="INT", lo=lo, hi=hi)

    raise SchemaDeclError(f"unhandled schema kind: {kind!r}")  # pragma: no cover


def _parse_ints(*raw: str, decl_hint: str) -> tuple[int, ...]:
    out = []
    for r in raw:
        try:
            out.append(int(r))
        except ValueError:
            raise SchemaDeclError(f"expected integer, got {r!r} in {decl_hint!r}")
    return tuple(out)


def canonical(s: Schema) -> str:
    """The exact string that goes into the content-addressed key."""
    if s.kind == "BOOL":
        return "BOOL"
    if s.kind == "DATE_DAY":
        return "DATE_DAY"
    if s.kind == "ENUM":
        return "ENUM:" + ",".join(s.options)
    if s.kind == "BAND":
        return f"BAND:{s.lo}:{s.hi}:{s.step}"
    if s.kind == "INT":
        return f"INT:{s.lo}:{s.hi}"
    raise SchemaDeclError(f"cannot canonicalize unknown kind: {s.kind!r}")


def legal_values(s: Schema) -> list[str]:
    """Human-readable legal-value description(s) for prompt injection.

    For discrete kinds (BOOL, ENUM) this enumerates every legal value. For
    continuous kinds (BAND, INT, DATE_DAY) enumeration is impractical or
    unbounded, so a single descriptive string is returned instead. Callers
    building a prompt should join the list with commas or "or".
    """
    if s.kind == "BOOL":
        return ["true", "false"]
    if s.kind == "ENUM":
        return list(s.options)
    if s.kind == "BAND":
        n_bands = (s.hi - s.lo) // s.step
        return [
            f"a number between {s.lo} and {s.hi} (bucketed in steps of {s.step}, {n_bands} bands)"
        ]
    if s.kind == "INT":
        return [f"an integer between {s.lo} and {s.hi} inclusive"]
    if s.kind == "DATE_DAY":
        return ["a date in YYYY-MM-DD format"]
    raise SchemaDeclError(f"cannot enumerate unknown kind: {s.kind!r}")
