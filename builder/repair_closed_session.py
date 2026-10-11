"""Recognize the mock bank's terminal closed-session result explicitly."""

from copy import deepcopy


def _replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Closed-session repair precondition failed")
    return source.replace(old, new, 1)


def repair(workflow: dict) -> dict:
    fixed = deepcopy(workflow)
    nodes = fixed["nodes"]
    for name in ("verify_dob", "verify_phone"):
        action = nodes[name]["pre_actions"][0]
        action["post_process_code"] = _replace_once(
            action["post_process_code"],
            "state = 'malformed' if any(w in error for w in ['unreadable','invalid date','date format','parse','four digits','4 digits','malformed']) else 'service'",
            "state = 'session_closed' if 'the call is already closed' in error else ('malformed' if any(w in error for w in ['unreadable','invalid date','date format','parse','four digits','4 digits','malformed']) else 'service')",
        )
    field = nodes["action_result"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
    code = _replace_once(
        field["default"],
        "        elif status == 'swapped':",
        """        elif status == 'session_closed':
            finish('no_promise','service_error','I cannot complete the identity check in this call because the bank session is no longer active. Your answer was not marked wrong. Please start a new call later or use the mobile app or a branch.')
        elif status == 'swapped':""",
    )
    compile(code, "action_result", "exec")
    field["default"] = code
    return fixed
