"""Create a new guarded candidate and UI copy; never persist UI customer defaults."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import freya
from builder.repair_opening_and_security import repair
from builder.layout import arrange
from builder.validate import validate
from tools.arrange_brief_a_workflows import POSITIONS

WORKSPACE = "ca6619f6-ed5e-432a-a491-e9dcf8797dec"
DEMO = "86ca852f-de5d-4736-b785-7d6aac26c957"
SOURCE = ROOT / "runs/dispute-clarification-20261010T223223Z/workflow.json"
OPENAPI = ROOT / "tools/openapi.json"


def main():
    if freya.workspace_id() != WORKSPACE:
        raise ValueError("Unexpected workspace")
    if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
        raise ValueError("Phone model override")
    coordinates = {key: {"x": x, "y": y} for key, (x, y) in POSITIONS.items()}
    candidate = arrange(repair(json.loads(SOURCE.read_text())), coordinates)
    errors = validate(candidate, json.loads(OPENAPI.read_text()))
    if errors:
        raise ValueError("Local validation failed")
    if candidate.get("test_variables"):
        raise ValueError("Candidate contains UI defaults")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "runs" / ("opening-security-repair-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    (out / "workflow.json").write_text(json.dumps(candidate, indent=2) + "\n")
    state = {"source": str(SOURCE.relative_to(ROOT)), "created_at": stamp,
             "local_validation": "passed", "public_score": "not_run", "ui_test": "not_run", "candidates": []}

    def save():
        (out / "summary.json").write_text(json.dumps(state, indent=2) + "\n")

    save()
    name = "opening-security-repair-" + stamp
    dry = freya.validate_workflow(name, candidate)
    if dry.get("valid") is False:
        raise ValueError("Platform candidate validation failed")
    state["platform_validation"] = "passed"
    save()
    ids = freya.create_workflow(name, candidate)
    state["candidates"].append({"purpose": "candidate", **ids})
    save()
    freya.export_workflow(ids["workflow_id"], str(out / "workflow.export.json"))
    exported = json.loads((out / "workflow.export.json").read_text())
    if exported["workflow"].get("test_variables"):
        (out / "workflow.export.json").unlink()
        raise ValueError("Candidate export contains UI defaults")
    state["candidate_export"] = "workflow.export.json"
    save()

    demo = freya.api("GET", f"/api/v2/workflow/{DEMO}", workspaceId=WORKSPACE)["workflow"]["workflow"]
    defaults = demo.get("test_variables") or {}
    keys = ("customer_id", "first_name", "last_name", "title")
    if not all(isinstance(defaults.get(k), str) and defaults[k].strip() for k in keys):
        raise ValueError("Demo UI defaults incomplete")
    ui = json.loads(json.dumps(candidate))
    ui["test_variables"] = {key: defaults[key] for key in keys}
    ui["test_variables"]["now"] = datetime.now(ZoneInfo("Europe/Istanbul")).isoformat(timespec="minutes")
    ui_name = name + "-ui"
    ui_dry = freya.validate_workflow(ui_name, ui)
    if ui_dry.get("valid") is False:
        raise ValueError("Platform UI validation failed")
    ui_ids = freya.create_workflow(ui_name, ui)
    state["candidates"].append({"purpose": "ui_copy", **ui_ids})
    save()
    readback = freya.api("GET", f"/api/v2/workflow/{ui_ids['workflow_id']}", workspaceId=WORKSPACE)["workflow"]["workflow"]
    if readback.get("test_variables") != ui["test_variables"]:
        raise ValueError("UI defaults did not survive readback")
    state["ui_readback"] = "defaults_match"
    save()
    print(json.dumps({"out": str(out), "candidate": ids, "ui_copy": ui_ids,
                      "test_variable_keys": sorted(ui["test_variables"])}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("DEPLOYMENT_ERROR", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
