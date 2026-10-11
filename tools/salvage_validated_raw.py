"""Deploy one preserved raw builder candidate after a validator false positive.

Never retries an ambiguous create. Keeps the original failed builder trace intact.
"""
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya
from builder.layout import arrange
from builder.validate import validate
from tools.resume_validated_deploy import save


def main():
    run = Path(sys.argv[1]).resolve()
    status_path = run / "salvage-deployment.json"
    if status_path.exists():
        raise ValueError("Salvage already attempted; inspect status before retry")
    state = {"status": "starting", "create_attempted": False}
    save(status_path, state)
    try:
        original = json.loads((run / "validation-0.json").read_text())["errors"]
        expected = {f"nodes/{name}/pre_actions/0/post_process_code: avoid template braces in Python; read vars instead"
                    for name in ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent")}
        if set(original) != expected:
            raise ValueError("Original errors differ from known validator false positives")
        workflow = arrange(json.loads((run / "candidate-0.raw.txt").read_text()))
        spec = json.loads((run / "inputs/openapi.json").read_text())
        errors = validate(workflow, spec)
        save(run / "salvage-validation.json", {"errors": errors, "scope": "structure and OpenAPI only"})
        if errors:
            raise ValueError("Candidate fails corrected validator")
        save(run / "candidate-0.salvaged.workflow.json", workflow)
        if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
            raise ValueError("Phone model override detected")
        state["status"] = "dry_run"
        save(status_path, state)
        dry = freya.validate_workflow(run.name + "-salvaged", workflow)
        if isinstance(dry, dict) and dry.get("success") is False:
            raise ValueError("Platform dry run rejected candidate")
        save(run / "salvage-platform-validation.json", dry)
        state.update(status="creating", create_attempted=True)
        save(status_path, state)
        ids = freya.create_workflow(run.name + "-salvaged", workflow)
        save(run / "salvage-candidate.json", ids)
        state.update(status="created", **ids)
        save(status_path, state)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.json"
            freya.export_workflow(ids["workflow_id"], str(path))
            exported = json.loads(path.read_text())
        if exported.get("workflow_id") != ids["workflow_id"] or not exported.get("workflow", {}).get("nodes"):
            raise ValueError("Invalid platform export")
        raw = json.dumps(exported)
        for key, value in os.environ.items():
            if value and re.search(r"KEY|TOKEN|SECRET|PASSWORD", key, re.I) and value in raw:
                raise ValueError("Export contains credential; withheld")
        save(run / "salvage-workflow.export.json", exported)
        state["status"] = "exported"
        return 0
    except Exception as exc:
        state["error"] = f"{type(exc).__name__}: {exc}"
        state["status"] = "failed" if not state["create_attempted"] else "create_attempted_or_later"
        return 1
    finally:
        save(status_path, state)
        print("salvage deployment:", state["status"], flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
