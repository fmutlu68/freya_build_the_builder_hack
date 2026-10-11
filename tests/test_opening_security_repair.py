import json
from pathlib import Path

from builder.repair_opening_and_security import repair


SOURCE = Path(__file__).resolve().parents[1] / "runs/dispute-clarification-20261010T223223Z/workflow.json"


def evaluate(workflow, stage, event, raw, answer="", asks=1):
    state = {
        "today": "2026-10-11", "clock_text": "2026-10-11T20:00:00+03:00",
        "stage": stage, "input_event": event, "input_raw": raw,
        "input_answer": answer, "first_name": "Alex", "last_name": "Reyes",
        "title": "Mr", "opening_asks": asks, "customer_confirmed": "no",
        "verified_state": "none", "turn_count": 0,
    }
    code = workflow["nodes"]["evaluate"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    exec(code, {"vars": state})
    return state


def test_only_brief_listed_confirmations_advance_to_dob():
    workflow = repair(json.loads(SOURCE.read_text()))
    for raw in ("yes", "that's me", "speaking", "Alex Reyes", "Alex"):
        state = evaluate(workflow, "opening", "affirm", raw, asks=1)
        assert state["flow_target"] == "dob"
        assert state["customer_confirmed"] == "yes"


def test_unclear_and_negative_do_not_advance():
    workflow = repair(json.loads(SOURCE.read_text()))
    for raw in ("no", "who is this", "14 march 1988", "yeah", "its me", "talking to him"):
        state = evaluate(workflow, "opening", "identity_confirmation", raw, asks=1)
        assert state["flow_target"] == "opening"
        assert state["customer_confirmed"] == "no"
        assert state["opening_asks"] == 2
    for raw in ("yes, but I am his father", "I am not Alex Reyes"):
        state = evaluate(workflow, "opening", "identity_confirmation", raw, asks=2)
        assert state["flow_target"] == "end"
        assert state["close_outcome"] == "not_reached"
        assert state["close_reason"] == "unclear"


def test_valid_dob_with_vague_date_label_is_sent_for_verification():
    workflow = repair(json.loads(SOURCE.read_text()))
    state = evaluate(workflow, "dob", "vague_date", "14 march 1988", "1988-03-14")
    assert state["flow_target"] == "verify_dob"
    assert state["dob_answer"] == "1988-03-14"
