"""Offline checks for builder.repair_restructure_scope.

The decision code is the real `evaluate` snippet of the repaired candidate. The
extractor output for each turn is supplied by the test (no LLM, no network), so
these checks cover deterministic workflow logic and the schema text only, not the
platform extractor's actual labels.
"""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from builder.repair_restructure_scope import repair
from builder.validate import validate

BASE = ROOT / "runs" / "build-20261011T164343Z-48b503" / "candidate-0.workflow.json"

# Synthetic state, not a public case: late band, floor already offered once.
STATE = {
    "state": "negotiate",
    "now": "2026-03-04T10:00",
    "deadline": "2026-03-13",
    "product_name": "personal loan",
    "full_amount": 900.00,
    "floor_amount": 300.00,
    "pending_amount": 300.00,
    "pending_date": "2026-03-06",
    "pending_question": "Can you pay 300.00 on 6 March 2026? The rest stays overdue.",
    "offer_mode": "floor",
    "floor_offered": 1,
    "persuasion_used": 1,
    "persuasion_limit": 2,
    "refused_offers": [],
    "hardship_active": "no",
    "account_authorized": "yes",
    "account_facts": "Your personal loan has a past-due amount of 900.00.",
    "days_late": 20,
}


def evaluate(code, variables):
    scope = {"vars": dict(variables)}
    exec(code, scope)
    return scope["vars"]


def turn(code, previous, extracted):
    """Platform-like turn: only freshly extracted keys overwrite the variable table."""
    table = dict(previous)
    table.update(extracted)
    return evaluate(code, table)


class RestructureScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads(BASE.read_text())
        cls.wf = repair(cls.base)
        cls.code = cls.wf["nodes"]["evaluate"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        cls.base_code = cls.base["nodes"]["evaluate"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        cls.errors = validate(cls.wf, json.loads((ROOT / "tools" / "openapi.json").read_text()))

    def test_validation_and_readback_untouched(self):
        self.assertEqual(self.errors, [])
        start = self.base_code.index("    def readback(prefix=''):")
        end = self.base_code.index("    def rejected_pair():")
        self.assertIn(self.base_code[start:end], self.code)

    def test_schema_text_distinguishes_restructure(self):
        neg = {f["name"]: f for f in self.wf["nodes"]["negotiate"]["extraction_schema"]}
        desc = neg["event"]["description"]
        self.assertIn("new payment plan or lower instalments", desc)
        self.assertIn("cannot pay the floor or minimum amount", desc)
        self.assertIn("is accept or propose, never restructure", desc)
        self.assertNotIn("Truncated or unreadable speech is unclear.", desc)
        self.assertIn("never copy a day from the agent's own offer", neg["offer_date"]["extraction_prompt"])

    # 1. Floor amount on a day -> payment negotiation and readback, not transfer.
    def test_1_floor_on_day_is_negotiation(self):
        out = turn(self.code, STATE, {"event": "propose", "offer_amount": 300.0, "date_kind": "this_friday"})
        self.assertEqual(out["route"], "confirm")
        self.assertIn("300.00 on 6 March 2026. Do you confirm?", out["say"])
        self.assertNotEqual(out.get("transfer_queue"), "restructuring")

    # 2. New plan / lower instalments -> rule 41 transfer, no extra confirmation step.
    def test_2_new_plan_is_restructuring(self):
        out = turn(self.code, STATE, {"event": "restructure"})
        self.assertEqual(out["route"], "transfer_to_agent")
        self.assertEqual(out["transfer_queue"], "restructuring")

    # 3a. Cut-off commitment to the amount with an incomplete day: keep amount, ask only the day.
    def test_3a_cut_off_amount_vague_day(self):
        out = turn(self.code, STATE, {"event": "propose", "offer_amount": 300.0, "date_kind": "vague"})
        self.assertEqual(out["route"], "negotiate")
        self.assertEqual(out["say"], "What exact day do you mean for this payment?")
        self.assertEqual(float(out["pending_amount"]), 300.0)
        self.assertNotEqual(out.get("transfer_queue"), "restructuring")

    # 3b. Same, but the extractor returns unclear: understood amount still kept, no transfer, no invented day.
    def test_3b_cut_off_unclear_keeps_understood_part(self):
        out = turn(self.code, STATE, {"event": "unclear", "offer_amount": 300.0, "date_kind": "vague"})
        self.assertEqual(out["route"], "negotiate")
        self.assertEqual(out["say"], "What exact day do you mean for this payment?")
        self.assertEqual(float(out["pending_amount"]), 300.0)

    # 3c. Nothing readable extracted: plain clarification.
    def test_3c_unclear_without_terms_clarifies(self):
        out = turn(self.code, STATE, {"event": "unclear"})
        self.assertEqual(out["route"], "negotiate")
        self.assertIn("could not clearly understand", out["say"])

    # 4. Cannot pay the floor + explicit new plan -> restructuring, even if an amount was mentioned.
    def test_4_inability_plus_new_plan_is_restructuring(self):
        out = turn(self.code, STATE, {"event": "restructure", "offer_amount": 300.0})
        self.assertEqual(out["route"], "transfer_to_agent")
        self.assertEqual(out["transfer_queue"], "restructuring")

    # 5. Robot question + acceptance in one reply: prefix kept, clean readback.
    def test_5_robot_question_with_accept(self):
        out = turn(self.code, STATE, {"event": "accept", "question_kind": "robot"})
        self.assertEqual(out["route"], "confirm")
        self.assertTrue(out["say"].startswith("I am Freya Bank's digital assistant. For your personal loan"))
        self.assertNotIn("The rest stays overdue", out["say"])

    # Stale values: a failed extraction must not reuse the previous intent or day.
    def test_reset_uses_schema_valid_sentinels(self):
        out = turn(self.code, STATE, {"event": "non_answer", "offer_date": "2026-03-06"})
        self.assertEqual(out["event"], "unclear")
        self.assertEqual(out["question_kind"], "none")
        self.assertEqual(out["date_kind"], "none")
        self.assertEqual(out["offer_amount"], 0.0)

    def test_failed_extraction_does_not_reuse_restructure(self):
        # Previous turn left event=restructure in the table (old reset was rejected); new code resets it.
        first = turn(self.code, STATE, {"event": "question", "question_kind": "account"})
        stale_table = dict(first)
        second = turn(self.code, stale_table, {})  # extraction failed this turn
        self.assertNotEqual(second["route"], "transfer_to_agent")
        self.assertEqual(second["route"], "negotiate")

    def test_copied_day_without_date_phrase_is_not_a_proposal(self):
        # offer_date survived from an earlier turn (date type cannot be reset) but no date phrase now.
        table = dict(STATE, offer_date="2026-03-10", date_kind="none", offer_amount=300.0, event="propose")
        out = evaluate(self.code, table)
        self.assertNotIn("10 March", out["say"])

    def test_explicit_exact_day_still_works(self):
        out = turn(self.code, STATE, {"event": "propose", "offer_date": "2026-03-10", "date_kind": "exact"})
        self.assertEqual(out["route"], "confirm")
        self.assertIn("300.00 on 10 March 2026", out["say"])

    def test_api_return_not_affected_by_sentinel(self):
        table = dict(STATE, event="unclear", waiting_api="promise", api_json=json.dumps({"ok": True}),
                     state="confirm", confirm_authorized="yes", pending_date="2026-03-06")
        out = evaluate(self.code, table)
        self.assertNotIn("could not clearly understand", str(out.get("say")))


if __name__ == "__main__":
    unittest.main()
