"""Validate and deploy an existing candidate without regenerating it."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import freya
from builder.validate import validate


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--name-prefix", default="existing-candidate")
    args = parser.parse_args()
    if not os.environ.get("FREYA_API_KEY"):
        raise RuntimeError("FREYA_API_KEY missing")
    if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
        raise RuntimeError("phone agent model differs from experimental-5")

    candidate = args.candidate.resolve()
    workflow = json.loads(candidate.read_text())
    spec = json.loads((ROOT / "tools/openapi.json").read_text())
    errors = validate(workflow, spec)
    if errors:
        raise ValueError(f"Local validation failed: {errors}")

    name = f"{args.name_prefix}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    output = ROOT / "runs" / name
    output.mkdir(parents=True, exist_ok=False)
    write(output / "candidate.workflow.json", workflow)
    record = {
        "name": name,
        "source_candidate": str(candidate.relative_to(ROOT)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phone_model": freya.AGENT_LLM,
        "local_validation": "passed",
        "platform_validation": "pending",
        "deploy": "not_run",
        "export": "not_run",
    }
    write(output / "deployment.json", record)
    print(f"Output: {output}", flush=True)

    result = freya.validate_workflow(name, workflow)
    write(output / "platform-validation.json", result)
    record["platform_validation"] = "passed"
    write(output / "deployment.json", record)
    print("Platform validation passed", flush=True)

    ids = freya.create_workflow(name, workflow)
    record.update(ids)
    record["deploy"] = "created"
    write(output / "deployment.json", record)
    print(f"Created workflow_id={ids['workflow_id']} agent_id={ids['agent_id']}", flush=True)

    export_path = output / "workflow.export.json"
    freya.export_workflow(ids["workflow_id"], str(export_path))
    exported = json.loads(export_path.read_text())
    if exported.get("agent_id") != ids["agent_id"]:
        raise RuntimeError("exported agent ID differs from created agent ID")
    record["export"] = "complete"
    record["export_path"] = str(export_path.relative_to(ROOT))
    write(output / "deployment.json", record)
    print("Export complete", flush=True)


if __name__ == "__main__":
    main()
