"""Wait for one builder run, then score PUB-04 and (if it passes) Brief A.

The builder and this watcher have separate deadlines. Results remain in the
builder run directory; a failed build never starts a simulation.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def write(path, state):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(path)


def score(run_dir, agent_id, label, options, timeout, state, state_path):
    out = run_dir / f"{label}.json"
    log = run_dir / f"{label}.log"
    state["phase"] = label
    state["tests"].append({"label": label, "started_at": timestamp(), "result": str(out)})
    write(state_path, state)
    cmd = [sys.executable, "-u", str(ROOT / "tools" / "run_cases.py"), agent_id,
           *options, "--out", str(out)]
    with log.open("w") as stream:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise TimeoutError(f"{label} exceeded {timeout} seconds")
    if code:
        raise RuntimeError(f"{label} runner exited {code}; see {log}")
    result = json.loads(out.read_text())
    entry = state["tests"][-1]
    entry.update({"ended_at": timestamp(), "passed": result["passed"],
                  "total": result["total"], "log": str(log)})
    write(state_path, state)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--wait-seconds", type=int, default=1200)
    parser.add_argument("--test-seconds", type=int, default=1800)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    state_path = run_dir / "auto-test-status.json"
    state = {"started_at": timestamp(), "phase": "waiting_for_export", "tests": []}
    write(state_path, state)
    try:
        deadline = time.monotonic() + args.wait_seconds
        while True:
            summary = json.loads((run_dir / "summary.json").read_text())
            status = summary.get("status")
            if status == "exported":
                break
            if status in {"failed", "blocked_deployment", "watchdog_terminated"}:
                state["phase"] = "build_failed_no_test"
                state["build_status"] = status
                return 0
            if time.monotonic() >= deadline:
                raise TimeoutError("Builder did not finish within watcher deadline")
            time.sleep(10)
        export = run_dir / "workflow.export.json"
        candidate = json.loads((run_dir / "candidate.json").read_text())
        if not export.is_file() or not candidate.get("agent_id"):
            raise ValueError("Export or agent ID missing despite exported status")
        state["agent_id"] = candidate["agent_id"]
        result = score(run_dir, candidate["agent_id"], "pub04-run1",
                       ["--only", "PUB-04"], args.test_seconds, state, state_path)
        if result["total"] == 1 and result["passed"] == 1:
            score(run_dir, candidate["agent_id"], "briefA-run1",
                  ["--brief", "A"], args.test_seconds, state, state_path)
            state["phase"] = "completed"
        else:
            state["phase"] = "pub04_failed_stopped"
        return 0
    except Exception as exc:
        state["phase"] = "error"
        state["error"] = f"{type(exc).__name__}: {exc}"
        return 1
    finally:
        state["ended_at"] = timestamp()
        write(state_path, state)


if __name__ == "__main__":
    raise SystemExit(main())
