import json
from pathlib import Path

from builder.repair_closed_session import repair


SOURCE = Path(__file__).resolve().parents[1] / "runs/opening-security-repair-20261010T224156Z/workflow.json"


def test_closed_session_is_terminal_and_does_not_blame_answer():
    workflow = repair(json.loads(SOURCE.read_text()))
    for name in ("verify_dob", "verify_phone"):
        result = {"status": "success", "data": {"ok": False, "error": "the call is already closed"}}
        post = workflow["nodes"][name]["pre_actions"][0]["post_process_code"]
        exec(post, {"result": result})
        assert result["data"]["workflow_state"] == "session_closed"

    state = {"flow_target": "verify_dob", "api_state": "session_closed",
             "today": "2026-10-11", "identity_technical": 0,
             "verified_state": "none", "customer_confirmed": "yes"}
    code = workflow["nodes"]["action_result"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    exec(code, {"vars": state})
    assert state["flow_target"] == "end"
    assert state["identity_technical"] == 0
    assert state["close_reason"] == "service_error"
    assert "answer was not marked wrong" in state["farewell"]
