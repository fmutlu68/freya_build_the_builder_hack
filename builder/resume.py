"""Validate, deploy and export a Codex-written artifact after a lost final response.

This resumes only platform work. The supplied source run remains the real model
session and its event log remains the generation trace. No workflow is edited.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from builder.layout import arrange
from builder.validate import validate
import freya


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--artifact", default="codex-workflow.local.json")
    parser.add_argument("--out", type=Path, default=Path("runs"))
    args = parser.parse_args(argv)
    source = args.source_run.resolve()
    artifact = (source / args.artifact).resolve()
    if source not in artifact.parents:
        parser.error("artifact must be inside source run")
    trace = source / "codex-0.events.jsonl"
    spec_file = source / "inputs/openapi.json"
    if not all(path.is_file() for path in (artifact, trace, spec_file)):
        parser.error("source run artifact, real Codex trace, or effective OpenAPI missing")
    events = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
    if not any(event.get("type") == "item.completed" and
               "workflow.local.json" in str(event.get("item", {}).get("command", ""))
               for event in events):
        parser.error("Codex trace does not record the workflow artifact")
    if (source / "candidate.json").exists():
        parser.error("source run already created a candidate; never duplicate an ambiguous create")
    spec = json.loads(spec_file.read_text())
    workflow = arrange(json.loads(artifact.read_text()))
    errors = validate(workflow, spec)
    if errors:
        parser.error("candidate failed structural/OpenAPI validation: " + json.dumps(errors))
    if not os.environ.get("FREYA_API_KEY"):
        parser.error("FREYA_API_KEY missing")
    if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
        parser.error("phone model override detected")
    name = "Freya builder resume " + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out.resolve() / ("resume-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    out.mkdir(parents=True)
    state = {"status": "validated_locally", "started_at": timestamp(), "source_run": str(source),
             "source_artifact": str(artifact), "artifact_sha256": digest(artifact),
             "source_trace": str(trace), "trace_sha256": digest(trace),
             "effective_openapi_sha256": digest(spec_file), "workflow_name": name,
             "candidate": None}
    save(out / "summary.json", state)
    save(out / "candidate.workflow.json", workflow)
    try:
        dry = freya.validate_workflow(name, workflow)
        if isinstance(dry, dict) and dry.get("success") is False:
            raise RuntimeError("platform dryRun rejected")
        save(out / "platform-validation.json", dry)
        state["status"] = "validated_on_platform"
        save(out / "summary.json", state)
        ids = freya.create_workflow(name, workflow)  # Never auto-retry an ambiguous create.
        state["candidate"] = ids
        state["status"] = "created"
        save(out / "candidate.json", {"name": name, **ids})
        save(out / "summary.json", state)
        with tempfile.TemporaryDirectory(prefix="freya-export-") as temporary:
            export = Path(temporary) / "workflow.export.json"
            freya.export_workflow(ids["workflow_id"], str(export))
            raw_export = export.read_text()
        payload = json.loads(raw_export)
        if payload.get("workflow_id") != ids["workflow_id"] or not payload.get("workflow", {}).get("nodes"):
            raise ValueError("invalid/incomplete platform export")
        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if re.fullmatch(r"api_?key|authorization|access_?token|secret", key, re.I) and item:
                        raise ValueError("platform export contains credentials; withheld")
                    check(item)
            elif isinstance(value, list):
                for item in value: check(item)
        check(payload)
        if os.environ["FREYA_API_KEY"] in raw_export:
            raise ValueError("platform export contains workspace key; withheld")
        save(out / "workflow.export.json", payload)
        state["status"] = "exported"
        state["ended_at"] = timestamp()
        save(out / "summary.json", state)
        print(json.dumps({"status": state["status"], "run": str(out), **ids}))
        return 0
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
        state["ended_at"] = timestamp()
        save(out / "summary.json", state)
        print(json.dumps({"status": "failed", "run": str(out), "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
