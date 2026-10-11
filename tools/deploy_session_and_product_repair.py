"""Deploy combined Brief A fixes as a new candidate and private UI copy."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import freya
from builder.repair_closed_session import repair as repair_session
from builder.repair_product_uncertainty import repair as repair_product
from builder.validate import validate

WORKSPACE = "ca6619f6-ed5e-432a-a491-e9dcf8797dec"
UI_SOURCE = "eeb848b2-d455-4cc4-98ee-1720c6175665"
SOURCE = ROOT / "runs/opening-security-repair-20261010T224156Z/workflow.json"


def main():
    if freya.workspace_id() != WORKSPACE:
        raise ValueError("Unexpected workspace")
    if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
        raise ValueError("Phone model override")
    workflow = repair_product(repair_session(json.loads(SOURCE.read_text())))
    if validate(workflow, json.loads((ROOT / "tools/openapi.json").read_text())):
        raise ValueError("Local validation failed")
    if workflow.get("test_variables"):
        raise ValueError("Candidate contains UI defaults")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "runs" / ("session-product-repair-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    (out / "workflow.json").write_text(json.dumps(workflow, indent=2) + "\n")
    summary = {"source": str(SOURCE.relative_to(ROOT)), "created_at": stamp,
               "local_validation": "passed", "public_score": "not_run",
               "ui_test": "not_run", "candidates": []}

    def save():
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    save()
    name = "session-product-repair-" + stamp
    if freya.validate_workflow(name, workflow).get("valid") is False:
        raise ValueError("Platform candidate validation failed")
    summary["platform_validation"] = "passed"
    save()
    ids = freya.create_workflow(name, workflow)
    summary["candidates"].append({"purpose": "candidate", **ids})
    save()
    freya.export_workflow(ids["workflow_id"], str(out / "workflow.export.json"))
    exported = json.loads((out / "workflow.export.json").read_text())
    if exported["workflow"].get("test_variables"):
        (out / "workflow.export.json").unlink()
        raise ValueError("Candidate export contains UI defaults")
    summary["candidate_export"] = "workflow.export.json"
    save()

    current = freya.api("GET", f"/api/v2/workflow/{UI_SOURCE}", workspaceId=WORKSPACE)["workflow"]["workflow"]
    defaults = current.get("test_variables") or {}
    if not all(defaults.get(k) for k in ("customer_id", "first_name", "last_name", "title")):
        raise ValueError("UI defaults missing")
    ui = json.loads(json.dumps(workflow))
    ui["test_variables"] = {k: defaults[k] for k in ("customer_id", "first_name", "last_name", "title")}
    ui["test_variables"]["now"] = datetime.now(ZoneInfo("Europe/Istanbul")).isoformat(timespec="minutes")
    if freya.validate_workflow(name + "-ui", ui).get("valid") is False:
        raise ValueError("Platform UI validation failed")
    ui_ids = freya.create_workflow(name + "-ui", ui)
    summary["candidates"].append({"purpose": "ui_copy", **ui_ids})
    save()
    readback = freya.api("GET", f"/api/v2/workflow/{ui_ids['workflow_id']}", workspaceId=WORKSPACE)["workflow"]["workflow"]
    if readback.get("test_variables") != ui["test_variables"]:
        raise ValueError("UI defaults changed")
    summary["ui_readback"] = "defaults_match"
    save()
    print(json.dumps({"out": str(out), "candidate": ids, "ui_copy": ui_ids,
                      "positioned_nodes": sum(bool(n.get("position")) for n in workflow["nodes"].values())}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("DEPLOYMENT_ERROR", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
