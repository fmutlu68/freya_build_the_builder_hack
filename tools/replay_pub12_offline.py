"""Replay PUB-12 decisions through exported phone code with synthetic tool replies.

This does not run Freya speech/extraction, the practice bank, or the PUB judge.
"""
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "runs/build-20261011T150532Z-a05a27/salvage-workflow.export.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", type=Path, default=EXPORT)
    parser.add_argument("--mixed-clarify", action="store_true", help="Replay mixed answer, focused clarification, then product refusals")
    args = parser.parse_args()
    case = next(c for c in json.loads((ROOT / "public-test-set.json").read_text())
                if c["id"] == "PUB-12")
    loaded = json.loads(args.workflow.read_text())
    workflow = loaded.get("workflow", loaded)
    code = workflow["nodes"]["process"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    vars_ = {**case["variables"]}
    history = []

    def step(label, *, intent=None, answer=None, date_kind=None, amount=None,
             target=None, scope=None, reply=None):
        for key in ("e_intent", "e_answer", "e_date_kind", "e_date", "e_amount", "e_target", "e_scope"):
            vars_.pop(key, None)
        if intent is not None:
            vars_["e_intent"] = intent
        if answer is not None:
            vars_["e_answer"] = answer
        if date_kind is not None:
            vars_["e_date_kind"] = date_kind
        if amount is not None:
            vars_["e_amount"] = amount
        if target is not None:
            vars_["e_target"] = target
        if scope is not None:
            vars_["e_scope"] = scope
        if reply is not None:
            vars_["api_reply"] = json.dumps({"kind": "business", "body": reply})
        exec(code, {"vars": vars_})
        state = json.loads(vars_["wf_state"])
        if vars_.get("route") == "fault":
            raise AssertionError(f"{label}: code fault")
        history.append({"step": label, "stage": state["stage"],
                        "route": vars_.get("route"), "speech": vars_.get("speech", ""),
                        "products": [{"id": p["product_id"], "status": p["status"],
                                      "attempts": p["attempts"], "reason": p["reason"]}
                                     for p in state["products"]]})
        return state

    step("start")
    step("customer confirms identity", intent="self")
    step("date of birth answered", intent="answer", answer=case["identity"]["date_of_birth"])
    step("DOB tool passes", reply={"ok": True, "verified": True})
    step("phone answered incorrectly", intent="answer", answer="4401")
    step("phone tool rejects", reply={"ok": True, "verified": False, "wrong_answers_left": 2})
    step("phone answered correctly", intent="answer", answer=case["identity"]["phone_last4"])
    step("phone tool passes", reply={"ok": True, "verified": True, "all_verified": True})
    products = [dict(product, product_id=f"p{i}") for i, product in enumerate(case["products"], 1)]
    step("account tool returns three products", reply={"ok": True, "products": products})
    if args.mixed_clarify:
        state = step("mixed card payment and two refusals", intent="proposal", target=-1,
                     scope="mixed", date_kind="tomorrow")
        assert state["stage"] == "scope_clarify"
        assert [p["status"] for p in state["products"]] == ["open", "open", "open"]
        state = step("customer clarifies only card tomorrow", intent="proposal", target=0,
                     scope="only_one", date_kind="tomorrow", amount=case["products"][0]["past_due"])
        assert state["stage"] == "product"
        assert [p["status"] for p in state["products"]] == ["agreed", "open", "open"]
    else:
        step("customer offers card payment tomorrow", intent="proposal", target=0, scope="one",
             date_kind="tomorrow", amount=case["products"][0]["past_due"])
    step("customer refuses personal loan offer", intent="refuse")
    step("customer refuses final personal loan offer", intent="refuse")
    state = step("customer refuses car loan offer", intent="refuse")
    assert state["stage"] == "readback", state["stage"]
    assert state["products"][2]["attempts"] == 1
    assert state["products"][2]["status"] == "excluded"
    assert "car loan" not in vars_["speech"].lower(), vars_["speech"]
    step("customer confirms aggregate readback", intent="yes")
    step("promise tool records card", reply={"ok": True, "promise_id": "synthetic"})
    step("note tool records personal loan refusal", reply={"ok": True})
    step("note tool records car loan refusal", reply={"ok": True})
    final = json.loads(vars_["wf_state"])
    assert vars_.get("close_outcome") == "promise"
    assert final["products"][0]["amount"] == case["expected"]["promises"][0]["amount"]
    assert final["products"][0]["date"] == case["expected"]["promises"][0]["date"]
    assert [p["attempts"] for p in final["products"][1:]] == [2, 1]
    routes = [x["route"] for x in history]
    assert routes.count("verify_identity") == 3
    assert routes.count("create_promise") == 1
    assert routes.count("add_note") == 2
    assert [(p["product_id"], p["status"], p["reason"]) for p in final["products"]] == [
        ("p1", "recorded", ""), ("p2", "excluded", "refused"),
        ("p3", "excluded", "refused")]
    print(json.dumps({"result": "offline_policy_path_pass", "scope": "deterministic code only",
                      "stages": [(x["step"], x["stage"], x["route"]) for x in history],
                      "final": {"outcome": vars_.get("close_outcome"),
                                "products": history[-1]["products"]}}, indent=2))


if __name__ == "__main__":
    main()
