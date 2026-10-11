"""Arrange the current Brief A candidate and UI copy without changing their logic.

Run after sourcing env.sh. UI test defaults are kept only on the platform.
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import freya
from builder.layout import arrange

WORKSPACE = "ca6619f6-ed5e-432a-a491-e9dcf8797dec"
IDS = {"candidate": "90227d93-e026-408e-a9b2-9a21611686a5",
       "ui_copy": "8a4c5604-e57b-4d04-9bae-9b0de35e54c1"}
POSITIONS = {
    "initialize": (0, 0), "opening": (560, 0), "dob": (1120, 0),
    "verify_dob": (1680, 0), "phone": (2240, 0), "verify_phone": (2800, 0),
    "account": (3360, 0), "discussion": (3920, 0), "confirm": (4480, 0),
    "record": (5040, 0), "end": (6160, 0),
    "evaluate": (1680, 600), "action_result": (3360, 600),
    "callback": (1120, 1200), "schedule": (1680, 1200),
    "transfer": (3920, 1200), "abort": (560, 1200),
}


def without_positions(workflow):
    result = json.loads(json.dumps(workflow))
    result.pop("nodePositions", None)
    for node in result["nodes"].values():
        node.pop("position", None)
    if isinstance(result.get("agent_config"), dict):
        result["agent_config"] = {k: v for k, v in result["agent_config"].items() if v is not None}
    return result


def main():
    if freya.workspace_id() != WORKSPACE:
        raise ValueError("Unexpected workspace")
    if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
        raise ValueError("Phone model override")
    coordinates = {key: {"x": x, "y": y} for key, (x, y) in POSITIONS.items()}
    output = {}
    for label, workflow_id in IDS.items():
        original = freya.api("GET", f"/api/v2/workflow/{workflow_id}", workspaceId=WORKSPACE)["workflow"]["workflow"]
        arranged = arrange(original, coordinates)
        if without_positions(original) != without_positions(arranged):
            raise ValueError("Layout changed workflow logic")
        if all(original["nodes"][key].get("position") == point for key, point in coordinates.items()):
            versions = freya.api("GET", f"/api/v2/versions/workflow/{workflow_id}", workspaceId=WORKSPACE)["versions"]
            published = [v["versionNumber"] for v in versions if v.get("isPublished")]
            version = max(published) if published else None
        else:
            dry = freya.validate_workflow("layout-" + label, arranged)
            if dry.get("valid") is False:
                raise ValueError("Platform rejected layout")
            version = freya.update_workflow(workflow_id, arranged)
        readback = freya.api("GET", f"/api/v2/workflow/{workflow_id}", workspaceId=WORKSPACE)["workflow"]["workflow"]
        if any(readback["nodes"][key].get("position") != point for key, point in coordinates.items()):
            raise ValueError("Platform did not retain all positions")
        if without_positions(readback) != without_positions(original):
            raise ValueError("Platform readback changed non-layout fields")
        output[label] = {"workflow_id": workflow_id, "published_version": version,
                         "positioned_nodes": len(coordinates)}
        if label == "candidate":
            export_path = ROOT / "runs/dispute-clarification-20261010T223223Z/workflow.export.json"
            freya.export_workflow(workflow_id, str(export_path))
            if json.loads(export_path.read_text())["workflow"].get("test_variables"):
                export_path.unlink()
                raise ValueError("Candidate export contains UI defaults")
    print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print("LAYOUT_ERROR", str(exc), file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print("LAYOUT_ERROR", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
