import json
import os
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from builder.repair_question_in_negotiate import repair
from builder.validate import validate

ROOT = Path(__file__).resolve().parent.parent


def run_evaluate_code(code_str, initial_vars):
    scope = {"vars": initial_vars.copy()}
    exec(code_str, scope)
    return scope["vars"]


class TestQuestionInNegotiate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_wf_path = ROOT / "runs" / "build-20261011T131745Z-fc9e6e" / "candidate-0.workflow.json"
        raw_wf = json.loads(base_wf_path.read_text())
        cls.repaired_wf = repair(raw_wf)
        cls.code = cls.repaired_wf["nodes"]["evaluate"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        spec = json.loads((ROOT / "tools" / "openapi.json").read_text())
        cls.val_errors = validate(cls.repaired_wf, spec)

    def test_validation_passes(self):
        self.assertEqual(self.val_errors, [])

    def test_1_standalone_information_question_in_negotiate(self):
        # Pending offer: floor offered (637.50). Caller asks: "How much is the minimum payment?"
        init_vars = {
            "state": "negotiate",
            "now": "2026-10-14T11:00",
            "today": "2026-10-14",
            "deadline": "2026-10-23",
            "product_name": "credit card ending 1903",
            "full_amount": 2125.10,
            "floor_amount": 637.50,
            "pending_amount": 637.50,
            "pending_date": "2026-10-14",
            "pending_question": "Can you pay 637.50 on 14 October 2026? The rest stays overdue.",
            "account_facts": "Your credit card ending 1903 has a past-due amount of 2125.10 and is 12 days late. The amount floor is 637.50. The latest promise date is 23 October 2026.",
            "account_authorized": "yes",
            "floor_offered": 1,
            "persuasion_used": 0,
            "event": "question",
            "question_kind": "account",
            "offer_date": "2026-10-14"
        }
        res = run_evaluate_code(self.code, init_vars)
        # Should stay in negotiate
        self.assertEqual(res["route"], "negotiate")
        # Should answer the question using account facts
        self.assertIn("The amount floor is 637.50", res["say"])
        # Should NOT repeat the offer question!
        self.assertNotIn("Can you pay 637.50 on 14 October 2026?", res["say"])
        # Counters and pending offer must remain unchanged
        self.assertEqual(res["floor_offered"], 1)
        self.assertEqual(res["persuasion_used"], 0)
        self.assertEqual(res["pending_amount"], 637.50)
        self.assertEqual(res["pending_question"], "Can you pay 637.50 on 14 October 2026? The rest stays overdue.")

    def test_2_question_with_payment_proposal(self):
        # Caller asks question and proposes Friday: "How much is the minimum? I can pay this Friday."
        init_vars = {
            "state": "negotiate",
            "now": "2026-10-14T11:00",
            "today": "2026-10-14",
            "deadline": "2026-10-23",
            "product_name": "credit card ending 1903",
            "full_amount": 2125.10,
            "floor_amount": 637.50,
            "pending_amount": 637.50,
            "pending_date": "2026-10-14",
            "pending_question": "Can you pay 637.50 on 14 October 2026? The rest stays overdue.",
            "account_facts": "Your credit card ending 1903 has a past-due amount of 2125.10 and is 12 days late. The amount floor is 637.50. The latest promise date is 23 October 2026.",
            "account_authorized": "yes",
            "floor_offered": 1,
            "persuasion_used": 0,
            "event": "propose",
            "date_kind": "this_friday",
            "offer_date": "2026-10-16",
            "offer_amount": 637.50,
            "question_kind": "account"
        }
        res = run_evaluate_code(self.code, init_vars)
        # Proposal should transition to confirm with readback
        self.assertEqual(res["route"], "confirm")
        self.assertEqual(res["pending_date"], "2026-10-16")
        self.assertEqual(res["pending_amount"], 637.50)
        self.assertIn("Do you confirm?", res["say"])

    def test_3_inability_triggers_floor_offer(self):
        # First offer was full amount. Caller says: "The full amount is too much."
        init_vars = {
            "state": "negotiate",
            "now": "2026-10-14T11:00",
            "today": "2026-10-14",
            "deadline": "2026-10-23",
            "product_name": "credit card ending 1903",
            "full_amount": 2125.10,
            "floor_amount": 637.50,
            "pending_amount": 2125.10,
            "pending_date": "2026-10-14",
            "pending_question": "Can you make this payment today?",
            "account_authorized": "yes",
            "floor_offered": 0,
            "persuasion_used": 0,
            "event": "inability",
            "question_kind": "account"
        }
        res = run_evaluate_code(self.code, init_vars)
        # Inability without caller date must propose floor on the last business day of this week (Friday 16 Oct)
        self.assertEqual(res["floor_offered"], 1)
        self.assertEqual(res["persuasion_used"], 1)
        self.assertEqual(res["pending_amount"], 637.50)
        self.assertEqual(res["pending_date"], "2026-10-16")
        self.assertIn("16 October 2026", res["say"])
        self.assertIn("The rest stays overdue.", res["say"])


    def test_4_explicit_accept_after_question(self):
        # After information is given, caller says "Yes"
        init_vars = {
            "state": "negotiate",
            "now": "2026-10-14T11:00",
            "today": "2026-10-14",
            "deadline": "2026-10-23",
            "product_name": "credit card ending 1903",
            "full_amount": 2125.10,
            "floor_amount": 637.50,
            "pending_amount": 637.50,
            "pending_date": "2026-10-14",
            "pending_question": "Can you pay 637.50 on 14 October 2026? The rest stays overdue.",
            "account_authorized": "yes",
            "floor_offered": 1,
            "persuasion_used": 0,
            "event": "accept"
        }
        res = run_evaluate_code(self.code, init_vars)
        # Accept transitions to confirm for readback
        self.assertEqual(res["route"], "confirm")
        self.assertIn("Do you confirm?", res["say"])
        # Readback must NOT include overdue note or account facts
        self.assertNotIn("The rest stays overdue", res["say"])
        self.assertNotIn("The amount floor is", res["say"])

    def test_4b_robot_question_with_accept(self):
        # Caller says "Are you a robot? I will accept that date."
        init_vars = {
            "state": "negotiate",
            "now": "2026-10-14T11:00",
            "today": "2026-10-14",
            "deadline": "2026-10-23",
            "product_name": "car loan",
            "full_amount": 1250.00,
            "floor_amount": 375.00,
            "pending_amount": 1250.00,
            "pending_date": "2026-10-23",
            "pending_question": "Can you pay 1250.00 on 23 October 2026?",
            "account_authorized": "yes",
            "event": "accept",
            "question_kind": "robot"
        }
        res = run_evaluate_code(self.code, init_vars)
        self.assertEqual(res["route"], "confirm")
        # Must identify as digital assistant AND do readback
        self.assertTrue(res["say"].startswith("I am Freya Bank's digital assistant. For your car loan"))
        self.assertIn("Do you confirm?", res["say"])
        self.assertNotIn("The rest stays overdue", res["say"])



    def test_5_second_persuasion_late_band_offers_floor_on_deadline(self):
        # In late band (days_late >= 8), caller refused floor.
        # Persuasion attempt 2 proposes floor on deadline!
        init_vars = {
            "state": "negotiate",
            "now": "2026-10-14T11:00",
            "today": "2026-10-14",
            "deadline": "2026-10-23",
            "product_name": "credit card ending 1903",
            "full_amount": 2125.10,
            "floor_amount": 637.50,
            "pending_amount": 637.50,
            "pending_date": "2026-10-14",
            "account_authorized": "yes",
            "attempt_limit": 2,
            "persuasion_limit": 2,
            "persuasion_used": 1,
            "floor_offered": 1,
            "full_too_much": "yes",
            "event": "refuse"
        }
        res = run_evaluate_code(self.code, init_vars)
        # Attempt 2 must offer floor on deadline
        self.assertEqual(res["persuasion_used"], 2)
        self.assertEqual(res["pending_amount"], 637.50)
        self.assertEqual(res["pending_date"], "2026-10-23")
        self.assertIn("23 October 2026", res["say"])

    def test_6_inability_with_explicit_future_date(self):
        # Caller says: "The full amount is too much, but I can pay on 20 October."
        init_vars = {
            "state": "negotiate",
            "now": "2026-10-14T11:00",
            "today": "2026-10-14",
            "deadline": "2026-10-23",
            "product_name": "credit card ending 1903",
            "full_amount": 2125.10,
            "floor_amount": 637.50,
            "pending_amount": 2125.10,
            "pending_date": "2026-10-20",
            "account_authorized": "yes",
            "floor_offered": 0,
            "persuasion_used": 0,
            "event": "inability"
        }
        res = run_evaluate_code(self.code, init_vars)
        self.assertEqual(res["floor_offered"], 1)
        self.assertEqual(res["pending_amount"], 637.50)
        self.assertEqual(res["pending_date"], "2026-10-20")
        self.assertIn("20 October 2026", res["say"])

    def test_7_non_answer_after_floor_offer_clarifies_without_second_offer(self):
        # Floor already offered for Friday 16 Oct. Caller gives ambiguous non-answer: "You tell me."
        init_vars = {
            "state": "negotiate",
            "now": "2026-10-14T11:00",
            "today": "2026-10-14",
            "deadline": "2026-10-23",
            "product_name": "credit card ending 1903",
            "full_amount": 2125.10,
            "floor_amount": 637.50,
            "pending_amount": 637.50,
            "pending_date": "2026-10-16",
            "account_authorized": "yes",
            "floor_offered": 1,
            "persuasion_used": 1,
            "persuasion_limit": 2,
            "event": "non_answer"
        }
        res = run_evaluate_code(self.code, init_vars)
        # Must stay in negotiate and ask for confirmation of 16 Oct WITHOUT advancing to Attempt 2 (23 Oct)
        self.assertEqual(res["route"], "negotiate")
        self.assertEqual(res["pending_date"], "2026-10-16")
        self.assertEqual(res["pending_amount"], 637.50)
        self.assertEqual(res["floor_offered"], 1)
        self.assertEqual(res["persuasion_used"], 1)
        self.assertIn("16 October 2026", res["say"])
        self.assertNotIn("23 October", res["say"])


if __name__ == "__main__":
    unittest.main()


