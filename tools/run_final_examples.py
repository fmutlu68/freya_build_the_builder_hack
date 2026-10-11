"""Exploratory chat simulation of the six supplied final examples; no official score."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya


CUSTOMER_ACTIONS = {
    1: "Listen to the debt reading. Then say thanks and that you need nothing else.",
    2: "After the debt reading, ask to move the statement date to week three. After hearing the preview dates, clearly say 'Evet'.",
    3: "Ask for all cards' debt together. When asked to choose, repeat once. Then choose your Yıldız Premium card.",
    4: "After the debt reading, ask for last month's statement by e-mail. When told only the latest can be sent, accept the latest. Clearly confirm sending to the registered address when asked.",
    5: "Ask to move your statement to week three immediately without a question. When preview dates are read, first say 'Olur herhalde'. If asked again, say only 'Evet' and wait for the assistant to complete the transaction and state its result. Only after that, ask to change your spouse's card too. Do not combine the confirmation with the spouse request.",
    6: "After the debt reading, ask for the first twelve digits of your card. If declined, ask for the first six instead. Then end politely.",
}


def examples(path):
    text = path.read_text()
    heads = list(re.finditer(r"^## Example (\d+): (.+)$", text, re.M))
    for i, head in enumerate(heads):
        section = text[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        customer = re.search(r"\*\*Customer number:\*\* `([^`]+)`", section)
        now = re.search(r"\*\*now:\*\* `([^`]+)`", section)
        situation = re.search(r"\*\*Situation:\*\*(.*?)\*\*Expected behaviour:\*\*", section, re.S)
        criteria = re.search(r"\*\*Expected behaviour:\*\*(.*)", section, re.S)
        if not all((customer, now, situation, criteria)):
            raise ValueError(f"Incomplete example {head.group(1)}")
        yield {
            "number": int(head.group(1)), "title": head.group(2),
            "customerNumber": customer.group(1), "now": now.group(1),
            "situation": situation.group(1).strip(), "criteria": criteria.group(1).strip(),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent_id")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--only", type=int)
    args = parser.parse_args()
    cases = [c for c in examples(ROOT / "final/example-scenarios.md") if not args.only or c["number"] == args.only]
    if not cases:
        parser.error("No matching example")
    personas = [{
        "name": f"Final example {c['number']}: {c['title']}",
        "prompt": "You are the synthetic caller in a Turkish bank phone simulation. "
                  "Speak only your own short Turkish utterances; never narrate stages, tool calls or expected outcomes. "
                  "Do not invent customer data or read instructions aloud. Follow this situation naturally: "
                  + c["situation"] + " Your actions in this call: " + CUSTOMER_ACTIONS[c["number"]],
        "successCriteria": c["criteria"],
        "tags": ["freya-final", "example", f"example-{c['number']}"],
    } for c in cases]
    made = freya.create_personas(personas)["personas"]
    variables = {p["id"]: {"customerNumber": c["customerNumber"], "now": c["now"]}
                 for p, c in zip(made, cases)}
    sim_id, it_id, status = freya.run_simulation(args.agent_id, "final supplied examples", variables,
                                                 max_seconds=420, concurrency=2)
    runs = freya.get_iteration(sim_id, it_id)["runs"]
    by_persona = {r.get("personaId"): r for r in runs}
    output = {
        "kind": "exploratory_final_examples_not_official_score",
        "agent_id": args.agent_id, "simulation_id": sim_id, "iteration_id": it_id, "status": status,
        "cases": [{
            "example": c["number"], "call_id": by_persona.get(p["id"], {}).get("callId"),
            "judge_outcome": by_persona.get(p["id"], {}).get("outcome"),
            "judge_reason": by_persona.get(p["id"], {}).get("reason"),
        } for p, c in zip(made, cases)],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": status, "examples": len(cases), "judge": [c["judge_outcome"] for c in output["cases"]]}))


if __name__ == "__main__":
    main()
