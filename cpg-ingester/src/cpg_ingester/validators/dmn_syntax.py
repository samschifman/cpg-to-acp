"""Deterministic DMN syntax validation — XML, namespace, structure, FEEL regex."""

import logging
import re
from io import BytesIO

from lxml import etree

logger = logging.getLogger(__name__)

DMN_NAMESPACE = "https://www.omg.org/spec/DMN/20191111/MODEL/"
DMN_NS = {"dmn": DMN_NAMESPACE}

VALID_HIT_POLICIES = {"UNIQUE", "FIRST", "COLLECT", "ANY", "PRIORITY", "RULE ORDER", "OUTPUT ORDER"}
VALID_TYPE_REFS = {"string", "number", "boolean", "date", "time", "dateTime", "duration", "Any"}

FEEL_UNARY_PATTERNS = [
    re.compile(r'^[<>]=?\s*\d'),               # >= 140, < 130
    re.compile(r'^\[?\(?\d+\.\.\d+[\]\)]?$'),  # [130..139], (0..100)
    re.compile(r'^"[^"]*"$'),                    # "Start medication"
    re.compile(r'^(true|false)$'),               # boolean
    re.compile(r'^\d+(\.\d+)?$'),                # plain number
    re.compile(r'^-$'),                          # any value
    re.compile(r'^null$'),                       # null
    re.compile(r'^not\s*\('),                    # not("excluded")
]


def validate_dmn_xml(dmn_xml: str) -> list[str]:
    """Validate DMN XML and return a list of error messages. Empty list = valid."""
    errors = []

    # 1. XML well-formedness
    try:
        tree = etree.parse(BytesIO(dmn_xml.encode("utf-8")))
    except etree.XMLSyntaxError as e:
        errors.append(f"XML parse error: {e}")
        return errors

    root = tree.getroot()

    # 2. DMN namespace check
    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    if ns != DMN_NAMESPACE:
        errors.append(f"Wrong namespace: expected '{DMN_NAMESPACE}', got '{ns}'")

    # 3. Find decision tables
    decision_tables = root.findall(".//dmn:decisionTable", DMN_NS)
    if not decision_tables:
        errors.append("No decisionTable elements found")
        return errors

    for dt in decision_tables:
        dt_id = dt.get("id", "unknown")

        # 4. Hit policy
        hit_policy = dt.get("hitPolicy")
        if not hit_policy:
            errors.append(f"DecisionTable '{dt_id}': missing hitPolicy attribute")
        elif hit_policy not in VALID_HIT_POLICIES:
            errors.append(f"DecisionTable '{dt_id}': invalid hitPolicy '{hit_policy}'")

        # 5. Input columns have typeRef
        inputs = dt.findall("dmn:input", DMN_NS)
        for inp in inputs:
            ie = inp.find("dmn:inputExpression", DMN_NS)
            if ie is not None:
                type_ref = ie.get("typeRef")
                if not type_ref:
                    inp_id = inp.get("id", "unknown")
                    errors.append(f"Input '{inp_id}': inputExpression missing typeRef")

        # 6. Output columns exist
        output_cols = dt.findall("dmn:output", DMN_NS)
        if not output_cols:
            errors.append(f"DecisionTable '{dt_id}': no output columns")

        # 7. Rules: correct number of entries, no empty cells
        num_inputs = len(inputs)
        num_outputs = len(output_cols)
        rules = dt.findall("dmn:rule", DMN_NS)

        if not rules:
            errors.append(f"DecisionTable '{dt_id}': no rules")

        for rule in rules:
            rule_id = rule.get("id", "unknown")
            input_entries = rule.findall("dmn:inputEntry", DMN_NS)
            output_entries = rule.findall("dmn:outputEntry", DMN_NS)

            if len(input_entries) != num_inputs:
                errors.append(
                    f"Rule '{rule_id}': has {len(input_entries)} inputEntries, expected {num_inputs}"
                )

            if len(output_entries) != num_outputs:
                errors.append(
                    f"Rule '{rule_id}': has {len(output_entries)} outputEntries, expected {num_outputs}"
                )

            # Check for empty text in entries
            for ie in input_entries:
                text_el = ie.find("dmn:text", DMN_NS)
                if text_el is None or not (text_el.text or "").strip():
                    ie_id = ie.get("id", "unknown")
                    errors.append(f"Rule '{rule_id}', input '{ie_id}': empty text (use '-' for any)")

            for oe in output_entries:
                text_el = oe.find("dmn:text", DMN_NS)
                if text_el is None or not (text_el.text or "").strip():
                    oe_id = oe.get("id", "unknown")
                    errors.append(f"Rule '{rule_id}', output '{oe_id}': empty text")

    # 8. InputData have variables with typeRef
    input_data_els = root.findall(".//dmn:inputData", DMN_NS)
    for id_el in input_data_els:
        var = id_el.find("dmn:variable", DMN_NS)
        if var is None:
            errors.append(f"InputData '{id_el.get('id', '?')}': missing variable element")
        elif not var.get("typeRef"):
            errors.append(f"InputData '{id_el.get('id', '?')}': variable missing typeRef")

    # 9. Decisions have informationRequirement
    decisions = root.findall(".//dmn:decision", DMN_NS)
    for dec in decisions:
        ir_els = dec.findall("dmn:informationRequirement", DMN_NS)
        if not ir_els and input_data_els:
            errors.append(f"Decision '{dec.get('id', '?')}': no informationRequirement elements")

    return errors
