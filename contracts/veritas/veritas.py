# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Veritas - a shared, schema-constrained web-fact oracle.

Self-contained by design: `genlayer deploy --contract <path>` ships exactly
the bytes of this one file (confirmed against the CLI's deployment
mechanics - there is no multi-file import path for a single `py-genlayer`
deployment). The schema/normalize logic below is a lock-step copy of
lib/schema/*.py and lib/normalize/*.py, verified identical by
tests/direct/test_veritas_parity.py. See docs/ARCHITECTURE.md and
docs/BUILD-PLAN.md phase 3 for the full design rationale.

Error taxonomy note (a refinement made concrete while writing this file):
HTTP/fetch failures do NOT raise - they become the UNAVAILABLE status VALUE,
because that is the entire point of Veritas (docs/ARCHITECTURE.md section
1). [EXPECTED] fires for a malformed schema declaration, deterministically,
*before* the non-deterministic block even starts, so it never needs
leader/validator comparison at all. [LLM_ERROR] fires inside the leader
function when the model returns non-dict JSON, and always forces validator
disagreement (rotation) per docs/ARCHITECTURE.md section 5. [EXTERNAL] and
[TRANSIENT] are therefore unused in v1 - reserved for a future failure
class that must raise rather than resolve to UNAVAILABLE.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from genlayer import *

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ERROR_EXPECTED = "[EXPECTED]"
ERROR_LLM = "[LLM_ERROR]"

STATUS_OK = "OK"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
STATUS_PENDING = "PENDING"

DEFAULT_MAX_AGE = 3600
PENDING_RETRY_WINDOW = 120  # seconds before a PENDING slot can be re-requested

MIN_EVIDENCE_CHARS = 40
PAYWALL_LENGTH_FLOOR = 600
MAX_EVIDENCE_CHARS = 4000
_WINDOW_RADIUS = MAX_EVIDENCE_CHARS // 2

_KNOWN_KINDS = frozenset({"BOOL", "ENUM", "BAND", "DATE_DAY", "INT"})

_BOT_WALL_MARKERS = (
    "just a moment",
    "enable javascript",
    "access denied",
    "attention required",
    "checking your browser",
    "verify you are human",
    "please enable cookies",
    "unusual traffic",
)

_PAYWALL_MARKERS = (
    "subscribe to continue",
    "subscribe now to read",
    "this article is for subscribers",
    "you have reached your article limit",
    "become a subscriber",
    "sign in to continue reading",
    "to continue reading this article",
)

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "this",
        "that", "what", "when", "where", "which", "who", "how", "does",
        "did", "do", "has", "have", "had", "for", "and", "or", "of", "to",
        "in", "on", "at", "it", "than", "more",
    }
)

_DROP_BLOCK_RE = re.compile(
    r"<(script|style|nav|footer|aside)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z0-9]{4,}")

_BOOL_TRUE = {"true", "yes", "1"}
_BOOL_FALSE = {"false", "no", "0"}
_BOOL_TOKEN_RE = re.compile(r"\b(true|false|yes|no|1|0)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_INT_RE = re.compile(r"-?\d+")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

_REL_TIME_RE = re.compile(
    r"\b("
    r"just now"
    r"|a (?:second|minute|hour|day|week|month|year) ago"
    r"|\d+\s*(?:second|minute|hour|day|week|month|year)s?\s+ago"
    r"|(?:yesterday|today|tomorrow)"
    r")\b",
    re.IGNORECASE,
)
_SUBDAY_TIME_RE = re.compile(
    r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp][Mm])?\b"
    r"|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_QUANTIZE_NUMBER_RE = re.compile(r"\d[\d,]{2,}(?!-\d{2}-\d{2})")

_DEFAULT_PORTS = {"http": 80, "https": 443}


# ---------------------------------------------------------------------------
# Schema kernel - lock-step copy of lib/schema/parse.py + project.py
# ---------------------------------------------------------------------------


@dataclass
class _Schema:
    kind: str
    options: tuple = ()
    lo: int = None
    hi: int = None
    step: int = None


def _parse_schema(decl: str) -> _Schema:
    if not isinstance(decl, str) or not decl.strip():
        raise ValueError("empty schema declaration")

    parts = [p.strip() for p in decl.split(":")]
    kind = parts[0].strip().upper()

    if kind not in _KNOWN_KINDS:
        raise ValueError(f"unknown schema kind: {parts[0]!r}")

    if kind == "BOOL":
        if len(parts) != 1:
            raise ValueError(f"BOOL takes no arguments, got: {decl!r}")
        return _Schema(kind="BOOL")

    if kind == "DATE_DAY":
        if len(parts) != 1:
            raise ValueError(f"DATE_DAY takes no arguments, got: {decl!r}")
        return _Schema(kind="DATE_DAY")

    if kind == "ENUM":
        if len(parts) < 2 or not parts[1]:
            raise ValueError(f"ENUM requires options, got: {decl!r}")
        raw_options = ":".join(parts[1:])
        options = tuple(
            sorted({o.strip().lower() for o in raw_options.split(",") if o.strip()})
        )
        if not options:
            raise ValueError(f"ENUM requires at least one option, got: {decl!r}")
        return _Schema(kind="ENUM", options=options)

    if kind == "BAND":
        if len(parts) != 4:
            raise ValueError(f"BAND requires lo:hi:step, got: {decl!r}")
        lo, hi, step = _parse_ints(parts[1], parts[2], parts[3], decl_hint=decl)
        if step <= 0:
            raise ValueError(f"BAND step must be positive, got: {decl!r}")
        if hi <= lo:
            raise ValueError(f"BAND hi must be greater than lo, got: {decl!r}")
        if (hi - lo) % step != 0:
            raise ValueError(f"BAND range must be evenly divisible by step, got: {decl!r}")
        return _Schema(kind="BAND", lo=lo, hi=hi, step=step)

    if kind == "INT":
        if len(parts) != 3:
            raise ValueError(f"INT requires lo:hi, got: {decl!r}")
        lo, hi = _parse_ints(parts[1], parts[2], decl_hint=decl)
        if hi < lo:
            raise ValueError(f"INT hi must be >= lo, got: {decl!r}")
        return _Schema(kind="INT", lo=lo, hi=hi)

    raise ValueError(f"unhandled schema kind: {kind!r}")  # pragma: no cover


def _parse_ints(*raw, decl_hint):
    out = []
    for r in raw:
        try:
            out.append(int(r))
        except ValueError:
            raise ValueError(f"expected integer, got {r!r} in {decl_hint!r}")
    return tuple(out)


def _canonical_schema(s: _Schema) -> str:
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
    raise ValueError(f"cannot canonicalize unknown kind: {s.kind!r}")


def _legal_values(s: _Schema) -> list:
    if s.kind == "BOOL":
        return ["true", "false"]
    if s.kind == "ENUM":
        return list(s.options)
    if s.kind == "BAND":
        n_bands = (s.hi - s.lo) // s.step
        return [f"a number between {s.lo} and {s.hi} (bucketed in steps of {s.step}, {n_bands} bands)"]
    if s.kind == "INT":
        return [f"an integer between {s.lo} and {s.hi} inclusive"]
    if s.kind == "DATE_DAY":
        return ["a date in YYYY-MM-DD format"]
    raise ValueError(f"cannot enumerate unknown kind: {s.kind!r}")


def _project(schema: _Schema, raw: str):
    if raw is None:
        return (STATUS_SCHEMA_VIOLATION, "")
    if not isinstance(raw, str):
        raw = str(raw)

    stripped = raw.strip()
    if stripped.upper() == "UNAVAILABLE":
        return (STATUS_UNAVAILABLE, "")
    if not stripped:
        return (STATUS_SCHEMA_VIOLATION, "")

    if schema.kind == "BOOL":
        m = _BOOL_TOKEN_RE.search(stripped)
        if not m:
            return (STATUS_SCHEMA_VIOLATION, "")
        token = m.group(1).lower()
        if token in _BOOL_TRUE:
            return (STATUS_OK, "true")
        if token in _BOOL_FALSE:
            return (STATUS_OK, "false")
        return (STATUS_SCHEMA_VIOLATION, "")  # pragma: no cover

    if schema.kind == "ENUM":
        lowered = stripped.lower()
        if lowered in schema.options:
            return (STATUS_OK, lowered)
        for option in schema.options:
            if re.search(rf"\b{re.escape(option)}\b", lowered):
                return (STATUS_OK, option)
        return (STATUS_SCHEMA_VIOLATION, "")

    if schema.kind == "BAND":
        m = _NUMBER_RE.search(stripped)
        if not m:
            return (STATUS_SCHEMA_VIOLATION, "")
        try:
            value = float(m.group(0))
        except ValueError:
            return (STATUS_SCHEMA_VIOLATION, "")  # pragma: no cover
        clamped = min(max(value, schema.lo), schema.hi)
        band_index = int(clamped - schema.lo) // schema.step
        max_index = (schema.hi - schema.lo) // schema.step - 1
        band_index = min(band_index, max_index)
        return (STATUS_OK, str(band_index))

    if schema.kind == "INT":
        m = _INT_RE.search(stripped)
        if not m:
            return (STATUS_SCHEMA_VIOLATION, "")
        try:
            value = int(m.group(0))
        except ValueError:
            return (STATUS_SCHEMA_VIOLATION, "")  # pragma: no cover
        if value < schema.lo or value > schema.hi:
            return (STATUS_SCHEMA_VIOLATION, "")
        return (STATUS_OK, str(value))

    if schema.kind == "DATE_DAY":
        m = _DATE_RE.search(stripped)
        if not m:
            return (STATUS_SCHEMA_VIOLATION, "")
        try:
            parsed = date.fromisoformat(m.group(0))
        except ValueError:
            return (STATUS_SCHEMA_VIOLATION, "")
        return (STATUS_OK, parsed.isoformat())

    return (STATUS_SCHEMA_VIOLATION, "")


# ---------------------------------------------------------------------------
# Normalize kernel - lock-step copy of lib/normalize/*.py
# ---------------------------------------------------------------------------


def _strip_to_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = _DROP_BLOCK_RE.sub(" ", raw_html)
    text = _COMMENT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = _html_unescape(text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def _html_unescape(text: str) -> str:
    import html

    return html.unescape(text)


def _question_keywords_availability(question: str) -> set:
    words = _WORD_RE.findall((question or "").lower())
    return {w for w in words if w not in _STOPWORDS}


def _check_availability(status_code: int, body: str, question: str):
    if status_code == 429:
        return ("UNAVAILABLE", "RATE_LIMIT")
    if status_code >= 500:
        return ("UNAVAILABLE", "TRANSIENT")
    if status_code >= 400:
        return ("UNAVAILABLE", "EXTERNAL")

    text = _strip_to_text(body or "")
    lowered = text.lower()

    for marker in _BOT_WALL_MARKERS:
        if marker in lowered:
            return ("UNAVAILABLE", "BOT_WALL")

    if len(text) < PAYWALL_LENGTH_FLOOR:
        for marker in _PAYWALL_MARKERS:
            if marker in lowered:
                return ("UNAVAILABLE", "PAYWALL")

    if len(text) < MIN_EVIDENCE_CHARS:
        return ("UNAVAILABLE", "EMPTY")

    keywords = _question_keywords_availability(question or "")
    if keywords and not any(k in lowered for k in keywords):
        return ("UNAVAILABLE", "NO_OVERLAP")

    return ("READABLE", "")


def _redact_times(text: str) -> str:
    text = _REL_TIME_RE.sub("[REL_TIME]", text)
    text = _SUBDAY_TIME_RE.sub("[TIME]", text)
    return text


def _quantize_number(match) -> str:
    raw = match.group(0).replace(",", "")
    try:
        n = int(raw)
    except ValueError:
        return match.group(0)
    if n < 1000:
        return match.group(0)
    digits = len(str(n))
    sig_figs = 2
    factor = 10 ** (digits - sig_figs)
    quantized = round(n / factor) * factor
    return str(quantized)


def _quantize_numbers(text: str) -> str:
    return _QUANTIZE_NUMBER_RE.sub(_quantize_number, text)


def _question_keywords_normalize(question: str) -> list:
    words = _WORD_RE.findall((question or "").lower())
    seen = []
    for w in words:
        if w not in _STOPWORDS and w not in seen:
            seen.append(w)
    return seen


def _window(text: str, question: str) -> str:
    if len(text) <= MAX_EVIDENCE_CHARS:
        return text
    lowered = text.lower()
    anchor = None
    for kw in _question_keywords_normalize(question):
        idx = lowered.find(kw)
        if idx != -1:
            anchor = idx
            break
    if anchor is None:
        return text[:MAX_EVIDENCE_CHARS]
    start = max(0, anchor - _WINDOW_RADIUS)
    end = min(len(text), start + MAX_EVIDENCE_CHARS)
    start = max(0, end - MAX_EVIDENCE_CHARS)
    return text[start:end]


def _normalize(body: str, question: str) -> str:
    text = _strip_to_text(body or "")
    text = _redact_times(text)
    text = _quantize_numbers(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = _window(text, question or "")
    return text


# ---------------------------------------------------------------------------
# Key derivation - lock-step copy of lib/schema/keys.py
# ---------------------------------------------------------------------------


def _canonical_url(url: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()

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


def _compute_key(url: str, question: str, schema_decl: str) -> str:
    schema = _parse_schema(schema_decl)
    payload = "\x00".join(
        [_canonical_url(url), question.strip(), _canonical_schema(schema)]
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _compute_key_or_raise(url: str, question: str, schema_decl: str) -> str:
    """compute_key() wrapped with the [EXPECTED] error prefix. request_fact
    and the compute_key view both need a malformed schema to fail with the
    prefix intact - _compute_key itself stays a plain ValueError-raiser so
    it matches lib/schema/keys.veritas_key()'s off-chain behavior exactly
    for the parity test.
    """
    try:
        return _compute_key(url, question, schema_decl)
    except ValueError as e:
        raise gl.vm.UserError(f"{ERROR_EXPECTED} {e}")


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_prompt(question: str, schema: _Schema, evidence: str) -> str:
    legal = _legal_values(schema)
    legal_str = " or ".join(legal)
    return (
        "You are answering ONE question from the EVIDENCE below.\n"
        f"QUESTION: {question}\n"
        f"Legal answers, and nothing else: {legal_str}\n"
        "If the evidence does not contain enough information to answer, "
        "answer exactly: UNAVAILABLE\n"
        "Do not guess. Do not explain outside the JSON.\n"
        f"EVIDENCE:\n{evidence}\n\n"
        'Return JSON: {"answer": "<one legal value, or UNAVAILABLE>", '
        '"evidence_span": "<verbatim short quote from EVIDENCE supporting the answer, or empty string>"}'
    )


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


@allow_storage
@dataclass
class Fact:
    url: str
    question: str
    schema: str
    status: str
    answer: str
    fetched_at: u256
    fingerprint: str
    evidence_span: str
    resolve_count: u256
    last_error: str
    requester: Address


class Veritas(gl.Contract):
    facts: TreeMap[str, Fact]
    fact_keys: DynArray[str]
    total_resolves: u256
    total_unavailable: u256
    owner: Address

    def __init__(self):
        self.owner = gl.message.sender_address

    # -- views ---------------------------------------------------------

    @gl.public.view
    def compute_key(self, url: str, question: str, schema: str) -> str:
        return _compute_key_or_raise(url, question, schema)

    @gl.public.view
    def get_fact(self, key: str, max_age: u256) -> dict:
        if key not in self.facts:
            return {
                "status": STATUS_PENDING,
                "answer": "",
                "fetched_at": 0,
                "is_fresh": False,
                "evidence_span": "",
                "resolve_count": 0,
            }
        f = self.facts[key]
        now = int(datetime.now(timezone.utc).timestamp())
        is_fresh = (now - int(f.fetched_at)) <= int(max_age) and f.status == STATUS_OK
        return {
            "status": f.status,
            "answer": f.answer,
            "fetched_at": int(f.fetched_at),
            "is_fresh": is_fresh,
            "evidence_span": f.evidence_span,
            "resolve_count": int(f.resolve_count),
        }

    @gl.public.view
    def has_fresh(self, key: str, max_age: u256) -> bool:
        if key not in self.facts:
            return False
        f = self.facts[key]
        now = int(datetime.now(timezone.utc).timestamp())
        return f.status == STATUS_OK and (now - int(f.fetched_at)) <= int(max_age)

    @gl.public.view
    def stats(self) -> dict:
        return {
            "total_resolves": int(self.total_resolves),
            "total_unavailable": int(self.total_unavailable),
            "total_facts": len(self.fact_keys),
        }

    # -- writes ----------------------------------------------------------

    @gl.public.write
    def request_fact(self, url: str, question: str, schema: str) -> None:
        key = _compute_key_or_raise(url, question, schema)
        now = int(datetime.now(timezone.utc).timestamp())

        if key in self.facts:
            f = self.facts[key]
            if f.status == STATUS_OK and (now - int(f.fetched_at)) <= DEFAULT_MAX_AGE:
                return  # idempotent no-op: fresh answer already cached
            if f.status == STATUS_PENDING and (now - int(f.fetched_at)) <= PENDING_RETRY_WINDOW:
                return  # idempotent no-op: a resolution is already in flight
        else:
            self.fact_keys.append(key)
            self.facts[key] = Fact(
                url=url,
                question=question,
                schema=schema,
                status=STATUS_PENDING,
                answer="",
                fetched_at=u256(now),
                fingerprint="",
                evidence_span="",
                resolve_count=u256(0),
                last_error="",
                requester=gl.message.sender_address,
            )

        self._resolve(key, url, question, schema)

    @gl.public.write
    def refresh(self, key: str) -> None:
        if key not in self.facts:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} unknown fact key")
        f = self.facts[key]
        self._resolve(key, f.url, f.question, f.schema)

    # -- internal ----------------------------------------------------------

    def _resolve(self, key: str, url: str, question: str, schema_decl: str) -> None:
        try:
            schema = _parse_schema(schema_decl)
        except ValueError as e:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} {e}")

        def leader_fn():
            return _resolve_pipeline(url, question, schema)

        def validator_fn(leaders_res: gl.vm.Result) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                # The only error leader_fn can raise is [LLM_ERROR]
                # (malformed model JSON) - always disagree, forcing
                # validator rotation, per docs/ARCHITECTURE.md section 5.
                return False
            mine = leader_fn()
            theirs = leaders_res.calldata
            return mine["status"] == theirs["status"] and mine["value"] == theirs["value"]

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        now = int(datetime.now(timezone.utc).timestamp())
        old = self.facts[key]
        self.facts[key] = Fact(
            url=old.url,
            question=old.question,
            schema=old.schema,
            status=result["status"],
            answer=result["value"],
            fetched_at=u256(now),
            fingerprint=result.get("fingerprint", ""),
            evidence_span=result.get("span", ""),
            resolve_count=u256(int(old.resolve_count) + 1),
            last_error="",
            requester=old.requester,
        )

        self.total_resolves = u256(int(self.total_resolves) + 1)
        if result["status"] == STATUS_UNAVAILABLE:
            self.total_unavailable = u256(int(self.total_unavailable) + 1)


def _resolve_pipeline(url: str, question: str, schema: _Schema) -> dict:
    """The full leader-side resolution pipeline. Re-run independently by the
    validator inside validator_fn - see docs/ARCHITECTURE.md section 4.
    Every branch returns a value; only malformed LLM JSON raises.
    """
    try:
        resp = gl.nondet.web.request(url, method="GET")
        # NOTE: the field is `.status`, NOT `.status_code` - verified against
        # the actual installed SDK's genlayer/gl/nondet/web.py Response
        # dataclass, which disagrees with the public docs' HTTP-errors
        # example. See docs/FRICTION.md.
        status_code = resp.status
        body = (resp.body or b"").decode("utf-8", errors="replace")
    except Exception:
        return {"status": STATUS_UNAVAILABLE, "value": "", "fingerprint": "", "span": "FETCH_ERROR"}

    verdict, reason = _check_availability(status_code, body, question)
    if verdict != "READABLE":
        return {"status": STATUS_UNAVAILABLE, "value": "", "fingerprint": "", "span": reason}

    evidence = _normalize(body, question)
    prompt = _build_prompt(question, schema, evidence)

    out = gl.nondet.exec_prompt(prompt, response_format="json")
    if not isinstance(out, dict):
        raise gl.vm.UserError(f"{ERROR_LLM} non-dict LLM response: {type(out)}")

    raw_answer = str(out.get("answer", ""))
    span = str(out.get("evidence_span", ""))
    status, value = _project(schema, raw_answer)
    fingerprint = hashlib.sha256(evidence.encode("utf-8")).hexdigest()

    return {"status": status, "value": value, "fingerprint": fingerprint, "span": span}
