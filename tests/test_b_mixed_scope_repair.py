"""Deterministic checks for the Brief B mixed-product repair (no Freya calls)."""

import json
from pathlib import Path
import unittest

from builder.repair_b_mixed_scope import repair
from builder.validate import validate


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "runs/build-20261011T150532Z-a05a27/candidate-0.salvaged.workflow.json"
PRODUCTS = [
    {"product_id": "card", "type": "credit_card", "card_last4": "1234", "past_due": 500, "minimum_payment": 150, "days_late": 16},
    {"product_id": "loan-a", "type": "personal_loan", "past_due": 800, "instalment_amount": 200, "days_late": 16},
    {"product_id": "loan-b", "type": "car_loan", "past_due": 300, "instalment_amount": 100, "days_late": 6},
]


class MixedScopeRepairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = repair(json.loads(SOURCE.read_text()))
        cls.code = cls.workflow["nodes"]["process"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]

    def setUp(self):
        self.v = {"now": "2026-10-14T10:00:00Z", "customer_id": "synthetic", "title": "Ms", "last_name": "Smith"}
        self.step()
        self.step(e_intent="self")
        self.step(e_intent="answer", e_answer="1990-01-01")
        self.step(reply={"ok": True, "verified": True})
        self.step(e_intent="answer", e_answer="1234")
        self.step(reply={"ok": True, "verified": True, "all_verified": True})
        self.step(reply={"ok": True, "products": PRODUCTS})

    def step(self, reply=None, **extracted):
        for key in ("e_intent", "e_answer", "e_date_kind", "e_date", "e_amount", "e_target", "e_scope"):
            self.v.pop(key, None)
        self.v.update(extracted)
        if reply is not None:
            self.v["api_reply"] = json.dumps({"kind": "business", "body": reply})
        exec(self.code, {"vars": self.v})
        self.assertNotEqual(self.v["route"], "fault")
        transitions = self.workflow["nodes"]["process"]["transitions"]
        def matches(condition):
            if "conditions" in condition:
                answers = [matches(item) for item in condition["conditions"]]
                return any(answers) if condition["logic"] == "or" else all(answers)
            return condition["operator"] == "always" or (
                condition["operator"] == "equals"
                and self.v.get(condition["variable"]) == condition["operand"]
            )
        actual_target = next(item["target_node"] for item in transitions if matches(item["condition"]))
        self.assertEqual(actual_target, self.v["route"])
        return json.loads(self.v["wf_state"])

    def test_mixed_reply_preserves_decisions_until_scope_is_clear(self):
        state = self.step(e_intent="proposal", e_target=-1, e_scope="mixed", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["open", "open", "open"])
        self.assertEqual([p["attempts"] for p in state["products"]], [0, 0, 0])
        self.assertEqual(state["stage"], "scope_clarify")
        self.assertEqual(state["scope_focus"], 0)
        self.assertIn("credit card", self.v["speech"])
        state = self.step(e_intent="proposal", e_target=0, e_scope="only_one", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "open", "open"])
        self.assertEqual(state["products"][0]["date"], "2026-10-15")
        self.assertEqual(state["stage"], "product")
        self.assertIn("personal loan", self.v["speech"])

    def test_unknown_mixed_target_never_becomes_all_products(self):
        state = self.step(e_intent="proposal", e_target=-1, e_scope="mixed", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["open", "open", "open"])
        self.assertEqual(state["stage"], "scope_clarify")
        state = self.step(e_intent="proposal", e_target=-1, e_scope="mixed", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "open", "open"])
        self.assertEqual(state["stage"], "product")

    def test_exclusive_readback_correction_reopens_other_products(self):
        state = self.step(e_intent="proposal", e_target=-1, e_scope="all", e_date_kind="tomorrow")
        self.assertEqual(state["stage"], "readback")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed"] * 3)
        state = self.step(e_intent="proposal", e_target=0, e_scope="only_one", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "open", "open"])
        self.assertEqual(state["stage"], "product")
        self.assertNotIn("car loan", self.v["speech"])

    def test_nonexclusive_one_product_change_keeps_other_agreements(self):
        self.step(e_intent="proposal", e_target=-1, e_scope="all", e_date_kind="tomorrow")
        state = self.step(e_intent="proposal", e_target=0, e_scope="one", e_date_kind="next_business_day")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed"] * 3)
        self.assertEqual(state["stage"], "readback")

    def test_explicit_all_scope_overrides_incidental_single_target(self):
        state = self.step(e_intent="proposal", e_target=0, e_scope="all", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed"] * 3)
        self.assertEqual(state["stage"], "readback")

    def test_mixed_readback_correction_clears_unconfirmed_loans(self):
        self.step(e_intent="proposal", e_target=-1, e_scope="all", e_date_kind="tomorrow")
        state = self.step(e_intent="proposal", e_target=0, e_scope="mixed", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed"] * 3)
        self.assertEqual(state["stage"], "scope_clarify")
        state = self.step(e_intent="proposal", e_target=0, e_scope="only_one", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "open", "open"])
        self.assertEqual(state["stage"], "product")

    def test_missing_scope_does_not_expand_one_date_to_all_products(self):
        state = self.step(e_intent="proposal", e_target=-1, e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["open", "open", "open"])
        self.assertEqual(state["stage"], "scope_clarify")

    def test_yes_to_aggregate_question_is_all_in_context(self):
        state = self.step(e_intent="yes", e_target=-1)
        self.assertEqual([p["status"] for p in state["products"]], ["agreed"] * 3)
        self.assertEqual(state["stage"], "readback")

    def test_excluded_product_cannot_be_resurrected_at_readback(self):
        self.step(e_intent="proposal", e_target=0, e_scope="one", e_date_kind="tomorrow")
        self.step(e_intent="refuse", e_target=1)
        self.step(e_intent="refuse", e_target=1)
        state = self.step(e_intent="refuse", e_target=2)
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "excluded", "excluded"])
        before = [p["attempts"] for p in state["products"]]
        state = self.step(e_intent="proposal", e_target=2, e_scope="one", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "excluded", "excluded"])
        self.assertEqual([p["attempts"] for p in state["products"]], before)
        self.assertEqual(state["stage"], "scope_clarify")

    def test_active_product_refusal_wins_over_other_product_target(self):
        self.step(e_intent="proposal", e_target=0, e_scope="one", e_date_kind="tomorrow")
        state = self.step(e_intent="refuse", e_target=0, e_scope="mixed")
        self.assertEqual(state["products"][0]["status"], "agreed")
        self.assertEqual(state["products"][1]["attempts"], 2)
        self.assertEqual(state["stage"], "product")

    def test_exclusive_correction_never_clears_recorded_promise(self):
        state = self.step(e_intent="proposal", e_target=-1, e_scope="all", e_date_kind="tomorrow")
        state["products"][0]["status"] = "recorded"
        state["recorded"] = 1
        self.v["wf_state"] = json.dumps(state)
        state = self.step(e_intent="proposal", e_target=1, e_scope="only_one", e_date_kind="tomorrow")
        self.assertEqual(state["products"][0]["status"], "recorded")
        self.assertEqual(state["recorded"], 1)

    def test_same_terms_affirmation_after_single_product_readback_progresses(self):
        self.step(e_intent="proposal", e_target=0, e_scope="one", e_date_kind="tomorrow")
        self.step(e_intent="refuse", e_target=1)
        self.step(e_intent="refuse", e_target=1)
        self.step(e_intent="refuse", e_target=2)
        state = self.step(e_intent="proposal", e_target=0, e_scope="one", e_date_kind="tomorrow")
        self.assertEqual(state["stage"], "readback")
        self.assertEqual(self.v["route"], "create_promise")

    def test_multiturn_mixed_answer_through_notes_and_promise(self):
        state = self.step(e_intent="proposal", e_target=-1, e_scope="mixed", e_date_kind="tomorrow")
        self.assertEqual((state["stage"], state["scope_focus"]), ("scope_clarify", 0))
        state = self.step(e_intent="proposal", e_target=0, e_scope="only_one", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "open", "open"])
        self.assertEqual([p["attempts"] for p in state["products"]], [0, 1, 0])
        state = self.step(e_intent="refuse", e_target=1)
        self.assertEqual([p["attempts"] for p in state["products"]], [0, 2, 0])
        state = self.step(e_intent="refuse", e_target=1)
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "excluded", "open"])
        self.assertEqual([p["attempts"] for p in state["products"]], [0, 2, 1])
        state = self.step(e_intent="refuse", e_target=2)
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "excluded", "excluded"])
        self.assertEqual([p["attempts"] for p in state["products"]], [0, 2, 1])
        self.assertEqual(state["stage"], "readback")
        self.assertNotIn("personal loan", self.v["speech"])
        self.assertNotIn("car loan", self.v["speech"])
        self.step(e_intent="yes")
        self.assertEqual(self.v["route"], "create_promise")
        self.step(reply={"ok": True, "promise_id": "synthetic"})
        self.assertEqual(self.v["route"], "add_note")
        self.step(reply={"ok": True})
        self.assertEqual(self.v["route"], "add_note")
        state = self.step(reply={"ok": True})
        self.assertEqual(self.v["route"], "end")
        self.assertEqual([p["status"] for p in state["products"]], ["recorded", "excluded", "excluded"])
        self.assertEqual(self.v["close_outcome"], "promise")

    def test_mixed_clear_card_terms_are_kept_without_repeat_question(self):
        state = self.step(e_intent="proposal", e_target=0, e_scope="mixed", e_date_kind="tomorrow")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "open", "open"])
        self.assertEqual(state["products"][0]["date"], "2026-10-15")
        self.assertEqual(state["stage"], "product")
        self.assertEqual(self.v["route"], "negotiation")
        self.assertIn("personal loan", self.v["speech"])
        self.assertNotIn("Can you pay all", self.v["speech"])
        state = self.step(e_intent="refuse", e_target=1)
        self.assertEqual(state["products"][1]["attempts"], 2)
        state = self.step(e_intent="refuse", e_target=1)
        self.assertEqual(state["products"][1]["status"], "excluded")
        self.assertEqual(state["stage"], "product")
        self.assertIn("car loan", self.v["speech"])
        state = self.step(e_intent="refuse", e_target=2)
        self.assertEqual(state["stage"], "readback")
        self.assertEqual([p["status"] for p in state["products"]], ["agreed", "excluded", "excluded"])
        self.assertIn("credit card", self.v["speech"])
        self.assertNotIn("personal loan", self.v["speech"])
        self.assertNotIn("car loan", self.v["speech"])

    def test_local_schema(self):
        openapi = json.loads((ROOT / "tools/openapi.json").read_text())
        self.assertEqual(validate(self.workflow, openapi), [])
        focus_fields = [field["name"] for field in self.workflow["nodes"]["scope_clarify"]["extraction_schema"]]
        self.assertEqual(len(focus_fields), 5)
        self.assertNotIn("e_target", focus_fields)
        transitions = self.workflow["nodes"]["process"]["transitions"]
        scope_index = next(i for i, item in enumerate(transitions) if item["target_node"] == "scope_clarify")
        fault_index = next(i for i, item in enumerate(transitions) if item["target_node"] == "fault")
        self.assertLess(scope_index, fault_index)
        self.assertEqual(transitions[scope_index]["condition"]["conditions"][0],
                         {"variable": "route", "operator": "equals", "operand": "scope_clarify"})


if __name__ == "__main__":
    unittest.main()
