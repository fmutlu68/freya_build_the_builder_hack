"""python3 -m builder.run BRIEF... --openapi API.json --model ID --reasoning-effort medium"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid

from builder.validate import validate, operations
from builder.layout import arrange

ROOT = Path(__file__).resolve().parent.parent


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def child_env():
    # Keep login discovery; never hand deployment/provider keys to the generator.
    allowed = {"PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL", "TERM", "TMPDIR",
               "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"}
    return {k: v for k, v in os.environ.items() if k in allowed}


def codex_command(model, effort, work, final):
    return ["codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
            "--sandbox", "workspace-write", "--cd", str(work), "--model", model,
            "-c", 'model_reasoning_effort=' + json.dumps(effort),
            "-c", 'web_search="disabled"', "--json", "--color", "never",
            "--output-last-message", str(final), "-"]


def terminate_tree(root_pid):
    """Stop a timed-out CLI and nested helpers that may own separate groups."""
    parents = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
            parents[int(entry.name)] = int(fields[1])
        except (OSError, ValueError, IndexError):
            continue
    descendants = []
    pending = [root_pid]
    while pending:
        parent = pending.pop()
        children = [pid for pid, ppid in parents.items() if ppid == parent]
        descendants.extend(children)
        pending.extend(children)
    targets = descendants[::-1] + [root_pid]
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in targets:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        if sig == signal.SIGTERM:
            time.sleep(0.2)


class Run:
    def __init__(self, args):
        self.args = args
        self.start = time.monotonic()
        self.deadline = self.start + args.budget_seconds
        self.name = "build-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        self.out = args.out.resolve() / self.name
        self.out.mkdir(parents=True, exist_ok=False)
        self.secrets = [v for k, v in os.environ.items() if v and re.search(r"KEY|TOKEN|SECRET|PASSWORD", k, re.I)]
        self.state = {"run": self.name, "started_at": now(), "model": args.model,
                      "reasoning_effort": args.reasoning_effort, "budget_seconds": args.budget_seconds,
                      "export_reserve_seconds": args.export_reserve_seconds, "candidates": [],
                      "tests": "not_run", "status": "starting",
                      "mock_base_url": getattr(args, "mock_base_url", None)}
        code = self.out / "runner-source"
        code.mkdir()
        for filename in ("run.py", "validate.py", "layout.py", "INSTRUCTIONS.md"):
            shutil.copyfile(ROOT / "builder" / filename, code / filename)
        shutil.copyfile(ROOT / "freya.py", code / "freya.py")
        self.state["source_hashes"] = {p.name: digest(p) for p in code.iterdir()}
        self.write("summary.json", self.state)

    def redact(self, text):
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"\bfak_[A-Za-z0-9_-]+", "[REDACTED]", text)
        text = re.sub(r"(?i)Bearer\s+[^\s\"\\]+", "Bearer [REDACTED]", text)
        return text

    def write(self, name, value):
        text = self.redact(json.dumps(value, indent=2, ensure_ascii=False)) + "\n"
        path = self.out / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)

    def event(self, event, **data):
        with (self.out / "trace.jsonl").open("a") as f:
            f.write(self.redact(json.dumps({"at": now(), "elapsed_s": round(time.monotonic()-self.start, 2), "event": event, **data})) + "\n")
        print(event, flush=True)

    def remaining(self, reserve=0):
        left = self.deadline - time.monotonic() - reserve
        if left <= 0:
            raise TimeoutError("Run budget exhausted (including export reserve)")
        return left

    def generate(self, work, attempt, prompt):
        final = work / "last-message.json"
        if final.exists(): final.unlink()
        command = codex_command(self.args.model, self.args.reasoning_effort, work, final)
        self.event("model_call_start", model=self.args.model, reasoning_effort=self.args.reasoning_effort,
                   purpose="generate workflow" if attempt == 0 else "repair validation errors", attempt=attempt, command=command)
        (self.out / f"prompt-{attempt}.txt").write_text(prompt)
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=child_env(), start_new_session=True, text=True)
        def drain(stream, filename):
            with (self.out / filename).open("w") as f:
                for line in stream:
                    f.write(self.redact(line)); f.flush()
        readers = [threading.Thread(target=drain, args=(proc.stdout, f"codex-{attempt}.events.jsonl"), daemon=True),
                   threading.Thread(target=drain, args=(proc.stderr, f"codex-{attempt}.stderr.log"), daemon=True)]
        for reader in readers: reader.start()
        try:
            proc.stdin.write(prompt); proc.stdin.close()
            proc.wait(timeout=self.remaining(self.args.export_reserve_seconds))
        finally:
            if proc.poll() is None:
                terminate_tree(proc.pid)
                try: proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            for reader in readers: reader.join(timeout=3)
            if proc.stdin and not proc.stdin.closed: proc.stdin.close()
            for reader, stream in zip(readers, (proc.stdout, proc.stderr)):
                # close() can block forever if a surviving grandchild holds the
                # pipe; the bounded run must still return with its logs intact.
                if stream and not stream.closed and not reader.is_alive(): stream.close()
            if final.exists():
                (self.out / f"candidate-{attempt}.raw.txt").write_text(self.redact(final.read_text()))
            self.event("model_call_end", attempt=attempt, returncode=proc.returncode)
        if proc.returncode:
            raise RuntimeError(f"Codex exited {proc.returncode}; see codex-{attempt}.stderr.log and events. No model fallback.")
        if not final.exists():
            raise RuntimeError("Codex returned no final artifact")
        raw = final.read_text()
        (self.out / f"candidate-{attempt}.raw.txt").write_text(self.redact(raw))
        if self.redact(raw) != raw:
            raise ValueError("Credential-like value in generated artifact; not deployable")
        return raw

    def execute(self):
        a = self.args
        self.event("run_start", **self.state)
        version = subprocess.run(["codex", "--version"], env=child_env(), capture_output=True, text=True, timeout=min(15, self.remaining()))
        login = subprocess.run(["codex", "login", "status"], env=child_env(), capture_output=True, text=True, timeout=min(15, self.remaining()))
        self.state["codex_version"] = version.stdout.strip()
        self.event("cli_preflight", version=version.stdout.strip(), login_ok=login.returncode == 0)
        if version.returncode or login.returncode:
            raise RuntimeError("Codex CLI/login unavailable; credentials not logged")
        api_file = a.openapi.resolve()
        spec = json.loads(api_file.read_text())
        if getattr(a, "mock_base_url", None):
            spec["servers"] = [{"url": a.mock_base_url.rstrip("/")}]
        operations(spec)  # Fail explicitly for unsupported API shapes, not after deployment.
        sources = [p.resolve() for p in a.briefs]
        case_folder = getattr(a, "case_folder", None)
        case_files = sorted(p for p in case_folder.resolve().rglob("*") if p.is_file()) if case_folder else []
        repair_files = [a.prior_candidate.resolve(), a.feedback.resolve()] if a.prior_candidate else []
        self.state["inputs"] = [{"path": str(p), "sha256": digest(p)} for p in sources + [api_file] + case_files + repair_files]
        self.write("summary.json", self.state)
        inputs = self.out / "inputs"; inputs.mkdir()
        for i, p in enumerate(sources): shutil.copyfile(p, inputs / f"brief-{i}{p.suffix}")
        (inputs / "openapi.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False))
        if a.prior_candidate:
            shutil.copyfile(a.prior_candidate.resolve(), inputs / "prior-candidate.workflow.json")
            shutil.copyfile(a.feedback.resolve(), inputs / "feedback.md")
        if case_folder:
            case = inputs / "case"
            shutil.copytree(case_folder.resolve(), case)
            for pdf in case.rglob("*.pdf"):
                subprocess.run(["pdftotext", "-layout", str(pdf), str(pdf.with_suffix(".pdf.txt"))], check=True)
        # Separate /tmp workspace avoids inheriting this development chat's AGENTS,
        # env.sh, local project config, test fixtures, or earlier candidates.
        with tempfile.TemporaryDirectory(prefix="freya-builder-") as tmp:
            work = Path(tmp)
            shutil.copytree(inputs, work / "inputs")
            (work / "platform").mkdir()
            for name in ("workflow-format.md", "tools-and-code.md"):
                shutil.copyfile(ROOT / "docs" / name, work / "platform" / name)
            instructions = (ROOT / "builder/INSTRUCTIONS.md").read_text()
            (work / "AGENTS.md").write_text(instructions)
            (self.out / "instructions.md").write_text(instructions)
            shutil.copytree(work / "platform", self.out / "platform")
            errors = []
            for attempt in range(a.max_repairs + 1):
                self.remaining(a.export_reserve_seconds)
                prompt = ("Read AGENTS.md, supplied narrative sources in inputs/ (briefs in numeric order), and platform/. "
                          "If inputs/case exists, compare dated sources and explicit corrections, then write requirements.md "
                          "with important conflicts, chosen authority, scope, and unresolved points. "
                          "Use the customer fixture overview for coverage; do not embed customer fixture records in the workflow. "
                          "Generate the complete workflow for these documents. Final response must be ONLY raw workflow JSON. "
                          "Do not deploy or run simulations. Do not access any file outside this directory.\n")
                if a.prior_candidate:
                    prompt += ("This is a bounded repair of inputs/prior-candidate.workflow.json using the observed failure "
                               "in inputs/feedback.md. Preserve independently working behavior and source-backed rules. "
                               "Resolve the failure from the supplied case documents and OpenAPI; do not embed the "
                               "test utterance, fixture identity, or expected answer as a special case. Produce a complete "
                               "new workflow JSON, not a patch, and record the evidence and decisions in requirements.md.\n")
                if attempt:
                    prompt += "Repair the previous attempt using previous.workflow.json and validation-errors.json.\n"
                    (work / "validation-errors.json").write_text(json.dumps(errors, indent=2))
                raw = self.generate(work, attempt, prompt)
                if (work / "requirements.md").is_file():
                    (self.out / "requirements.md").write_text(self.redact((work / "requirements.md").read_text()))
                (work / "previous.workflow.json").write_text(raw)
                try:
                    workflow = arrange(json.loads(raw))
                    errors = validate(workflow, spec)
                except json.JSONDecodeError as exc:
                    errors = [f"Final response must be raw valid JSON: {exc}"]
                if case_folder and not (work / "requirements.md").is_file():
                    errors.append("Missing requirements.md source conflict and scope record")
                self.write(f"validation-{attempt}.json", {"errors": errors, "scope": "static structure and OpenAPI; not policy/runtime proof"})
                self.event("local_validation", attempt=attempt, errors=errors)
                if errors: continue
                self.write(f"candidate-{attempt}.workflow.json", workflow)
                import freya
                if not os.environ.get("FREYA_API_KEY"):
                    self.state["status"] = "blocked_deployment"
                    raise RuntimeError("FREYA_API_KEY missing; validated workflow preserved")
                # Do not permit caller env to change the fixed phone model.
                if freya.AGENT_LLM != {"provider": "experimental-5", "model": "experimental-5"}:
                    raise ValueError("Phone model override detected; remove FREYA_AGENT_PROVIDER/MODEL overrides")
                try:
                    self.remaining()
                    dry = freya.validate_workflow(self.name, workflow)
                    if isinstance(dry, dict) and dry.get("success") is False:
                        raise RuntimeError("Platform dry run rejected: " + json.dumps(dry))
                    self.write(f"platform-validation-{attempt}.json", dry)
                    self.event("platform_validation", attempt=attempt, accepted=True)
                except RuntimeError as exc:
                    if any(x in str(exc) for x in ("-> 400:", "-> 422:", "dry run rejected")):
                        errors = [self.redact(str(exc))]
                        self.event("platform_validation", attempt=attempt, accepted=False, errors=errors)
                        continue
                    raise
                self.remaining()
                self.event("create_start", name=self.name, attempt=attempt)
                # Never retry an ambiguous create: server may already have stored it.
                ids = freya.create_workflow(self.name, workflow)
                self.state["candidates"].append({"attempt": attempt, **ids})
                self.write("summary.json", self.state)
                self.write("candidate.json", {"name": self.name, **ids})
                self.event("created", **ids)
                self.remaining()
                export = work / "export.json"
                freya.export_workflow(ids["workflow_id"], str(export))
                exported = json.loads(export.read_text())
                if exported.get("workflow_id") != ids["workflow_id"] or not exported.get("workflow", {}).get("nodes"):
                    raise ValueError("Invalid/incomplete platform export")
                # Platform defaults should not contain credentials. Do not write
                # a credential-bearing export to persistent artifacts.
                def check_secrets(value):
                    if isinstance(value, dict):
                        for k, v in value.items():
                            if re.fullmatch(r"api_?key|authorization|access_?token|secret", k, re.I) and v:
                                raise ValueError("Platform export contains credentials; withheld")
                            check_secrets(v)
                    elif isinstance(value, list):
                        for v in value: check_secrets(v)
                check_secrets(exported)
                raw_export = json.dumps(exported)
                if self.redact(raw_export) != raw_export:
                    raise ValueError("Platform export contains a known credential; withheld")
                self.write("workflow.export.json", exported)
                self.state["status"] = "exported"
                self.state["export"] = "workflow.export.json"
                self.event("exported", **ids, path="workflow.export.json")
                return
            raise ValueError(f"Repair limit reached: {len(errors)} unresolved validation errors")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("briefs", nargs="*", type=Path)
    p.add_argument("--case-folder", type=Path, help="Snapshot all case sources, including PDF text, for this run")
    p.add_argument("--openapi", required=True, type=Path)
    p.add_argument("--mock-base-url", help="Override the OpenAPI server with the deployed mock base URL")
    p.add_argument("--prior-candidate", type=Path, help="Existing workflow JSON to repair in a new isolated run")
    p.add_argument("--feedback", type=Path, help="Observed failure evidence for a bounded repair")
    p.add_argument("--model", required=True, help="Exact Codex model ID; no fallback")
    p.add_argument("--reasoning-effort", required=True, choices=["low", "medium", "high", "xhigh", "max", "ultra"])
    p.add_argument("--out", type=Path, default=ROOT / "runs")
    p.add_argument("--budget-seconds", type=int, default=1800)
    p.add_argument("--export-reserve-seconds", type=int, default=180)
    p.add_argument("--max-repairs", type=int, default=2)
    a = p.parse_args(argv)
    if not 0 < a.export_reserve_seconds < a.budget_seconds <= 1800:
        p.error("0 < export reserve < budget <= 1800 required")
    if not 0 <= a.max_repairs <= 5: p.error("max-repairs must be 0..5")
    if not a.briefs and not a.case_folder: p.error("supply brief files or --case-folder")
    if a.case_folder and not a.case_folder.is_dir(): p.error(f"Missing case folder: {a.case_folder}")
    if bool(a.prior_candidate) != bool(a.feedback): p.error("--prior-candidate and --feedback must be used together")
    for path in a.briefs + [a.openapi] + ([a.prior_candidate, a.feedback] if a.prior_candidate else []):
        if not path.is_file(): p.error(f"Missing input: {path}")
    run = Run(a)
    def timeout(signum, frame):
        raise TimeoutError("Total run deadline reached")
    old = signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, run.remaining())
    code = 1
    try:
        run.execute(); code = 0
    except (Exception, KeyboardInterrupt) as exc:
        if run.state["status"] != "blocked_deployment": run.state["status"] = "failed"
        run.state["error"] = run.redact(f"{type(exc).__name__}: {exc}")
        run.event("run_error", error=run.state["error"])
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old)
        run.state["ended_at"] = now()
        run.state["elapsed_seconds"] = round(time.monotonic()-run.start, 2)
        run.write("summary.json", run.state)
        run.event("run_end", status=run.state["status"])
        print("Artifacts:", run.out, flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
