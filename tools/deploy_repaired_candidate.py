"""Deploy limited repair candidate with relative and vague date handling."""

from datetime import datetime, timezone
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import freya
from builder.repair_relative_and_vague_dates import repair
from builder.validate import validate
from builder.layout import arrange


def main():
    if not os.environ.get("FREYA_API_KEY"):
        raise RuntimeError("FREYA_API_KEY missing")

    base_candidate_dir = ROOT / "runs" / "build-20261011T105306Z-47f058"
    wf_path = base_candidate_dir / "candidate-0.workflow.json"
    raw_wf = json.loads(wf_path.read_text())

    fixed_wf = arrange(repair(raw_wf))
    spec = json.loads((ROOT / "tools" / "openapi.json").read_text())
    errors = validate(fixed_wf, spec)
    if errors:
        raise ValueError(f"Local validation failed: {errors}")

    run_name = "build-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    out_dir = ROOT / "runs" / run_name
    out_dir.mkdir(parents=True, exist_ok=False)

    (out_dir / "candidate-0.workflow.json").write_text(json.dumps(fixed_wf, indent=2))

    # Platform dry-run
    print(f"Validating workflow on Freya platform: {run_name}...", flush=True)
    dry = freya.validate_workflow(run_name, fixed_wf)
    (out_dir / "platform-validation-0.json").write_text(json.dumps(dry, indent=2))
    print("Platform validation passed.", flush=True)

    # Create workflow
    print(f"Creating workflow: {run_name}...", flush=True)
    ids = freya.create_workflow(run_name, fixed_wf)
    print(f"Created: workflow_id={ids['workflow_id']}, agent_id={ids['agent_id']}", flush=True)

    candidate_info = {"name": run_name, **ids}
    (out_dir / "candidate.json").write_text(json.dumps(candidate_info, indent=2))

    # Export workflow
    export_path = out_dir / "workflow.export.json"
    print(f"Exporting workflow to {export_path}...", flush=True)
    freya.export_workflow(ids["workflow_id"], str(export_path))
    print("Export complete.", flush=True)

    summary = {
        "run": run_name,
        "base_candidate": "build-20261011T105306Z-47f058",
        "repair": "repair_relative_and_vague_dates",
        "workflow_id": ids["workflow_id"],
        "agent_id": ids["agent_id"],
        "status": "exported"
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Successfully deployed and recorded repaired candidate: {run_name}")


if __name__ == "__main__":
    main()
