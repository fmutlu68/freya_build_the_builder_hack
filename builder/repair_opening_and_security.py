"""Guarded security-answer repair, retaining Brief A's two-ask opening rule."""

from copy import deepcopy


def _replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Opening/security repair precondition failed")
    return source.replace(old, new, 1)


def repair(workflow: dict) -> dict:
    fixed = deepcopy(workflow)
    nodes = fixed["nodes"]
    if fixed.get("initial_node") != "initialize":
        raise ValueError("Unexpected workflow")
    code_field = nodes["evaluate"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
    code = code_field["default"]
    code = _replace_once(
        code,
        "confirmed = event == 'identity_confirmation' and (clean in ['yes','thats me','speaking',own,str(vars.get('first_name') or '').lower(),str(vars.get('last_name') or '').lower()] or clean.startswith('yes ') or clean.startswith('thats me ') or clean.startswith('speaking ') or own and own in clean)",
        "confirmed = bool(clean) and clean in ['yes','thats me','speaking',own,str(vars.get('first_name') or '').lower()]",
    )
    code = _replace_once(
        code,
        "elif event in ['answer','proposal','identity_confirmation']:\n            valid = False",
        "elif event in ['answer','proposal','identity_confirmation','vague_date'] or (stage == 'dob' and re.fullmatch(r'\\d{4}-\\d{2}-\\d{2}', answer)):\n            valid = False",
    )
    compile(code, "evaluate", "exec")
    code_field["default"] = code
    for name in ("opening", "dob", "phone"):
        node = nodes[name]
        node["task_message"] = _replace_once(
            node["task_message"],
            "Speak the prepared facts and one question, then wait.",
            "Follow speech_task as the sole instruction for what to say next; do not advance the stage based on the caller's answer yourself. Speak the prepared facts and one question, then wait.",
        )
    nodes["opening"]["task_message"] += " While this node is active, ask only whether the named customer is speaking. Never ask for date of birth here."
    return fixed
