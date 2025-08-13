from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import re
import json

app = FastAPI(
    title="ABAP CO-PA Remediator (SAP Note 3320010)"
)

# Regex to match "IS INITIAL"/"IS NOT INITIAL" expressions
PAOBJNR_INITIAL_RE = re.compile(
    r"""
    (?P<full>
        (?P<var>\w+)
        \s+
        IS
        \s+
        (?P<negation>NOT\s+)?INITIAL
    )
    """,
    re.IGNORECASE | re.VERBOSE
)

# Regex to find "DATA: var_name TYPE rkeobjnr." declarations
DATA_DECL_RE = re.compile(
    r"""
    \bDATA:
    \s*
    (?P<var>\w+)
    \s+
    TYPE
    \s+
    (?P<type>\w+)
    \s*
    [\.\,]?
    """,
    re.IGNORECASE | re.VERBOSE
)

# Regex to find deprecated CDS field: ProfitabilitySegment
CDS_FIELD_RE = re.compile(
    r"""
    (?P<full>
        \bProfitabilitySegment\b
    )
    """,
    re.IGNORECASE | re.VERBOSE
)

class Unit(BaseModel):
    pgm_name: str
    inc_name: str
    type: str
    name: Optional[str] = None
    class_implementation: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    code: Optional[str] = ""

def suggest_paobjnr_replacement(var: str, is_negated: bool) -> str:
    return f"cl_fco_copa_paobjnr=>is_initial( {var} ) = {'abap_false' if is_negated else 'abap_true'}"

def extract_variable_types(code: str) -> dict:
    var_types = {}
    for m in DATA_DECL_RE.finditer(code):
        var_name = m.group("var").lower()
        var_type = m.group("type").lower()
        var_types[var_name] = var_type
    return var_types

def find_paobjnr_usage(txt: str, var_types: dict):
    matches = []
    for m in PAOBJNR_INITIAL_RE.finditer(txt):
        var = m.group("var")
        var_lower = var.lower()
        var_type = var_types.get(var_lower)

        # Skip if variable type is not RKEOBJNR
        if var_type != "rkeobjnr":
            continue

        is_negated = bool(m.group("negation"))
        suggested = suggest_paobjnr_replacement(var, is_negated)

        matches.append({
            "full": m.group("full"),
            "var": var,
            "negated": is_negated,
            "suggested_statement": suggested,
            "span": m.span("full")
        })
    return matches

def find_deprecated_cds_fields(txt: str):
    matches = []
    for m in CDS_FIELD_RE.finditer(txt):
        matches.append({
            "full": m.group("full"),
            "suggested_statement": "ProfitabilitySegment_2",
            "span": m.span("full")
        })
    return matches

@app.post("/remediate-copa")
def remediate_copa(units: List[Unit]):
    results = []

    for u in units:
        src = u.code or ""

        # Extract variable types from declarations
        var_types = extract_variable_types(src)

        # Find uses of IS INITIAL / IS NOT INITIAL for variables typed as rkeobjnr
        paobjnr_matches = find_paobjnr_usage(src, var_types)

        # Find deprecated CDS field usage
        cds_field_matches = find_deprecated_cds_fields(src)

        metadata = []

        for m in paobjnr_matches:
            metadata.append({
                "type": "PAOBJNR_CHECK",
                "table": "None",
                "target_type": "None",
                "target_name": "None",
                "start_char_in_unit": m["span"][0],
                "end_char_in_unit": m["span"][1],
                "used_fields": [m["var"]],
                "ambiguous": False,
                "suggested_statement": m["suggested_statement"],
                "suggested_fields": None
            })

        for m in cds_field_matches:
            metadata.append({
                "type": "CDS_FIELD_REPLACEMENT",
                "table": "None",
                "target_type": "CDS_VIEW",
                "target_name": "Unknown",
                "start_char_in_unit": m["span"][0],
                "end_char_in_unit": m["span"][1],
                "used_fields": ["ProfitabilitySegment"],
                "ambiguous": False,
                "suggested_statement": m["suggested_statement"],
                "suggested_fields": ["ProfitabilitySegment_2"]
            })

        obj = json.loads(u.model_dump_json())
        obj["copa_usage"] = metadata
        results.append(obj)

    return results
