import json
from pathlib import Path

from builder.repair_product_uncertainty import repair


SOURCE = Path(__file__).resolve().parents[1] / "runs/opening-security-repair-20261010T224156Z/workflow.json"


def evaluate(event, raw):
    workflow = repair(json.loads(SOURCE.read_text()))
    state = {"today": "2026-10-11", "clock_text": "2026-10-11T20:00:00+03:00",
             "stage": "negotiate", "input_event": event, "input_raw": raw,
             "verified_state": "full", "product_label": "credit card ending 4821",
             "full_amount": 420.0, "turn_count": 2, "recorded": "no"}
    code = workflow["nodes"]["evaluate"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    exec(code, {"vars": state})
    return state


def test_observed_uncertainty_gets_account_facts_and_question():
    state = evaluate("other", "i dont think there is a card like this for me ?")
    assert state["stage"] == "product_clarification"
    assert state["flow_target"] == "discussion"
    assert "credit card ending 4821" in state["speech_task"]
    assert "420.0" in state["speech_task"]


def test_missing_raw_with_dispute_label_does_not_close_immediately():
    state = evaluate("dispute", "")
    assert state["stage"] == "product_clarification"
    assert state["flow_target"] == "discussion"


def test_clear_dispute_still_closes():
    state = evaluate("dispute", "I never had this product")
    assert state["flow_target"] == "end"
    assert state["close_reason"] == "dispute"
