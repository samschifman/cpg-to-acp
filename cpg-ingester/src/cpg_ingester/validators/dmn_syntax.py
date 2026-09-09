"""Deterministic DMN syntax validation — XML, structure, and FEEL lints."""

import logging
import re
from collections import Counter
from io import BytesIO

import mlflow
from lxml import etree

logger = logging.getLogger(__name__)

# DMN 1.4 language (MODEL) namespace. We target DMN 1.4 at conformance level 3
# (see AGENTS.md); produced models must declare this as their xmlns. Note this is
# the *language* namespace — distinct from the per-model target `namespace=`
# attribute, which is a unique URI per model.
DMN_NAMESPACE = "https://www.omg.org/spec/DMN/20211108/MODEL/"
DMN_NS = {"dmn": DMN_NAMESPACE}

VALID_HIT_POLICIES = {
    "UNIQUE", "FIRST", "COLLECT", "ANY", "PRIORITY", "RULE ORDER", "OUTPUT ORDER",
}
VALID_TYPE_REFS = {
    "string", "number", "boolean", "date", "time", "dateTime", "duration", "Any",
}

_NUMBER = r"-?(?:\d+(?:\.\d+)?|\.\d+)"
_COMPARISON = rf"[<>]=?\s*{_NUMBER}"
_RANGE = rf"[\[(]\s*{_NUMBER}\s*\.\.\s*{_NUMBER}\s*[\])]"
_QUOTED_STRING = r'"(?:[^"\\]|\\.)*"'

FEEL_UNARY_PATTERNS = [
    re.compile(rf"^{_COMPARISON}$"),
    re.compile(rf"^{_RANGE}$"),
    re.compile(rf"^{_QUOTED_STRING}$"),
    re.compile(r"^(true|false)$"),
    re.compile(rf"^{_NUMBER}$"),
    re.compile(r"^-$"),
    re.compile(r"^null$"),
    re.compile(r"^(?:date|time|duration)\s*\(.*\)$"),
]

_FEEL_KEYWORDS = {
    "and", "or", "true", "false", "not", "for", "every", "some", "if", "then",
    "else", "function", "in", "null",
}
_FORBIDDEN_XML_CONTROLS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
_ENTITY_IN_CDATA = re.compile(r"&(?:lt|gt|amp);")


def _result(errors: list[str] | None = None,
            warnings: list[str] | None = None) -> tuple[list[str], list[str]]:
    return errors or [], warnings or []


def _normalized_name(value: str | None) -> str:
    return " ".join((value or "").split())


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _elements(root: etree._Element, name: str) -> list[etree._Element]:
    return root.xpath(f'.//*[local-name()="{name}"]')


def check_raw_xml(dmn_xml: str) -> tuple[list[str], list[str]]:
    """Check defects that XML parsing normalizes or rejects before tree traversal."""
    errors = []
    controls = sorted({ord(c) for c in _FORBIDDEN_XML_CONTROLS.findall(dmn_xml)})
    if controls:
        rendered = ", ".join(f"U+{code:04X}" for code in controls)
        errors.append(f"XML contains forbidden control character(s): {rendered}")

    for body in _CDATA.findall(dmn_xml):
        entities = sorted(set(_ENTITY_IN_CDATA.findall(body)))
        if entities:
            errors.append(
                "CDATA contains XML entities that FEEL will read literally: "
                + ", ".join(entities)
            )
    return _result(errors)


def check_ids_and_references(root: etree._Element) -> tuple[list[str], list[str]]:
    """Require unique IDs and resolvable local information requirements."""
    errors = []
    ids = [element.get("id") for element in root.xpath("//*[@id]")]
    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    for duplicate in duplicates:
        errors.append(f"Duplicate id '{duplicate}'")

    known_ids = set(ids)
    for requirement in _elements(root, "requiredDecision") + _elements(root, "requiredInput"):
        href = requirement.get("href", "")
        target = href[1:] if href.startswith("#") else ""
        if not target or target not in known_ids:
            errors.append(
                f"{_local_name(requirement)} href '{href}' does not resolve to an existing id"
            )
    return _result(errors)


def check_variable_names(root: etree._Element) -> tuple[list[str], list[str]]:
    """Require decision and inputData variables to repeat their parent's name."""
    errors = []
    parents = _elements(root, "decision") + _elements(root, "inputData")
    for parent in parents:
        variables = parent.xpath('./*[local-name()="variable"]')
        if not variables:
            continue
        parent_name = _normalized_name(parent.get("name"))
        variable_name = _normalized_name(variables[0].get("name"))
        if parent_name != variable_name:
            errors.append(
                f"{_local_name(parent)} '{parent.get('id', '?')}': variable name "
                f"'{variables[0].get('name', '')}' does not match parent name "
                f"'{parent.get('name', '')}'"
            )
    return _result(errors)


def check_input_expressions(root: etree._Element) -> tuple[list[str], list[str]]:
    """Require table input expressions to name a declared input or upstream decision."""
    errors = []
    upstream_names = set()
    for parent in _elements(root, "inputData") + _elements(root, "decision"):
        variables = parent.xpath('./*[local-name()="variable"]')
        if variables:
            upstream_names.add(_normalized_name(variables[0].get("name")))

    for expression in _elements(root, "inputExpression"):
        texts = expression.xpath('./*[local-name()="text"]')
        value = _normalized_name(texts[0].text if texts else "")
        if value not in upstream_names:
            errors.append(
                f"InputExpression '{expression.get('id', '?')}' text '{value}' does not "
                "match a declared inputData or decision variable name"
            )
    return _result(errors)


def _split_top_level(value: str, delimiter: str = ",") -> list[str]:
    parts = []
    start = 0
    depth = 0
    quoted = False
    escaped = False
    for index, char in enumerate(value):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == delimiter and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return parts


def _valid_boolean_function_expression(value: str) -> bool:
    """Recognize the function predicates present in the supported real corpus."""
    function = re.compile(rf"contains\s*\(\s*\?\s*,\s*{_QUOTED_STRING}\s*\)")
    remainder = function.sub("", value)
    remainder = re.sub(r"\b(?:and|or)\b", "", remainder)
    remainder = remainder.replace("(", "").replace(")", "")
    return "contains" in value and not remainder.strip()


def _valid_unary_test(value: str) -> bool:
    value = value.strip()
    if any(pattern.fullmatch(value) for pattern in FEEL_UNARY_PATTERNS):
        return True

    values = _split_top_level(value)
    if len(values) > 1:
        return all(_valid_unary_test(part) for part in values)

    if value.startswith("not(") and value.endswith(")"):
        return _valid_unary_test(value[4:-1]) or _valid_boolean_function_expression(value[4:-1])

    combined_comparisons = re.compile(
        rf"^{_COMPARISON}(?:\s+(?:and|or)\s+{_COMPARISON})+$"
    )
    return bool(combined_comparisons.fullmatch(value) or _valid_boolean_function_expression(value))


def check_feel_entries(root: etree._Element) -> tuple[list[str], list[str]]:
    """Lint unary tests and simple output literals without pretending to parse FEEL."""
    errors = []
    for entry in _elements(root, "inputEntry"):
        texts = entry.xpath('./*[local-name()="text"]')
        value = (texts[0].text or "").strip() if texts else ""
        if any(mark in value for mark in ("“", "”", "‘", "’")):
            errors.append(f"InputEntry '{entry.get('id', '?')}': smart quotes are not valid FEEL")
        elif value and not _valid_unary_test(value):
            errors.append(f"InputEntry '{entry.get('id', '?')}': unsupported FEEL unary test '{value}'")

    for table in _elements(root, "decisionTable"):
        output_types = [
            output.get("typeRef", "")
            for output in table.xpath('./*[local-name()="output"]')
        ]
        for rule in table.xpath('./*[local-name()="rule"]'):
            entries = rule.xpath('./*[local-name()="outputEntry"]')
            for index, entry in enumerate(entries):
                texts = entry.xpath('./*[local-name()="text"]')
                value = (texts[0].text or "").strip() if texts else ""
                type_ref = output_types[index] if index < len(output_types) else ""
                if any(mark in value for mark in ("“", "”", "‘", "’")):
                    errors.append(
                        f"OutputEntry '{entry.get('id', '?')}': smart quotes are not valid FEEL"
                    )
                elif value in {"True", "False", "TRUE", "FALSE"}:
                    errors.append(
                        f"OutputEntry '{entry.get('id', '?')}': FEEL booleans must be lowercase"
                    )
                elif type_ref == "string" and value and not re.fullmatch(_QUOTED_STRING, value):
                    if not re.match(r"^(?:if|for|some|every|let)\b", value):
                        errors.append(
                            f"OutputEntry '{entry.get('id', '?')}': string literal must be quoted"
                        )
    return _result(errors)


def check_type_refs(root: etree._Element) -> tuple[list[str], list[str]]:
    """Require typeRefs to be built-ins or locally declared item definitions."""
    errors = []
    local_types = {
        item.get("name", "") for item in _elements(root, "itemDefinition") if item.get("name")
    }
    allowed = VALID_TYPE_REFS | local_types
    for element in root.xpath("//*[@typeRef]"):
        type_ref = element.get("typeRef", "")
        if " " in type_ref:
            errors.append(f"{_local_name(element)} '{element.get('id', '?')}': typeRef contains spaces")
        elif type_ref not in allowed:
            errors.append(
                f"{_local_name(element)} '{element.get('id', '?')}': unknown typeRef '{type_ref}'"
            )
    return _result(errors)


def check_hit_policies(root: etree._Element) -> tuple[list[str], list[str]]:
    """Enforce PRIORITY output ordering and discourage order-dependent FIRST tables."""
    errors = []
    warnings = []
    for table in _elements(root, "decisionTable"):
        policy = table.get("hitPolicy", "")
        if policy == "PRIORITY":
            outputs = table.xpath('./*[local-name()="output"]')
            if any(not output.xpath('./*[local-name()="outputValues"]') for output in outputs):
                errors.append(
                    f"DecisionTable '{table.get('id', '?')}': PRIORITY requires outputValues "
                    "on every output"
                )
        elif policy == "FIRST":
            warnings.append(
                f"DecisionTable '{table.get('id', '?')}': FIRST is order-dependent; "
                "prefer PRIORITY or UNIQUE where possible"
            )
    return errors, warnings


def check_feel_names(root: etree._Element) -> tuple[list[str], list[str]]:
    """Reject names that conflict with FEEL keyword tokenization."""
    errors = []
    for element in root.xpath("//*[@name]"):
        name = _normalized_name(element.get("name"))
        lowered = name.lower()
        first = lowered.split(maxsplit=1)[0] if lowered else ""
        if " in " in f" {lowered} ":
            errors.append(
                f"{_local_name(element)} '{element.get('id', '?')}': name contains FEEL token 'in'"
            )
        if first in _FEEL_KEYWORDS:
            errors.append(
                f"{_local_name(element)} '{element.get('id', '?')}': "
                f"name starts with FEEL keyword '{first}'"
            )
    return _result(errors)


def _check_existing_structure(root: etree._Element) -> tuple[list[str], list[str]]:
    """Retain the original table-shape checks while the deeper lints are added."""
    errors = []
    decision_tables = root.findall(".//dmn:decisionTable", DMN_NS)
    if not decision_tables:
        return _result(["No decisionTable elements found"])

    for table in decision_tables:
        table_id = table.get("id", "unknown")
        hit_policy = table.get("hitPolicy")
        if not hit_policy:
            errors.append(f"DecisionTable '{table_id}': missing hitPolicy attribute")
        elif hit_policy not in VALID_HIT_POLICIES:
            errors.append(f"DecisionTable '{table_id}': invalid hitPolicy '{hit_policy}'")

        inputs = table.findall("dmn:input", DMN_NS)
        for input_column in inputs:
            expression = input_column.find("dmn:inputExpression", DMN_NS)
            if expression is not None and not expression.get("typeRef"):
                errors.append(
                    f"Input '{input_column.get('id', 'unknown')}': inputExpression missing typeRef"
                )

        outputs = table.findall("dmn:output", DMN_NS)
        if not outputs:
            errors.append(f"DecisionTable '{table_id}': no output columns")

        rules = table.findall("dmn:rule", DMN_NS)
        if not rules:
            errors.append(f"DecisionTable '{table_id}': no rules")
        for rule in rules:
            rule_id = rule.get("id", "unknown")
            input_entries = rule.findall("dmn:inputEntry", DMN_NS)
            output_entries = rule.findall("dmn:outputEntry", DMN_NS)
            if len(input_entries) != len(inputs):
                errors.append(
                    f"Rule '{rule_id}': has {len(input_entries)} inputEntries, "
                    f"expected {len(inputs)}"
                )
            if len(output_entries) != len(outputs):
                errors.append(
                    f"Rule '{rule_id}': has {len(output_entries)} outputEntries, "
                    f"expected {len(outputs)}"
                )
            for entry in input_entries:
                text = entry.find("dmn:text", DMN_NS)
                if text is None or not (text.text or "").strip():
                    errors.append(
                        f"Rule '{rule_id}', input '{entry.get('id', 'unknown')}': "
                        "empty text (use '-' for any)"
                    )
            for entry in output_entries:
                text = entry.find("dmn:text", DMN_NS)
                if text is None or not (text.text or "").strip():
                    errors.append(
                        f"Rule '{rule_id}', output '{entry.get('id', 'unknown')}': empty text"
                    )

    input_data = root.findall(".//dmn:inputData", DMN_NS)
    for element in input_data:
        variable = element.find("dmn:variable", DMN_NS)
        if variable is None:
            errors.append(f"InputData '{element.get('id', '?')}': missing variable element")
        elif not variable.get("typeRef"):
            errors.append(f"InputData '{element.get('id', '?')}': variable missing typeRef")

    for decision in root.findall(".//dmn:decision", DMN_NS):
        requirements = decision.findall("dmn:informationRequirement", DMN_NS)
        if not requirements and input_data:
            errors.append(
                f"Decision '{decision.get('id', '?')}': no informationRequirement elements"
            )
    return _result(errors)


@mlflow.trace(name="validate_dmn")
def validate_dmn(dmn_xml: str) -> tuple[list[str], list[str]]:
    """Return retry-triggering errors and non-blocking warnings for DMN XML."""
    errors, warnings = check_raw_xml(dmn_xml)
    try:
        tree = etree.parse(BytesIO(dmn_xml.encode("utf-8")))
    except etree.XMLSyntaxError as exc:
        errors.append(f"XML parse error: {exc}")
        return errors, warnings

    root = tree.getroot()
    namespace = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    if namespace != DMN_NAMESPACE:
        errors.append(f"Wrong namespace: expected '{DMN_NAMESPACE}', got '{namespace}'")

    checks = (
        _check_existing_structure,
        check_ids_and_references,
        check_variable_names,
        check_input_expressions,
        check_feel_entries,
        check_type_refs,
        check_hit_policies,
        check_feel_names,
    )
    for check in checks:
        check_errors, check_warnings = check(root)
        errors.extend(check_errors)
        warnings.extend(check_warnings)
    return errors, warnings


def validate_dmn_xml(dmn_xml: str) -> list[str]:
    """Return DMN validation errors; retained for existing callers."""
    errors, _ = validate_dmn(dmn_xml)
    return errors
