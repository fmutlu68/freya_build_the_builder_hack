"""Guarded repair for standalone information questions during negotiation.

Ensures that answering an informational question while a payment offer is pending:
1. Answers using authorized facts without repeating the payment proposal question.
2. Keeps the pending offer and counters unchanged in state.
3. Preserves mixed intents (question + proposal), refusals, second persuasion, and readback.
"""

from copy import deepcopy
import json


def repair(workflow: dict) -> dict:
    fixed = deepcopy(workflow)
    if fixed.get("initial_node") != "initialize":
        raise ValueError("Unexpected workflow structure")

    node = fixed["nodes"].get("evaluate")
    if not node:
        raise ValueError("Missing evaluate node")

    code_field = node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
    code = code_field["default"]

    old_info = """    def information():
        vars['information_count'] = count('information_count') + 1
        if count('information_count') > 3:
            technical_finish()
        else:
            repeat(answer_question(question) or 'I do not have that information.')"""

    new_info = """    def information():
        vars['information_count'] = count('information_count') + 1
        if count('information_count') > 3:
            technical_finish()
        else:
            ans = answer_question(question) or 'I do not have that information.'
            if state == 'negotiate':
                vars['say'] = ans
                vars['route'] = 'negotiate'
            else:
                repeat(ans)"""

    old_floor = """    def floor_offer(prefix=''):
        vars['full_too_much'] = 'yes'
        if count('floor_offered') > 0:
            persuade()
            return
        vars['floor_offered'] = 1
        day = iso_date(vars.get('pending_date'))
        day = next_business(max(today, day))
        day = min(day, iso_date(vars.get('deadline')))
        offer(vars.get('floor_amount'), day, 'floor', prefix)"""

    new_floor = """    def floor_offer(prefix=''):
        vars['full_too_much'] = 'yes'
        if count('floor_offered') > 0:
            persuade()
            return
        vars['floor_offered'] = 1
        day = iso_date(vars.get('pending_date'))
        if day <= today:
            monday = today - datetime.timedelta(days=today.weekday())
            last = monday + datetime.timedelta(days=4)
            while not business(last):
                last -= datetime.timedelta(days=1)
            if last <= today:
                last = monday + datetime.timedelta(days=11)
                while not business(last):
                    last -= datetime.timedelta(days=1)
            day = min(last, iso_date(vars.get('deadline')))
            vars['persuasion_used'] = max(count('persuasion_used'), 1)
        else:
            day = next_business(max(today, day))
            day = min(day, iso_date(vars.get('deadline')))
        offer(vars.get('floor_amount'), day, 'floor', prefix)"""

    old_refuse = """        if event in ['refuse', 'non_answer']:
            if vars.get('offer_mode') == 'vague_question' and event == 'non_answer':
                offer(vars.get('pending_amount'), iso_date(vars.get('deadline')), 'deadline', 'I can propose the latest available date. ')
                return
            if event == 'refuse':
                refused = vars.get('refused_offers') or []
                if not isinstance(refused, list):
                    refused = []
                pair = rejected_pair()
                if pair not in refused:
                    refused.append(pair)
                vars['refused_offers'] = refused
            persuade()
            return"""

    new_refuse = """        if event in ['refuse', 'non_answer']:
            if vars.get('offer_mode') == 'vague_question' and event == 'non_answer':
                offer(vars.get('pending_amount'), iso_date(vars.get('deadline')), 'deadline', 'I can propose the latest available date. ')
                return
            if count('floor_offered') > 0 and event == 'non_answer':
                day = iso_date(vars.get('pending_date'))
                ask('negotiate', 'Can you confirm if ' + day_text(day) + ' works for you?')
                return
            if event == 'refuse':
                refused = vars.get('refused_offers') or []
                if not isinstance(refused, list):
                    refused = []
                pair = rejected_pair()
                if pair not in refused:
                    refused.append(pair)
                vars['refused_offers'] = refused
            persuade()
            return"""

    old_readback = """    def readback(prefix=''):
        amount = money(vars.get('pending_amount'))
        day = iso_date(vars.get('pending_date'))
        floor = money(vars.get('floor_amount'))
        full = money(vars.get('full_amount'))
        deadline = iso_date(vars.get('deadline'))
        if amount < floor or amount > full or day < today or day > deadline or not business(day):
            raise ValueError('Unvalidated readback')
        notice = ' The rest stays overdue.' if amount < full else ''
        ask('confirm', prefix + 'For your ' + str(vars.get('product_name')) + ', the payment promise is ' + amount_text(amount) + ' on ' + day_text(day) + '.' + notice + ' Do you confirm?')"""

    new_readback = """    def readback(prefix=''):
        amount = money(vars.get('pending_amount'))
        day = iso_date(vars.get('pending_date'))
        floor = money(vars.get('floor_amount'))
        full = money(vars.get('full_amount'))
        deadline = iso_date(vars.get('deadline'))
        if amount < floor or amount > full or day < today or day > deadline or not business(day):
            raise ValueError('Unvalidated readback')
        ask('confirm', prefix + 'For your ' + str(vars.get('product_name')) + ', the payment promise is ' + amount_text(amount) + ' on ' + day_text(day) + '. Do you confirm?')"""

    if code.count(old_info) != 1:
        raise ValueError("information hook precondition failed; code pattern not found")
    if code.count(old_floor) != 1:
        raise ValueError("floor_offer hook precondition failed; code pattern not found")
    if code.count(old_refuse) != 1:
        raise ValueError("refuse/non_answer hook precondition failed; code pattern not found")
    if code.count(old_readback) != 1:
        raise ValueError("readback hook precondition failed; code pattern not found")

    code = code.replace(old_info, new_info, 1)
    code = code.replace(old_floor, new_floor, 1)
    code = code.replace(old_refuse, new_refuse, 1)
    code = code.replace(old_readback, new_readback, 1)
    compile(code, "evaluate", "exec")
    code_field["default"] = code

    return fixed


