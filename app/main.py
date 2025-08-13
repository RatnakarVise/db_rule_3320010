from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import re
import json

app = FastAPI(
    title="ABAP CO-PA Remediator (SAP Note 3320010)"
)

# Regex for PAOBJNR initial check
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

def find_paobjnr_usage(txt: str):
    matches = []
    for m in PAOBJNR_INITIAL_RE.finditer(txt):
        full_stmt = m.group("full")
        var = m.group("var")
        negation = m.group("negation")
        is_negated = bool(negation)
        suggested = suggest_paobjnr_replacement(var, is_negated)
        matches.append({
            "full": full_stmt,
            "var": var,
            "negated": is_negated,
            "suggested_statement": suggested,
            "span": m.span("full")
        })
    return matches

def find_deprecated_cds_fields(txt: str):
    matches = []
    for m in CDS_FIELD_RE.finditer(txt):
        full_stmt = m.group("full")
        suggested = "ProfitabilitySegment_2"
        matches.append({
            "full": full_stmt,
            "suggested_statement": suggested,
            "span": m.span("full")
        })
    return matches

@app.post("/remediate-copa")
def remediate_copa(units: List[Unit]):
    results = []
    for u in units:
        src = u.code or ""

        # Match PAOBJNR initial checks
        paobjnr_matches = find_paobjnr_usage(src)

        # Match deprecated CDS field usage
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
