"""Create a separate B diagnostic copy with deterministic aggregate read-back.

This is an experiment on the preserved B export, not the normal builder path.
"""
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya
from builder.validate import validate
from builder.layout import arrange

SOURCE = ROOT / "runs/build-20261010T231245Z-3cd302/workflow.export.json"


def make(workflow):
    workflow = copy.deepcopy(workflow)
    nodes = workflow["nodes"]
    engine = nodes["engine"]
    props = engine["pre_actions"][0]["function"]["parameters"]["properties"]
    code = props["code"]["default"]
    marker = "    vars['state_instruction'] = prompt\n"
    assert code.count(marker) == 1
    replacement = """    if s['stage'] == 'confirm' and action == 'talk':
        rows = []
        for p in s['products']:
            if p['status'] == 'draft':
                row = p['label'] + ': ' + str(p['amount']) + ' on ' + p['date']
                if p.get('common_adjustment'):
                    row += '. ' + p['common_adjustment']
                rows.append(row)
        if rows:
            vars['confirm_say'] = 'Please confirm these proposed payments: ' + '; '.join(rows) + '. Do you confirm?'
            vars['action'] = 'confirm_talk'
    vars['state_instruction'] = prompt
"""
    props["code"]["default"] = code.replace(marker, replacement, 1)
    confirm = copy.deepcopy(nodes["talk"])
    confirm["name"] = "confirm_talk"
    confirm["on_enter"] = {"type": "tts", "text": "{{confirm_say}}"}
    confirm["task_message"] = (
        "Speak only the fixed aggregate read-back from confirm_say. "
        "Wait for the customer's answer; the extractor must classify that answer "
        "against this complete read-back. Do not make a new offer."
    )
    nodes["confirm_talk"] = confirm
    talk_edge = next(i for i, edge in enumerate(engine["transitions"])
                     if edge["target_node"] == "talk")
    engine["transitions"].insert(talk_edge, {
        "condition": {"logic": "or", "conditions": [
            {"mode": "exact", "operand": "confirm_talk", "operator": "equals",
             "variable": "action"}]},
        "description": "Speak the current aggregate read-back as fixed text.",
        "target_node": "confirm_talk",
    })
    return arrange(workflow)


def main():
    run = ROOT / "runs" / ("diagnostic-b-confirm-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    run.mkdir()
    source = json.loads(SOURCE.read_text())["workflow"]
    candidate = make(source)
    spec = json.loads((ROOT / "tools/openapi.json").read_text())
    baseline_errors = validate(source, spec)
    errors = validate(candidate, spec)
    inherited_copy = "nodes/confirm_talk/extraction_schema/0: do not serialize several fields as a JSON object inside one string; define typed extraction fields"
    unexpected = [error for error in errors if error not in baseline_errors and error != inherited_copy]
    (run / "validation.json").write_text(json.dumps({
        "baseline_errors": baseline_errors, "candidate_errors": errors,
        "unexpected_errors": unexpected,
        "scope": "Legacy export already fails current validator; diagnostic copy only",
    }, indent=2))
    if unexpected:
        raise ValueError("New local validation failure; see validation.json")
    (run / "candidate.workflow.json").write_text(json.dumps(candidate, indent=2))
    freya.validate_workflow(run.name, candidate)
    ids = freya.create_workflow(run.name, candidate)
    (run / "candidate.json").write_text(json.dumps(ids, indent=2))
    freya.export_workflow(ids["workflow_id"], str(run / "workflow.export.json"))
    print("Diagnostic export:", run)
    print("Agent ID:", ids["agent_id"])


if __name__ == "__main__":
    main()
