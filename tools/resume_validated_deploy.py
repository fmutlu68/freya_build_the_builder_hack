"""Resume one locally validated builder candidate after a transient dry-run error.

Never retries an ambiguous create call. Keeps the original builder trace intact.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya
from builder.validate import validate


def save(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    content = json.dumps(data, indent=2)
    for key, value in os.environ.items():
        if value and re.search(r"KEY|TOKEN|SECRET|PASSWORD", key, re.I):
            content = content.replace(value, "[REDACTED]")
    content = re.sub(r"\bfak_[A-Za-z0-9_-]+", "[REDACTED]", content)
    tmp.write_text(content + "\n")
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--attempt", type=int, default=0)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    status_path = run / "deployment-resume.json"
    if status_path.exists():
        prior = json.loads(status_path.read_text())
        if prior.get("create_attempted") or prior.get("status") in {"created", "exported"}:
            parser.error("Create may already have run; inspect platform before retrying")
    state = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "starting"}
    save(status_path, state)
    try:
        summary = json.loads((run / "summary.json").read_text())
        if summary.get("status") != "failed" or summary.get("candidates"):
            raise ValueError("Run is not a failed pre-create candidate")
        if summary.get("error", "").find("POST /api/v2/workflow -> 504") < 0:
            raise ValueError("Original failure was not the expected dry-run 504")
        validation = json.loads((run / f"validation-{args.attempt}.json").read_text())
        if validation.get("errors"):
            raise ValueError("Candidate did not pass local validation")
        workflow = json.loads((run / f"candidate-{args.attempt}.workflow.json").read_text())
        spec = json.loads((run / "inputs" / "openapi.json").read_text())
        errors = validate(workflow, spec)
        if errors:
            raise ValueError("Candidate fails current validator: " + repr(errors[:3]))
        if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
            raise ValueError("Phone model override detected")
        state["status"] = "dry_run"
        save(status_path, state)
        dry = freya.validate_workflow(summary["run"], workflow)
        if isinstance(dry, dict) and dry.get("success") is False:
            raise ValueError("Platform dry run rejected candidate")
        save(run / "platform-validation-resume.json", dry)
        state["status"] = "creating"
        state["create_attempted"] = True
        save(status_path, state)
        ids = freya.create_workflow(summary["run"], workflow)
        # Persist IDs before any export attempt. Never repeat an ambiguous create.
        save(run / "candidate-resume.json", {"name": summary["run"], **ids})
        state.update(status="created", **ids)
        save(status_path, state)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "export.json"
            freya.export_workflow(ids["workflow_id"], str(path))
            exported = json.loads(path.read_text())
        if exported.get("workflow_id") != ids["workflow_id"] or not exported.get("workflow", {}).get("nodes"):
            raise ValueError("Invalid/incomplete platform export")

        def check(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if re.fullmatch(r"api_?key|authorization|access_?token|secret", key, re.I) and child:
                        raise ValueError("Platform export contains credentials; withheld")
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(exported)
        raw = json.dumps(exported)
        for key, value in os.environ.items():
            if value and re.search(r"KEY|TOKEN|SECRET|PASSWORD", key, re.I) and value in raw:
                raise ValueError("Platform export contains a known credential; withheld")
        save(run / "workflow.export.resume.json", exported)
        state["status"] = "exported"
        state["export"] = "workflow.export.resume.json"
        return 0
    except Exception as exc:
        state["error"] = f"{type(exc).__name__}: {exc}"
        if state["status"] != "created":
            state["status"] = "failed"
        return 1
    finally:
        state["ended_at"] = datetime.now(timezone.utc).isoformat()
        save(status_path, state)
        print("deployment resume status:", state["status"], flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
