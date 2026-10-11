"""Deploy the guarded Brief A negotiation question repair candidate.

Runs after sourcing env.sh. Takes the 9/10 baseline candidate
(runs/build-20261011T131745Z-fc9e6e/candidate-0.workflow.json),
applies builder/repair_question_in_negotiate.py, validates, uploads as a new
workflow, and exports.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import freya
from builder.repair_question_in_negotiate import repair
from builder.validate import validate

SOURCE_DIR = ROOT / "runs/build-20261011T131745Z-fc9e6e"
SOURCE_FILE = SOURCE_DIR / "candidate-0.workflow.json"
OPENAPI_FILE = ROOT / "tools/openapi.json"
WORKSPACE = "ca6619f6-ed5e-432a-a491-e9dcf8797dec"


def main():
    if freya.workspace_id() != WORKSPACE:
        raise ValueError(f"Unexpected Freya workspace: {freya.workspace_id()}")
    if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
        raise ValueError("Phone model override detected")

    source = json.loads(SOURCE_FILE.read_text())
    candidate = repair(source)

    openapi = json.loads(OPENAPI_FILE.read_text())
    errors = validate(candidate, openapi)
    if errors:
        raise ValueError(f"Local validation rejected candidate: {errors}")

    if candidate.get("test_variables"):
        raise ValueError("Repaired candidate must not contain UI customer defaults")

    # Generate unique stamp & short hash
    now_utc = datetime.now(timezone.utc)
    stamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
    cand_str = json.dumps(candidate, sort_keys=True)
    short_hash = hashlib.sha256(cand_str.encode()).hexdigest()[:6]
    run_name = f"build-{stamp}-{short_hash}"

    out_dir = ROOT / "runs" / run_name
    out_dir.mkdir(parents=True, exist_ok=False)

    cand_path = out_dir / "candidate-0.workflow.json"
    cand_path.write_text(json.dumps(candidate, indent=2) + "\n")

    summary = {
        "run": run_name,
        "base_candidate": "build-20261011T131745Z-fc9e6e",
        "repair": "repair_question_in_negotiate",
        "created_at": stamp,
        "local_validation": "passed",
        "status": "pending_upload",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    # Platform dry-run
    wf_name = f"brief-a-repair-{stamp}"
    dry = freya.validate_workflow(wf_name, candidate)
    if dry.get("valid") is False:
        raise ValueError(f"Platform dry run rejected candidate: {dry}")
    summary["platform_validation"] = "passed"
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    # Create workflow
    ids = freya.create_workflow(wf_name, candidate)
    summary["workflow_id"] = ids["workflow_id"]
    summary["agent_id"] = ids["agent_id"]
    summary["status"] = "created"
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    # Export workflow
    export_path = out_dir / "workflow.export.json"
    freya.export_workflow(ids["workflow_id"], str(export_path))
    exported = json.loads(export_path.read_text())
    if exported["workflow"].get("test_variables"):
        export_path.unlink()
        raise ValueError("Candidate export unexpectedly contains UI defaults")

    summary["status"] = "exported"
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    result = {
        "run_name": run_name,
        "run_dir": str(out_dir),
        "workflow_id": ids["workflow_id"],
        "agent_id": ids["agent_id"],
        "phone_model": freya.AGENT_LLM["model"],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
