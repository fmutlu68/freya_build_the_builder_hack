"""Guarded Brief A repair: restructuring scope and stale extraction values.

Applied on top of builder.repair_question_in_negotiate output. It does not touch
readback/prefix behaviour.

Observed in call e60c2379 (PUB-06, candidate build-20261011T164343Z-48b503):
1. The `negotiate` event extractor labelled a cut-off reply that committed to the
   already discussed floor amount as `restructure`; the decision code turned that
   label directly into a restructuring transfer.
2. The decision code clears extracted values with `vars[key] = ''` in `finally`.
   The platform rejects '' for enum/float/date variables ("rejected by schema
   validation"), so previous-turn values survive: a failed extraction can reuse an
   old intent, and an `offer_date` copied from the agent's own offer stayed in state.

Repair (brief rules 21, 26, 27, 29, 41):
- Event descriptions: restructure = explicit request for a new payment plan or
  lower instalments (also when combined with inability to pay the floor);
  agreeing to the offered/floor amount or naming a day for it is accept/propose.
  A cut-off reply is classified from its readable part, the missing part is left
  empty, never inferred.
- offer_date prompt: only a day the caller states in the latest speech.
- Reset uses schema-valid sentinels: event='unclear', question_kind='none',
  date_kind='none', offer_amount=0.0. Non-positive amounts count as absent.
- An extracted calendar day counts only together with date_kind 'exact' (or when
  date_kind was never set), so a stale/copied day is not used as a new proposal.
- An `unclear` reply in negotiate/confirm that still carries a freshly extracted
  amount or date phrase is handled as a partial proposal: the understood part is
  kept and only the missing part is clarified or read back for confirmation.
No case IDs, names, amounts, dates or customer sentences are embedded.
"""

from copy import deepcopy


NEG_OLD_RESTRUCTURE = "restructure requires an explicit new plan or lower instalments, not ordinary inability."
NEG_NEW_RESTRUCTURE = (
    "restructure requires an explicit request for a new payment plan or lower instalments, not ordinary inability; "
    "it stays restructure when the caller also says they cannot pay the floor or minimum amount. "
    "Agreeing to pay the currently offered amount or the floor/minimum amount already discussed, or naming a day for it, "
    "is accept or propose, never restructure."
)
NEG_OLD_TRUNC = "Truncated or unreadable speech is unclear."
NEG_NEW_TRUNC = (
    "Unreadable speech is unclear. If a reply is cut off, classify only its readable part "
    "(for example a commitment to pay an amount is propose) and leave the missing day or amount empty; "
    "never infer restructure, refusal or a day from the missing part."
)
CONF_OLD_RESTRUCTURE = "restructure requires an explicit request for changed payment terms."
CONF_NEW_RESTRUCTURE = (
    "restructure requires an explicit request for a new payment plan or lower instalments; "
    "agreeing to the read-back amount/date or naming a day for that amount is confirm or change, never restructure."
)
DATE_OLD = "Do not infer a payment day from an absent or truncated extraction. Return a plain ISO date."
DATE_NEW = (
    "Do not infer a payment day from an absent or truncated extraction. "
    "Use only a day the caller states in the latest speech; never copy a day from the agent's own offer or earlier turns. "
    "Return a plain ISO date."
)

CODE_OLD_TERMS = """        has_amount = raw_amount not in ['', None]
        vague = kind == 'vague'
        has_date = (raw_date not in ['', None] or kind in ['today', 'tomorrow'] or kind.startswith('next_') or kind.startswith('this_')) and not vague"""
CODE_NEW_TERMS = """        has_amount = fresh_amount()
        vague = kind == 'vague'
        has_date = ((raw_date not in ['', None] and kind in ['exact', '']) or kind in ['today', 'tomorrow'] or kind.startswith('next_') or kind.startswith('this_')) and not vague"""

CODE_OLD_TERMS_DEF = "    def terms(prefix=''):\n"
CODE_NEW_TERMS_DEF = """    def fresh_amount():
        raw = vars.get('offer_amount')
        if raw in ['', None]:
            return False
        try:
            return money(raw) > 0
        except Exception:
            return True
    def partial_terms():
        kind = str(vars.get('date_kind') or '')
        return fresh_amount() or kind not in ['', 'none']
    def terms(prefix=''):
"""

CODE_OLD_RUN = """    run()
except Exception:"""
CODE_NEW_RUN = """    if event == 'unclear' and not vars.get('waiting_api') and state in ['negotiate', 'confirm'] and vars.get('account_authorized') == 'yes' and partial_terms():
        event = 'propose' if state == 'negotiate' else 'change'
    run()
except Exception:"""

CODE_OLD_RESET = """    for key in ['event', 'question_kind', 'dob_value', 'dob_raw', 'last4', 'offer_amount', 'offer_date', 'date_kind', 'callback_date', 'callback_time']:
        vars[key] = ''"""
CODE_NEW_RESET = """    for key in ['dob_value', 'dob_raw', 'last4', 'offer_date', 'callback_date', 'callback_time']:
        vars[key] = ''
    vars['event'] = 'unclear'
    vars['question_kind'] = 'none'
    vars['date_kind'] = 'none'
    vars['offer_amount'] = 0.0"""


def _replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f"{label} precondition failed: expected exactly one match")
    return text.replace(old, new, 1)


def _schema_field(node, name):
    for field in node.get("extraction_schema") or []:
        if field.get("name") == name:
            return field
    raise ValueError(f"Missing extraction field {name}")


def repair(workflow: dict) -> dict:
    fixed = deepcopy(workflow)
    nodes = fixed.get("nodes") or {}
    for required in ["evaluate", "negotiate", "confirm"]:
        if required not in nodes:
            raise ValueError(f"Missing node {required}")

    neg_event = _schema_field(nodes["negotiate"], "event")
    if "restructure" not in (neg_event.get("enum_values") or []):
        raise ValueError("negotiate event enum lacks restructure")
    desc = neg_event["description"]
    desc = _replace_once(desc, NEG_OLD_RESTRUCTURE, NEG_NEW_RESTRUCTURE, "negotiate restructure description")
    desc = _replace_once(desc, NEG_OLD_TRUNC, NEG_NEW_TRUNC, "negotiate truncation description")
    neg_event["description"] = desc

    conf_event = _schema_field(nodes["confirm"], "event")
    conf_event["description"] = _replace_once(conf_event["description"], CONF_OLD_RESTRUCTURE, CONF_NEW_RESTRUCTURE, "confirm restructure description")

    neg_date = _schema_field(nodes["negotiate"], "offer_date")
    neg_date["extraction_prompt"] = _replace_once(neg_date["extraction_prompt"], DATE_OLD, DATE_NEW, "negotiate offer_date prompt")

    # Sentinels used by the reset must be valid for every node schema of that variable.
    for node in nodes.values():
        for field in node.get("extraction_schema") or []:
            enum = field.get("enum_values")
            if field.get("name") == "event" and enum and "unclear" not in enum:
                raise ValueError("event sentinel 'unclear' not valid in every schema")
            if field.get("name") in ["question_kind", "date_kind"] and enum and "none" not in enum:
                raise ValueError(f"{field['name']} sentinel 'none' not valid in every schema")
            if field.get("name") == "offer_amount" and field.get("type") not in ["float", "number"]:
                raise ValueError("offer_amount is not a float field")

    code_field = nodes["evaluate"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
    code = code_field["default"]
    code = _replace_once(code, CODE_OLD_TERMS, CODE_NEW_TERMS, "terms freshness")
    code = _replace_once(code, CODE_OLD_TERMS_DEF, CODE_NEW_TERMS_DEF, "terms helpers")
    code = _replace_once(code, CODE_OLD_RUN, CODE_NEW_RUN, "partial unclear terms")
    code = _replace_once(code, CODE_OLD_RESET, CODE_NEW_RESET, "typed reset")
    compile(code, "evaluate", "exec")
    code_field["default"] = code
    return fixed
