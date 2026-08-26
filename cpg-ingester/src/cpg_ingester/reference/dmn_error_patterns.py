"""Known DMN validation/compile error patterns and their targeted fixes.

When the syntax validator or the decision engine rejects a generated model, the
raw error is often terse. Matching it against a known pattern lets the creator
receive a concrete "here is the cause and the fix" hint on retry instead of just
the error text — which measurably shortens the repair loop.

This file is LIVING. Whenever a validator or compile error appears that no entry
here matches, add a new ``ErrorPattern`` for it:

    ErrorPattern(
        match="substring or regex found in the error text",
        cause="why the engine/validator rejected it",
        fix="the concrete change the creator should make",
        regex=True,  # omit for a plain case-insensitive substring match
    )

Keep ``match`` specific enough not to collide with unrelated errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorPattern:
    match: str
    cause: str
    fix: str
    regex: bool = False


# Seeded from the known failure classes: unescaped operators, FEEL name
# mismatches, missing structure, and duplicate identifiers.
ERROR_PATTERNS: list[ErrorPattern] = [
    ErrorPattern(
        match="XML parse error",
        cause="A raw <, > or & in a FEEL expression breaks XML well-formedness.",
        fix="Escape operators (&lt; &gt; &amp;) or wrap the FEEL text in a "
            "<![CDATA[ ... ]]> section. Never leave a bare < or & in element text.",
    ),
    ErrorPattern(
        match="Wrong namespace",
        cause="The definitions element uses the wrong DMN MODEL namespace URI.",
        fix="Use the exact DMN MODEL namespace URI required by this project on "
            "the root <definitions> element.",
    ),
    ErrorPattern(
        match="missing hitPolicy",
        cause="A decisionTable has no hitPolicy attribute.",
        fix="Add a hitPolicy attribute (UNIQUE, FIRST, PRIORITY, or COLLECT) to "
            "every decisionTable.",
    ),
    ErrorPattern(
        match="missing typeRef",
        cause="An inputExpression or variable has no typeRef.",
        fix="Give every inputExpression and variable a typeRef "
            "(number, string, or boolean).",
    ),
    ErrorPattern(
        match=r"(inputEntries|outputEntries), expected",
        regex=True,
        cause="A rule has a different number of entries than the table has columns.",
        fix="Emit exactly one inputEntry per <input> column and one outputEntry "
            "per <output> column in every rule. Use '-' for any-value cells.",
    ),
    ErrorPattern(
        match="empty text",
        cause="A rule entry has empty <text>.",
        fix="Every inputEntry/outputEntry needs non-empty text; use '-' for an "
            "any-value input cell.",
    ),
    ErrorPattern(
        match="no informationRequirement",
        cause="A decision does not link to the inputData it consumes.",
        fix="Add an <informationRequirement> with <requiredInput href=\"#...\"/> "
            "to the decision for each inputData it uses.",
    ),
    ErrorPattern(
        match="missing variable element",
        cause="An inputData has no <variable> child.",
        fix="Give every inputData a <variable> child whose name matches the "
            "inputData name and carries a typeRef.",
    ),
    # Decision-engine (Drools/Kogito) compile errors — surfaced via the compile
    # check, not the local syntax validator.
    ErrorPattern(
        match=r"unable to (resolve|find)|not (found|resolved)|no such|unknown (variable|input)",
        regex=True,
        cause="A FEEL inputExpression references a name the engine cannot bind.",
        fix="Make each <input><inputExpression><text> match a declared "
            "inputData/variable @name (or an upstream decision variable) exactly, "
            "character for character.",
    ),
    ErrorPattern(
        match=r"duplicate",
        regex=True,
        cause="Two elements share the same id (ids must be unique per document).",
        fix="Give every element a unique id; the definitions @id must differ from "
            "all others.",
    ),
]


def match_error_patterns(errors: list[str]) -> list[ErrorPattern]:
    """Return the known patterns whose match appears in any of ``errors``."""
    hits: list[ErrorPattern] = []
    for pattern in ERROR_PATTERNS:
        for err in errors:
            text = err or ""
            if pattern.regex:
                found = re.search(pattern.match, text, re.IGNORECASE)
            else:
                found = pattern.match.lower() in text.lower()
            if found:
                hits.append(pattern)
                break
    return hits


def format_error_pattern_hints(errors: list[str]) -> str:
    """Render matched patterns as feedback lines, or '' if none match."""
    hits = match_error_patterns(errors)
    if not hits:
        return ""
    lines = [f"- Known error pattern: {p.cause} Fix: {p.fix}" for p in hits]
    return "\n".join(lines)
