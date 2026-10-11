"""Reproducible, guarded repair for the first Brief A candidate's identity gate.

This changes only the generated verification hooks and result handler. It does
not add UI test variables or any customer facts. A different workflow shape
must be regenerated instead of being patched by this module.
"""

from copy import deepcopy


def _replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Identity repair precondition failed; source changed")
    return source.replace(old, new, 1)


def repair(workflow: dict) -> dict:
    fixed = deepcopy(workflow)
    nodes = fixed["nodes"]
    if fixed.get("initial_node") != "initialize":
        raise ValueError("Identity repair expects the first generated candidate")
    fixed["system_prompt"] = _replace_once(
        fixed["system_prompt"],
        "Before BOTH security answers actually pass and all_verified is true, never mention collections, debt, payment, any product, or private account facts.",
        "Never mention collections, debt, payment, any product, or private account facts until BOTH security answers actually pass and either all_verified is true or get_account explicitly succeeds after those answers.",
    )

    for key in ("verify_dob", "verify_phone"):
        actions = nodes[key]["pre_actions"]
        if len(actions) != 1 or actions[0]["function"]["handler"] != "__function__:api_call":
            raise ValueError("Unexpected verification node")
        post = _replace_once(
            actions[0]["post_process_code"],
            "state = 'full' if yes(d.get('all_verified')) else 'passed'",
            "state = 'full' if yes(d.get('all_verified')) else ('passed_unconfirmed' if 'all_verified' not in d else 'passed')",
        )
        post = _replace_once(
            post,
            "Never disclose account information or say fully verified unless both checks passed and all_verified is true.",
            "Never disclose account information or say fully verified unless both checks passed and either all_verified is true or a subsequent get_account check explicitly succeeds.",
        )
        actions[0]["post_process_code"] = post

    action = nodes["action_result"]["pre_actions"][0]
    if action["function"]["name"] != "code_exec":
        raise ValueError("Unexpected result handler")
    code = action["function"]["parameters"]["properties"]["code"]["default"]
    code = _replace_once(
        code,
        "        elif status in ['passed','full'] and action == 'verify_dob':",
        "        elif status in ['passed','passed_unconfirmed','full'] and action == 'verify_dob':",
    )
    code = _replace_once(
        code,
        "        elif status == 'passed' and action == 'verify_phone':",
        """        elif status == 'passed_unconfirmed' and action == 'verify_phone' and vars.get('dob_pass') == 'yes':
            vars['verified_state'] = 'pending_account'
            vars['identity_technical'] = 0
            vars['flow_target'] = 'account'
        elif status == 'passed' and action == 'verify_phone':""",
    )
    code = _replace_once(
        code,
        "        if vars.get('verified_state') != 'full' or vars.get('dob_pass') != 'yes':",
        "        if vars.get('verified_state') not in ['full','pending_account'] or vars.get('dob_pass') != 'yes':",
    )
    code = _replace_once(
        code,
        """        elif status != 'ok':
            if vars['account_calls'] < 2:""",
        """        elif status != 'ok':
            if vars.get('verified_state') == 'pending_account':
                finish('no_promise','service_error','I could not complete identity confirmation. No account details can be discussed.')
            elif vars['account_calls'] < 2:""",
    )
    code = _replace_once(
        code,
        """        else:
            products = vars.get('account_products',[])""",
        """        else:
            if vars.get('verified_state') == 'pending_account':
                vars['verified_state'] = 'full'
            products = vars.get('account_products',[])""",
    )
    compile(code, "action_result", "exec")
    action["function"]["parameters"]["properties"]["code"]["default"] = code
    return fixed
