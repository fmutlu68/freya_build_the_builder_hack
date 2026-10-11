"""Publish the guarded Brief A identity repair and a separate private UI copy.

Run after sourcing env.sh. The original candidate stays untouched. Only the
secret-free candidate is exported locally; the UI copy's customer_id remains on
the Freya platform and is never printed or saved by this script.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import freya
from builder.repair_identity_gate import repair
from builder.validate import validate

WORKSPACE = "ca6619f6-ed5e-432a-a491-e9dcf8797dec"
DEMO = "86ca852f-de5d-4736-b785-7d6aac26c957"
SOURCE = ROOT / "runs/build-20261010T211124Z-859ec3/candidate-0.workflow.json"
OPENAPI = ROOT / "tools/openapi.json"


def main():
    if freya.workspace_id() != WORKSPACE:
        raise ValueError("Unexpected Freya workspace")
    if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
        raise ValueError("Phone model override detected")
    source = json.loads(SOURCE.read_text())
    candidate = repair(source)
    errors = validate(candidate, json.loads(OPENAPI.read_text()))
    if errors:
        raise ValueError("Local validation rejected repaired workflow")
    if candidate.get("test_variables"):
        raise ValueError("Repaired candidate must not contain UI customer defaults")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "runs" / ("identity-gate-repair-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    (out / "workflow.json").write_text(json.dumps(candidate, indent=2) + "\n")
    state = {"source": str(SOURCE.relative_to(ROOT)), "created_at": stamp,
             "local_validation": "passed", "public_score": "not_run", "candidates": []}

    def save():
        (out / "summary.json").write_text(json.dumps(state, indent=2) + "\n")

    save()
    name = "identity-gate-repair-" + stamp
    dry = freya.validate_workflow(name, candidate)
    if dry.get("valid") is False:
        raise ValueError("Platform dry run rejected candidate")
    state["platform_validation"] = "passed"
    save()
    ids = freya.create_workflow(name, candidate)
    state["candidates"].append({"purpose": "repaired_candidate", **ids})
    save()
    freya.export_workflow(ids["workflow_id"], str(out / "workflow.export.json"))
    exported = json.loads((out / "workflow.export.json").read_text())
    if exported["workflow"].get("test_variables"):
        (out / "workflow.export.json").unlink()
        raise ValueError("Candidate export unexpectedly contains UI defaults")
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
        raise ValueError("Platform dry run rejected UI copy")
    ui_ids = freya.create_workflow(ui_name, ui)
    state["candidates"].append({"purpose": "ui_copy", **ui_ids})
    save()
    readback = freya.api("GET", f"/api/v2/workflow/{ui_ids['workflow_id']}", workspaceId=WORKSPACE)["workflow"]["workflow"]
    if readback.get("test_variables") != ui["test_variables"]:
        raise ValueError("UI defaults did not survive platform readback")
    state["ui_readback"] = "defaults_match"
    state["ui_test"] = "not_run"
    save()
    print(json.dumps({"out": str(out), "repaired_candidate": ids,
                      "ui_copy": ui_ids, "test_variable_keys": sorted(ui["test_variables"])}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("DEPLOYMENT_ERROR", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
