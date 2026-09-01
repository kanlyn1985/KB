# -*- coding: utf-8 -*-
from pathlib import Path

OUT = Path(r"E:\AI_Project\opencode_workspace\KB1\docs\architecture\decisions")
OUT.mkdir(parents=True, exist_ok=True)
DATE = "2026-09-01"

TEMPLATE = """# {title}

- Status: Proposed
- Date: {date}
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: {reqs}
- Related Data Model: {dm}
- Related ICD: {icd}
- Related V&V: {vv}

## Context

{context}

## Problem

{problem}

## Decision

{decision}

## Alternatives Considered

{alternatives}

## Rationale

{rationale}

## Consequences

{consequences}

## Rejected Alternatives

{rejected}

## Verification Impact

{verification}

## Change Impact

{change}

## References

{refs}
"""

def write(name, title, **kw):
    body = TEMPLATE.format(date=DATE, title=title, **kw)
    (OUT / name).write_text(body, encoding="utf-8", newline="\n")
    return name

BASE_REFS = """- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md"""