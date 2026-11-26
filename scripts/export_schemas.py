"""Export the artifact contracts (Pydantic models) as JSON Schemas into specifications/schemas/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import models  # noqa: E402
from core.config import ROOT  # noqa: E402

CONTRACTS = ["StructuredRequirement", "FeatureSpec", "AcceptanceCriterion", "ValidationReport", "TestScenarioSet",
             "TestCaseSet", "TestDataSet", "AutomationSpec", "ExecutionRun", "FailureAnalysisReport",
             "ChangeRecord", "ApprovalRecord"]

if __name__ == "__main__":
    out = ROOT / "specifications" / "schemas"
    out.mkdir(parents=True, exist_ok=True)
    for name in CONTRACTS:
        schema = getattr(models, name).model_json_schema()
        (out / f"{name}.schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
        print(f"wrote {name}.schema.json")
