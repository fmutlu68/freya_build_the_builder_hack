"""Publish the semantic opening repair on the two untested v1 workflows."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import freya
from builder.layout import arrange
from builder.repair_opening_and_security import repair
from builder.validate import validate
from tools.arrange_brief_a_workflows import POSITIONS

WORKSPACE = "ca6619f6-ed5e-432a-a491-e9dcf8797dec"
OUT = ROOT / "runs/opening-security-repair-20261010T224156Z"
SOURCE = ROOT / "runs/dispute-clarification-20261010T223223Z/workflow.json"
IDS = {"candidate": "c6eec2ca-15d4-4222-9900-17a656f900e2",
       "ui_copy": "eeb848b2-d455-4cc4-98ee-1720c6175665"}


def main():
    if freya.workspace_id() != WORKSPACE:
        raise ValueError("Unexpected workspace")
    coordinates = {key: {"x": x, "y": y} for key, (x, y) in POSITIONS.items()}
    candidate = arrange(repair(json.loads(SOURCE.read_text())), coordinates)
    if validate(candidate, json.loads((ROOT / "tools/openapi.json").read_text())):
        raise ValueError("Local validation failed")
    if candidate.get("test_variables"):
        raise ValueError("Candidate contains UI defaults")
    (OUT / "workflow.json").write_text(json.dumps(candidate, indent=2) + "\n")
    result = {}
    for purpose, workflow_id in IDS.items():
        current = freya.api("GET", f"/api/v2/workflow/{workflow_id}", workspaceId=WORKSPACE)["workflow"]["workflow"]
        workflow = json.loads(json.dumps(candidate))
        if purpose == "ui_copy":
            defaults = current.get("test_variables") or {}
            if not all(defaults.get(key) for key in ("customer_id", "first_name", "last_name", "title", "now")):
                raise ValueError("UI defaults missing")
            workflow["test_variables"] = defaults
        dry = freya.validate_workflow("semantic-opening-" + purpose, workflow)
        if dry.get("valid") is False:
            raise ValueError("Platform validation failed for " + purpose)
        version = freya.update_workflow(workflow_id, workflow)
        readback = freya.api("GET", f"/api/v2/workflow/{workflow_id}", workspaceId=WORKSPACE)["workflow"]["workflow"]
        if purpose == "ui_copy" and readback.get("test_variables") != defaults:
            raise ValueError("UI defaults changed")
        if purpose == "candidate":
            freya.export_workflow(workflow_id, str(OUT / "workflow.export.json"))
            if json.loads((OUT / "workflow.export.json").read_text())["workflow"].get("test_variables"):
                (OUT / "workflow.export.json").unlink()
                raise ValueError("Candidate export contains UI defaults")
        result[purpose] = {"workflow_id": workflow_id, "published_version": version,
                           "positioned_nodes": sum(bool(n.get("position")) for n in readback["nodes"].values())}
    summary_path = OUT / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["semantic_opening_update"] = result
    summary["ui_test"] = "not_run"
    summary["public_score"] = "not_run"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("PUBLISH_ERROR", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
