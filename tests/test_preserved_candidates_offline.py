"""Offline contract probes for preserved A/B artifacts; no Freya requests."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "runs/build-20261011T092921Z-d3b1ba/candidate-0.workflow.json"
B = ROOT / "runs/build-20261010T231245Z-3cd302/workflow.export.json"


def code(workflow, node):
    return workflow["nodes"][node]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


def a_state():
    workflow = json.loads(A.read_text())
    state = {"now": "2026-10-14T11:00", "customer_id": "synthetic",
             "first_name": "Test", "last_name": "Person", "title": "Ms"}
    exec(code(workflow, "initialize"), {"vars": state})
    return workflow, state


def b_product_state():
    product = {"product_id": "synthetic", "label": "car loan", "type": "car_loan",
               "past_due": 500.0, "days_late": 3, "floor": 100.0,
               "deadline": "2026-10-30", "attempt_limit": 1, "attempts": 1,
               "too_much": False, "floor_offered": False, "vague_count": 0,
               "rejected": [], "status": "pending", "reason": "", "amount": 500.0,
               "date": "2026-10-16", "offer_kind": "persuasion",
               "offer_key": "500.0:2026-10-16", "note_done": False,
               "write_attempts": 0, "common_adjustment": ""}
    return {"stage": "product", "opening_asks": 1, "wrong": 0, "declines": 0,
            "stop_count": 0, "human_asked": False, "verified": True,
            "dob_pass": True, "phone_pass": True, "products": [product], "index": 0,
            "pending": "", "api_attempt": 0, "callback_bad": 0,
            "transfer_requested": False, "notice": "", "outcome": "", "reason": "",
            "finalizing": False}


class PreservedCandidateProbes(unittest.TestCase):
    def test_a_clear_name_confirmation_enters_dob(self):
        workflow, state = a_state()
        self.assertEqual(workflow["nodes"]["listen"]["on_enter"],
                         {"type": "tts", "text": "{{say}}"})
        state.update(x_readability="complete", x_intent="self", x_question="none")
        exec(code(workflow, "process_answer"), {"vars": state})
        self.assertEqual((state["stage"], state["action"]), ("dob", "listen"))
        self.assertEqual(state["say"], "What is your date of birth?")
        self.assertNotIn("x_intent", state)

    def test_a_missing_extraction_does_not_reuse_dob(self):
        workflow, state = a_state()
        state.update(stage="dob", pending_question="What is your date of birth?",
                     x_readability="complete", x_intent="security_answer",
                     x_dob="1988-03-14", x_dob_month="word")
        exec(code(workflow, "process_answer"), {"vars": state})
        self.assertEqual(state["action"], "verify_identity")
        self.assertNotIn("x_dob", state)
        # Simulate an extraction error on a later turn: no new x_* values.
        exec(code(workflow, "process_answer"), {"vars": state})
        self.assertEqual((state["stage"], state["action"]), ("dob", "listen"))
        self.assertEqual(state["technical_clarifications"], 1)

    def test_a_iso_date_and_next_friday_agree(self):
        workflow, state = a_state()
        state.update(stage="payment", verified_state="yes", dob_passed="yes",
                     phone_passed="yes", full_amount=1250.0, floor=150.0,
                     product_label="personal loan", deadline="2026-10-30",
                     candidate_amount=1250.0, candidate_date="2026-10-14",
                     pending_question="Can you make this payment today?",
                     x_readability="complete", x_intent="proposal",
                     x_date_kind="exact", x_date="2026-10-23",
                     x_date_phrase="next Friday")
        exec(code(workflow, "process_answer"), {"vars": state})
        self.assertEqual((state["stage"], state["candidate_date"]),
                         ("confirm", "2026-10-23"))

    def test_a_early_band_persuasion_stops_after_one_offer(self):
        workflow, state = a_state()
        state.update(stage="payment", verified_state="yes", dob_passed="yes",
                     phone_passed="yes", full_amount=1250.0, floor=150.0,
                     product_label="personal loan", deadline="2026-10-30",
                     candidate_amount=1250.0, candidate_date="2026-10-14",
                     pending_question="Can you make this payment today?",
                     persuasion_limit=1, offer_kind="initial", offer_amount=1250.0,
                     offer_date="2026-10-14")
        for expected_action in ("listen", "finish"):
            state.update(x_readability="complete", x_intent="reject",
                         x_binary="no", x_question="none")
            exec(code(workflow, "process_answer"), {"vars": state})
            self.assertEqual(state["action"], expected_action)
            self.assertEqual(state["persuasions"], 1)
        self.assertEqual((state["outcome"], state["reason"]),
                         ("no_promise", "refused"))

    def test_b_early_product_refusal_stops_counter_but_unclear_can_repeat_speech(self):
        workflow = json.loads(B.read_text())["workflow"]
        engine = code(workflow, "engine")
        for intent in ("refuse", "unclear"):
            state = {"now": "2026-10-14T11:00", "bank_state": json.dumps(b_product_state()),
                     "turn_packet": json.dumps({"intent": intent})}
            exec(engine, {"vars": state})
            result = json.loads(state["bank_state"])
            self.assertEqual(result["products"][0]["attempts"], 1)
            if intent == "refuse":
                self.assertEqual(result["products"][0]["status"], "note")
                self.assertEqual(state["action"], "note")
            else:
                self.assertEqual(result["stage"], "product")
                self.assertIn("Offer 500.0 on 2026-10-16", state["state_instruction"])


if __name__ == "__main__":
    unittest.main()
