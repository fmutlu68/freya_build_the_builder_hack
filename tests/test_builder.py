import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from builder.run import Run, main, codex_command, child_env
from builder.repair_identity_gate import repair
from builder.repair_dispute_clarification import repair as repair_dispute
from builder.layout import arrange
from builder.validate import validate


def fixture():
    schema = {"type": "object", "properties": {
        "member_ref": {"type": "string"},
        "check": {"type": "string", "enum": ["postal_area", "joined_year"]}},
        "required": ["member_ref", "check"]}
    spec = {"servers": [{"url": "https://example.test/v7"}], "paths": {"/confirm": {"post": {
        "requestBody": {"content": {"application/json": {"schema": schema}}}}}}}
    body = copy.deepcopy(schema)
    body["properties"]["member_ref"]["default"] = "{{member_ref}}"
    body["properties"]["check"]["default"] = "{{check}}"
    tool = {"type": "function", "function": {"name": "confirm", "handler": "__function__:api_call",
            "parameters": {"type": "object", "properties": {
                "url": {"default": "https://example.test/v7/confirm"}, "method": {"default": "POST"}, "body": body}}}}
    wf = {"initial_node": "start", "nodes": {"start": {"name": "start", "node_type": "conversation", "tools": [tool], "transitions": []}}}
    return wf, spec


class ValidationTests(unittest.TestCase):
    def test_editor_layout_is_distinct_and_preserves_logic(self):
        wf, _ = fixture()
        wf["nodes"]["other"] = {"name": "other", "node_type": "end_call", "terminal": {}}
        before = copy.deepcopy(wf)
        laid_out = arrange(wf)
        self.assertEqual(wf, before)
        self.assertEqual(set(laid_out["nodes"]), set(wf["nodes"]))
        self.assertEqual(len({tuple(n["position"].values()) for n in laid_out["nodes"].values()}), 2)
        for key in wf["nodes"]:
            laid_out["nodes"][key].pop("position")
        self.assertEqual(laid_out, wf)

    def test_changed_contract_and_local_ref(self):
        wf, spec = fixture()
        schema = spec["paths"]["/confirm"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        spec["components"] = {"schemas": {"Body": schema}}
        spec["paths"]["/confirm"]["post"]["requestBody"]["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/Body"}
        self.assertEqual(validate(wf, spec), [])

    def test_reject_wrong_enum_required_and_external_url(self):
        wf, spec = fixture()
        props = wf["nodes"]["start"]["tools"][0]["function"]["parameters"]["properties"]
        props["body"]["properties"]["check"]["enum"] = ["date_of_birth"]
        props["body"]["required"] = []
        errors = validate(wf, spec)
        self.assertTrue(any("enum" in x for x in errors))
        self.assertTrue(any("required" in x for x in errors))
        props["url"]["default"] = "https://other.test/v7/confirm"
        self.assertTrue(any("URL" in x for x in validate(wf, spec)))

    def test_invalid_reference_and_code(self):
        wf, spec = fixture()
        wf["nodes"]["start"]["transitions"] = [{"target_node": "missing", "condition": {"operator": "always"}}]
        wf["nodes"]["start"]["tools"][0]["post_process_code"] = "if :"
        errors = validate(wf, spec)
        self.assertTrue(any("unknown target" in x for x in errors))
        self.assertTrue(any("invalid Python" in x for x in errors))

    def test_python_json_literal_is_not_a_template(self):
        wf, spec = fixture()
        tool = wf["nodes"]["start"]["tools"][0]
        tool["post_process_code"] = "payload = '{\"kind\":\"transport\",\"body\":{}}'"
        self.assertEqual(validate(wf, spec), [])
        tool["post_process_code"] = "payload = '{{customer_id}}'"
        self.assertTrue(any("template braces" in x for x in validate(wf, spec)))

    def test_reject_json_object_in_single_string_extraction(self):
        wf, spec = fixture()
        wf["nodes"]["start"]["extraction_schema"] = [{
            "name": "event", "type": "string",
            "description": "Return one JSON object with intent and security_answer",
            "min_confidence": 0.3,
        }]
        self.assertTrue(any("typed extraction fields" in x for x in validate(wf, spec)))

    def test_reject_oversized_monolithic_extraction_schema(self):
        wf, spec = fixture()
        wf["nodes"]["start"]["extraction_schema"] = [
            {"name": f"f_{i}", "type": "string", "description": f"Field {i}"} for i in range(12)
        ]
        self.assertTrue(any("stage-scoped" in x for x in validate(wf, spec)))

    def test_cli_explicit_model_and_effort(self):
        cmd = codex_command("some-accessible-model", "medium", Path("/tmp/work"), Path("/tmp/final"))
        self.assertEqual(cmd[cmd.index("--model")+1], "some-accessible-model")
        self.assertIn('model_reasoning_effort="medium"', cmd)
        self.assertIn("--ignore-user-config", cmd)
        with patch.dict(os.environ, {"FREYA_API_KEY": "secret", "OPENAI_API_KEY": "secret"}):
            self.assertNotIn("FREYA_API_KEY", child_env())
            self.assertNotIn("OPENAI_API_KEY", child_env())


class RunnerTests(unittest.TestCase):
    def test_generation_timeout_keeps_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = Run(SimpleNamespace(out=root, model="test-model", reasoning_effort="medium",
                                      budget_seconds=5, export_reserve_seconds=1))
            run.deadline = time.monotonic() + 1.2
            cmd = [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(20)"]
            started = time.monotonic()
            with patch("builder.run.codex_command", return_value=cmd):
                with self.assertRaises(subprocess.TimeoutExpired):
                    run.generate(root, 0, "prompt")
            self.assertLess(time.monotonic()-started, 4)
            self.assertIn("started", (run.out / "codex-0.events.jsonl").read_text())

    def test_generation_timeout_stops_nested_helper_holding_output_pipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = Run(SimpleNamespace(out=root, model="test-model", reasoning_effort="medium",
                                      budget_seconds=5, export_reserve_seconds=1))
            run.deadline = time.monotonic() + 1.2
            script = ("import subprocess,sys,time; "
                      "subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'], "
                      "start_new_session=True); print('helper-started',flush=True); time.sleep(20)")
            started = time.monotonic()
            with patch("builder.run.codex_command", return_value=[sys.executable, "-c", script]):
                with self.assertRaises(subprocess.TimeoutExpired):
                    run.generate(root, 0, "prompt")
            self.assertLess(time.monotonic()-started, 5)
            self.assertIn("helper-started", (run.out / "codex-0.events.jsonl").read_text())

    def run_case(self, generate, export_fails=False):
        import freya
        wf, spec = fixture()
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "brief.md").write_text("Synthetic policy")
        (root / "api.json").write_text(json.dumps(spec))
        def export(wid, path):
            if export_fails: raise OSError("network unavailable")
            Path(path).write_text(json.dumps({"workflow_id": wid, "agent_id": "aid", "workflow": wf}))
        with patch.dict(os.environ, {"FREYA_API_KEY": "test-secret-value"}), \
             patch("builder.run.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "codex test", "")), \
             patch.object(Run, "generate", side_effect=generate), \
             patch.object(freya, "validate_workflow", return_value={"valid": True}), \
             patch.object(freya, "create_workflow", return_value={"workflow_id": "wid", "agent_id": "aid"}) as create, \
             patch.object(freya, "export_workflow", side_effect=export):
            code = main([str(root / "brief.md"), "--openapi", str(root / "api.json"), "--model", "test-model",
                         "--reasoning-effort", "medium", "--out", str(root / "runs"), "--max-repairs", "1"])
            out = next((root / "runs").iterdir())
            return code, json.loads((out / "summary.json").read_text()), create.call_count, out

    def test_repair_then_export(self):
        wf, _ = fixture()
        code, summary, count, out = self.run_case(["not json", json.dumps(wf)])
        self.assertEqual(code, 0)
        self.assertEqual(count, 1)
        self.assertEqual(summary["status"], "exported")
        self.assertEqual(summary["tests"], "not_run")
        self.assertTrue((out / "validation-0.json").exists())
        self.assertTrue((out / "workflow.export.json").exists())

    def test_invalid_never_deploys(self):
        code, summary, count, out = self.run_case(["bad", "bad"])
        self.assertEqual(code, 1)
        self.assertEqual(count, 0)

    def test_export_failure_preserves_ids(self):
        wf, _ = fixture()
        code, summary, count, out = self.run_case([json.dumps(wf)], export_fails=True)
        self.assertEqual(code, 1)
        self.assertEqual(count, 1)
        self.assertEqual(summary["candidates"][0]["workflow_id"], "wid")
        self.assertTrue((out / "candidate.json").exists())


class IdentityGateRepairTests(unittest.TestCase):
    def test_optional_aggregate_requires_authorized_account_result(self):
        root = Path(__file__).resolve().parent.parent
        original = json.loads((root / "runs/build-20261010T211124Z-859ec3/candidate-0.workflow.json").read_text())
        fixed = repair(original)
        self.assertEqual(validate(fixed, json.loads((root / "tools/openapi.json").read_text())), [])
        self.assertIn("get_account explicitly succeeds", fixed["system_prompt"])
        self.assertEqual(original["nodes"]["verify_phone"]["pre_actions"][0]["post_process_code"].count("passed_unconfirmed"), 0)
        for state, aggregate in [("passed_unconfirmed", None), ("passed", False), ("full", True)]:
            data = {"ok": True, "verified": True}
            if aggregate is not None:
                data["all_verified"] = aggregate
            result = {"status": "success", "data": data}
            code = fixed["nodes"]["verify_phone"]["pre_actions"][0]["post_process_code"]
            exec(code, {"result": result})
            self.assertEqual(result["data"]["workflow_state"], state)

        handler = fixed["nodes"]["action_result"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        common = {"today": "2026-10-11", "dob_pass": "yes", "verified_state": "partial",
                  "identity_technical": 0, "wrong_left": 2, "recorded": "no"}
        denied = {**common, "flow_target": "verify_phone", "api_state": "passed"}
        exec(handler, {"vars": denied})
        self.assertEqual(denied["flow_target"], "phone")
        self.assertEqual(denied["verified_state"], "partial")

        premature = {**common, "flow_target": "verify_dob", "api_state": "full", "dob_pass": "no"}
        exec(handler, {"vars": premature})
        self.assertEqual(premature["flow_target"], "phone")
        self.assertEqual(premature["verified_state"], "partial")

        allowed = {**common, "flow_target": "verify_phone", "api_state": "passed_unconfirmed"}
        exec(handler, {"vars": allowed})
        self.assertEqual(allowed["flow_target"], "account")
        self.assertEqual(allowed["verified_state"], "pending_account")
        allowed.update(flow_target="account", api_state="ok", account_products=[
            {"type": "credit_card", "product_id": "test-product", "card_last4": "1234",
             "past_due": 100, "minimum_payment": 20, "days_late": 3}])
        exec(handler, {"vars": allowed})
        self.assertEqual(allowed["verified_state"], "full")
        self.assertEqual(allowed["flow_target"], "discussion")

        rejected = {**common, "flow_target": "account", "api_state": "failed",
                    "verified_state": "pending_account", "account_products": []}
        exec(handler, {"vars": rejected})
        self.assertEqual(rejected["flow_target"], "end")
        self.assertNotEqual(rejected["verified_state"], "full")


class DisputeClarificationTests(unittest.TestCase):
    def test_uncertain_product_question_gets_one_clarification(self):
        root = Path(__file__).resolve().parent.parent
        source = json.loads((root / "runs/identity-gate-repair-20261010T220103Z/workflow.json").read_text())
        fixed = repair_dispute(source)
        self.assertEqual(validate(fixed, json.loads((root / "tools/openapi.json").read_text())), [])
        handler = fixed["nodes"]["evaluate"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        base = {"today": "2026-10-11", "clock_text": "2026-10-11T01:27+03:00", "stage": "negotiate",
                "input_answer": "", "input_date_phrase": "", "input_date": "", "input_amount": "",
                "input_time": "", "turn_count": 0, "verified_state": "full", "dob_pass": "yes",
                "product_label": "credit card ending 1234", "full_amount": 100.0,
                "recorded": "no", "close_outcome": "no_promise", "close_reason": "refused"}
        for event in ("dispute", "other"):
            state = {**base, "input_event": event,
                     "input_raw": "I don't know that there is a credit card like that, are you sure?"}
            exec(handler, {"vars": state})
            self.assertEqual(state["stage"], "product_clarification")
            self.assertEqual(state["flow_target"], "discussion")
            self.assertIn("Do you dispute", state["speech_task"])
            state.update(input_event="affirm", input_raw="yes")
            exec(handler, {"vars": state})
            self.assertEqual(state["flow_target"], "end")
            self.assertEqual(state["close_reason"], "dispute")

        explicit = {**base, "input_event": "dispute", "input_raw": "This card is not mine."}
        exec(handler, {"vars": explicit})
        self.assertEqual(explicit["flow_target"], "end")
        self.assertEqual(explicit["close_reason"], "dispute")


if __name__ == "__main__":
    unittest.main()
