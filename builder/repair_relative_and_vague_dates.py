"""Guarded repair for relative dates, vague date priority, and transient API retries."""

from copy import deepcopy
import json
import re


def repair(workflow: dict) -> dict:
    fixed = deepcopy(workflow)
    if fixed.get("initial_node") != "initialize":
        raise ValueError("Unexpected workflow structure")

    # 1. Update negotiate extraction schema date_kind enum
    neg = fixed["nodes"].get("negotiate")
    if not neg:
        raise ValueError("Missing negotiate node")
    for f in neg.get("extraction_schema", []):
        if f.get("name") == "date_kind":
            enums = f.get("enum_values", [])
            for val in ["today", "tomorrow"]:
                if val not in enums:
                    enums.append(val)
            f["enum_values"] = enums
            f["description"] = (
                "Characterize the date phrase in the latest reply. today means today relative to now; "
                "tomorrow means tomorrow relative to now; vague means next week, end of month, salary "
                "timing or another period without an exact day; exact for an explicit calendar date; "
                "next_/this_ weekday for those explicit weekday phrases; none when no date phrase is present."
            )
            break
    else:
        raise ValueError("Missing date_kind in negotiate extraction schema")

    # 2. Add date_kind to callback node extraction schema
    cb = fixed["nodes"].get("callback")
    if not cb:
        raise ValueError("Missing callback node")
    cb_schema = cb.get("extraction_schema", [])
    if not any(f.get("name") == "date_kind" for f in cb_schema):
        cb_schema.append({
            "name": "date_kind",
            "type": "string",
            "description": (
                "Classification of the proposed callback day. today means today relative to now; "
                "tomorrow means tomorrow relative to now; vague means a period without a specific day; "
                "exact means an explicit calendar date; next_/this_ weekday for explicit weekday phrases; "
                "none if no day was mentioned."
            ),
            "enum_values": [
                "none", "exact", "vague", "today", "tomorrow",
                "next_monday", "next_tuesday", "next_wednesday", "next_thursday", "next_friday", "next_saturday", "next_sunday",
                "this_monday", "this_tuesday", "this_wednesday", "this_thursday", "this_friday", "this_saturday", "this_sunday"
            ],
            "max_retries": 1,
            "min_confidence": 0.8
        })

    # 3. Update evaluate node Python code
    node = fixed["nodes"]["evaluate"]
    code_field = node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
    code = code_field["default"]

    # (a) proposed_date: handle today and tomorrow
    old_pd = """    def proposed_date(kind, value):
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        if kind.startswith('next_') or kind.startswith('this_'):"""
    new_pd = """    def proposed_date(kind, value):
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        if kind == 'today':
            return today
        if kind == 'tomorrow':
            return today + datetime.timedelta(days=1)
        if kind.startswith('next_') or kind.startswith('this_'):"""
    if code.count(old_pd) != 1:
        raise ValueError("proposed_date hook precondition failed")
    code = code.replace(old_pd, new_pd, 1)

    # (b) terms: vague must not be overridden by raw_date
    old_terms = """        has_amount = raw_amount not in ['', None]
        has_date = raw_date not in ['', None] or kind.startswith('next_') or kind.startswith('this_')
        vague = kind == 'vague'"""
    new_terms = """        has_amount = raw_amount not in ['', None]
        vague = kind == 'vague'
        has_date = (raw_date not in ['', None] or kind in ['today', 'tomorrow'] or kind.startswith('next_') or kind.startswith('this_')) and not vague"""
    if code.count(old_terms) != 1:
        raise ValueError("terms date hook precondition failed")
    code = code.replace(old_terms, new_terms, 1)

    # (c) callback state: resolve relative and vague dates using runtime anchor
    old_cb = """            elif event == 'offer':
                try:
                    day = iso_date(vars.get('callback_date'))
                    time = str(vars.get('callback_time') or '')
                    if re.fullmatch(r'([01]\\d|2[0-3]):[0-5]\\d', time) is None:
                        raise ValueError('Unreadable time')
                    hour, minute = [int(x) for x in time.split(':')]
                    chosen = now.replace(year=day.year, month=day.month, day=day.day, hour=hour, minute=minute, second=0, microsecond=0)
                except Exception:
                    clarify()
                    return
                next_day = next_business(today + datetime.timedelta(days=1))
                valid = day in [today, next_day] and '10:00' <= time <= '19:00' and chosen > now"""

    new_cb = """            elif event == 'offer':
                try:
                    cb_kind = str(vars.get('date_kind') or '')
                    if cb_kind == 'today':
                        day = today
                    elif cb_kind == 'tomorrow':
                        day = today + datetime.timedelta(days=1)
                    elif cb_kind.startswith('next_') or cb_kind.startswith('this_'):
                        day = proposed_date(cb_kind, vars.get('callback_date'))
                    elif cb_kind == 'vague':
                        day = None
                    else:
                        day = iso_date(vars.get('callback_date'))
                    if day is None:
                        raise ValueError('Vague callback date')
                    time = str(vars.get('callback_time') or '')
                    if re.fullmatch(r'([01]\\d|2[0-3]):[0-5]\\d', time) is None:
                        raise ValueError('Unreadable time')
                    hour, minute = [int(x) for x in time.split(':')]
                    chosen = now.replace(year=day.year, month=day.month, day=day.day, hour=hour, minute=minute, second=0, microsecond=0)
                except Exception:
                    vars['callback_invalid'] = count('callback_invalid') + 1
                    if count('callback_invalid') >= 2:
                        finish('not_reached', 'no_callback', 'I cannot schedule a callback at those times.')
                    else:
                        next_day = next_business(today + datetime.timedelta(days=1))
                        ask('callback', 'Please give another time today or on ' + day_text(next_day) + ', from 10:00 to 19:00, later than the current time.')
                    return
                next_day = next_business(today + datetime.timedelta(days=1))
                valid = day in [today, next_day] and '10:00' <= time <= '19:00' and chosen > now"""

    if code.count(old_cb) != 1:
        raise ValueError("callback state hook precondition failed")
    code = code.replace(old_cb, new_cb, 1)

    # (d) api_response: allow bounded retries on transient transport/5xx errors
    old_verify_retry = """        if operation == 'verify':
            if http == 500 and count('api_attempts') < 2:"""
    new_verify_retry = """        if operation == 'verify':
            if (http in (0, 500, 502, 503, 504) or ok is False) and count('api_attempts') < 2:"""
    if code.count(old_verify_retry) != 1:
        raise ValueError("verify retry precondition failed")
    code = code.replace(old_verify_retry, new_verify_retry, 1)

    old_acct_retry = """        if operation == 'account':
            if http == 500 and count('api_attempts') < 2:"""
    new_acct_retry = """        if operation == 'account':
            if (http in (0, 500, 502, 503, 504) or ok is False) and count('api_attempts') < 2:"""
    if code.count(old_acct_retry) != 1:
        raise ValueError("account retry precondition failed")
    code = code.replace(old_acct_retry, new_acct_retry, 1)

    compile(code, "evaluate", "exec")
    code_field["default"] = code
    return fixed
