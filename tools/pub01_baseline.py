"""Create a fresh starter workflow, run official PUB-01, save redacted evidence.

Run from kit root after loading env.sh: python3 tools/pub01_baseline.py
Never reruns or updates an existing workflow. An interrupted run must be inspected
using its candidate.json before starting another simulation.
"""
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import freya
import run_cases
from score import http


SECRETS = [os.environ[k] for k in ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY") if os.environ.get(k)]


def redact(text):
    for secret in SECRETS:
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r'(?i)(Bearer\s+)[^\s"\\]+', r'\1[REDACTED]', text)
    return text


def save(path, value):
    path.write_text(redact(json.dumps(value, indent=2, ensure_ascii=False)) + "\n")


class SafeOutput(io.TextIOBase):
    def __init__(self, target):
        self.target = target
    def write(self, text):
        self.target.write(redact(text))
        self.target.flush()
        return len(text)
    def flush(self):
        self.target.flush()


def main():
    for key in ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY"):
        if len(os.environ.get(key, "")) < 16:
            raise ValueError(f"Missing or too short: {key}")
    if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
        raise ValueError("Unexpected phone model override; preserve kit model")
    raw = (ROOT / "examples/base-agent.json").read_bytes()
    workflow = json.loads(raw)
    assert workflow["initial_node"] in workflow["nodes"]
    for node in workflow["nodes"].values():
        for transition in node.get("transitions", []):
            assert transition["target_node"] in workflow["nodes"]
    name = "baseline-pub01-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    out = ROOT / "results" / name
    out.mkdir(parents=True)
    state = {"candidate": name, "started_at": datetime.now(timezone.utc).isoformat(),
             "source": "examples/base-agent.json", "sha256": hashlib.sha256(raw).hexdigest(),
             "status": "creating"}
    save(out / "candidate.json", state)
    try:
        state.update(freya.create_workflow(name, workflow))
        state["status"] = "created"
        save(out / "candidate.json", state)
        print(json.dumps(state), flush=True)
        # The official runner writes customer_id (a session secret) to its --out.
        # Keep that raw file in a private temporary directory, then redact it.
        with tempfile.TemporaryDirectory(prefix="freya-pub01-") as tmp:
            result_path = Path(tmp) / "run.json"
            sys.argv = ["tools/run_cases.py", state["agent_id"], "--only", "PUB-01", "--out", str(result_path)]
            state["status"] = "testing"
            save(out / "candidate.json", state)
            with contextlib.redirect_stdout(SafeOutput(sys.stdout)):
                run_cases.main()
            result = json.loads(result_path.read_text())
            for row in result["rows"]:
                SECRETS.append(row["customer_id"])
            save(out / "run.json", result)
            state["passed"] = result["passed"]
            state["total"] = result["total"]
            state["simulation_id"] = result["simulation_id"]
            state["iteration_id"] = result["iteration_id"]
            state["status"] = "scored"
            save(out / "candidate.json", state)
            for row in result["rows"]:
                save(out / (row["id"] + "-ledger.json"), http("/v1/practice/ledger/" + row["customer_id"]))
                if row.get("call_id"):
                    save(out / (row["id"] + "-call.json"), freya.get_call(row["call_id"]))
        state["status"] = "complete"
    except Exception as exc:
        state["error"] = redact(str(exc))
        state["status"] = "error"
        raise
    finally:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        save(out / "candidate.json", state)
        print("Evidence:", out.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(redact(f"{type(exc).__name__}: {exc}"), file=sys.stderr)
        sys.exit(1)
