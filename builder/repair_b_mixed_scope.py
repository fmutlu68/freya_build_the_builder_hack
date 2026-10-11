"""Guarded Brief B repair for mixed or exclusive product replies.

The existing candidate stores one intent and one target per utterance.  A
mixed reply can therefore be interpreted as a proposal for every product.
This repair makes aggregate proposals require an explicit aggregate scope and
returns ambiguous or mixed replies to Brief B's product-by-product flow.
"""

from copy import deepcopy


SCOPE = {
    "name": "e_scope",
    "type": "string",
    "description": (
        "Scope of the latest payment or refusal statement, not the previous offer. "
        "all: one uniform decision applies to every product; a clear yes to "
        "the pending all-products question is all in that context, even when "
        "the customer does not say the word all. "
        "one: a change concerns one named product and says nothing about the others. "
        "only_one: the customer explicitly says only one named product is agreed, "
        "excluding the other products from that agreement. "
        "mixed: different decisions for products, or a named subset containing "
        "multiple products. unclear: scope cannot be established. "
        "Do not turn a mixed acceptance/refusal into an all-products proposal. "
        "A missing or ambiguous target never establishes all by itself."
    ),
    "enum_values": ["all", "one", "only_one", "mixed", "unclear"],
    "max_retries": 1,
    "min_confidence": 0.75,
}


def repair(workflow: dict) -> dict:
    fixed = deepcopy(workflow)
    nodes = fixed["nodes"]
    if not {"process", "negotiation", "readback"} <= nodes.keys():
        raise ValueError("Unexpected Brief B workflow structure")
    code_field = nodes["process"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
    code = code_field["default"]

    for name in ("negotiation", "readback"):
        schema = nodes[name]["extraction_schema"]
        if any(item["name"] == "e_scope" for item in schema):
            raise ValueError("Product scope extraction already exists")
        schema.append(deepcopy(SCOPE))
        target = next(item for item in schema if item["name"] == "e_target")
        target["description"] += (
            " In a mixed payment/refusal sentence, choose the single product "
            "receiving the volunteered payment proposal if it is explicit; "
            "the refused products do not make that payment target ambiguous. "
            "Use -1 if the payment target itself is uncertain."
        )
    intent = next(item for item in nodes["negotiation"]["extraction_schema"] if item["name"] == "e_intent")
    intent["description"] += (
        " During a named-product question, classify the answer for the active "
        "product only. A simultaneous payment promise for another product "
        "must not override an explicit refusal of the active product. During "
        "scope_clarify, classify the named focus product only; a statement "
        "solely about another product is a non-answer to that question."
    )
    intent = next(item for item in nodes["readback"]["extraction_schema"] if item["name"] == "e_intent")
    intent["description"] += (
        " A clear unqualified affirmative commitment to the entire current "
        "readback is yes even if phrased without the literal word yes. A reply "
        "accepting only one of several read-back products is not yes."
    )
    focused = deepcopy(nodes["negotiation"])
    focused["name"] = "scope_clarify"
    focused["position"] = {"x": 1680, "y": 1100}
    focused["task_message"] = (
        "The fixed entry text asks about exactly one focus product. "
        "Current state: {{pending_context}} Product facts: {{product_context}} "
        "Classify the caller's decision only for that named focus product. "
        "Other products mentioned in the same reply do not change this turn's "
        "decision. Do not speak a new offer or call a tool."
    )
    focused["extraction_schema"] = [
        deepcopy(field) for field in nodes["negotiation"]["extraction_schema"]
        if field["name"] in {"e_intent", "e_date_kind", "e_date", "e_amount", "e_scope"}
    ]
    next(field for field in focused["extraction_schema"] if field["name"] == "e_intent")["description"] += (
        " The focus product named in the current question is the only product "
        "whose payment decision this field represents. A payment for another "
        "product does not establish payment for the focus product."
    )
    nodes["scope_clarify"] = focused
    process_transitions = nodes["process"]["transitions"]
    if any(t.get("target_node") == "scope_clarify" for t in process_transitions):
        raise ValueError("Scope clarification transition already exists")
    process_transitions.insert(
        next(i for i, t in enumerate(process_transitions) if t.get("target_node") == "fault"),
        {
            "target_node": "scope_clarify",
            "description": "Clarify one product after a mixed or uncertain answer",
            "condition": {
                "logic": "or",
                "conditions": [{"variable": "route", "operator": "equals", "operand": "scope_clarify"}],
            },
        },
    )

    old = """routes = dict(opening='opening', dob='identity_dob', phone='identity_phone', callback='callback', all='negotiation', product='negotiation', readback='readback', support='decision'"""
    new = """routes = dict(opening='opening', dob='identity_dob', phone='identity_phone', callback='callback', all='negotiation', product='negotiation', scope_clarify='scope_clarify', readback='readback', support='decision'"""
    code = _replace_once(code, old, new)
    old = """    if s.get('stage') in ['all', 'product', 'readback']:
        vars['product_context'] = ' '.join('Index ' + str(i) + ': ' + p['label'] + '; past due ' + money(p['past_due']) + '; floor ' + money(p['floor']) + '; deadline ' + p['deadline'] + '; status ' + p['status'] + '.' for i, p in enumerate(s['products']))
        vars['pending_context'] = 'Stage ' + s['stage'] + '. ' + ('Active product index ' + str(s['index']) + '.' if s['stage'] == 'product' else 'The current question concerns the products identified in the spoken question.')"""
    new = """    if s.get('stage') in ['all', 'product', 'readback', 'scope_clarify']:
        vars['product_context'] = ' '.join('Index ' + str(i) + ': ' + p['label'] + '; past due ' + money(p['past_due']) + '; floor ' + money(p['floor']) + '; deadline ' + p['deadline'] + '; status ' + p['status'] + '.' for i, p in enumerate(s['products']))
        if s['stage'] == 'scope_clarify':
            vars['pending_context'] = 'Stage scope_clarify. Classify only focus product index ' + str(s.get('scope_focus')) + '. Do not combine decisions about other products.'
        else:
            vars['pending_context'] = 'Stage ' + s['stage'] + '. ' + ('Active product index ' + str(s['index']) + '.' if s['stage'] == 'product' else 'The current question concerns the products identified in the spoken question.')"""
    code = _replace_once(code, old, new)

    old = """    def apply_proposal(indices, kind, value, amount, intent, prefix=''):
        date_state, proposed = resolve_date(kind, value)"""
    new = """    def apply_proposal(indices, kind, value, amount, intent, prefix=''):
        if not indices or any(s['products'][i]['status'] in ['recorded', 'excluded'] for i in indices):
            focus_scope(s['stage'])
            return
        date_state, proposed = resolve_date(kind, value)"""
    code = _replace_once(code, old, new)

    old = """            p['status'] = 'agreed'
        if adjusted:"""
    new = """            p['status'] = 'agreed'
            p['agreement_source'] = 'aggregate' if len(indices) > 1 else 'individual'
        if adjusted:"""
    code = _replace_once(code, old, new)

    old = """                        p['status'] = 'agreed'
                        if stage == 'all' and not s['all_offer']:"""
    new = """                        p['status'] = 'agreed'
                        p['agreement_source'] = 'aggregate' if stage == 'all' else 'individual'
                        if stage == 'all' and not s['all_offer']:"""
    code = _replace_once(code, old, new)

    old = """    def readback():
        agreed = [p for p in s['products'] if p['status'] == 'agreed']"""
    new = """    def focus_scope(origin, preferred=-1):
        eligible = [i for i, p in enumerate(s['products']) if p['status'] in ['open', 'agreed']]
        if not eligible:
            finish()
            return
        focus = preferred if preferred in eligible else eligible[0]
        s['scope_focus'] = focus
        s['scope_origin'] = origin
        p = s['products'][focus]
        say('scope_clarify', 'I heard different decisions for different products. Let us clarify only ' + p['label'] + ' first. Are you proposing a payment date for this product, or declining it?')
    def same_readback_commitment(intent, target, scope, kind, value, amount):
        agreed = [i for i, p in enumerate(s['products']) if p['status'] == 'agreed']
        if len(agreed) != 1 or intent not in ['proposal', 'propose_full'] or scope not in ['all', 'one', 'only_one', 'mixed']:
            return False
        i = agreed[0]
        if target != i and not (target < 0 and scope == 'all'):
            return False
        p = s['products'][i]
        date_state, proposed = resolve_date(kind, value)
        if date_state != 'exact' or proposed is None or proposed.isoformat() != p['date']:
            return False
        if amount is not None and abs(amount - p['amount']) > 0.005:
            return False
        if intent == 'propose_full' and abs(p['amount'] - p['past_due']) > 0.005:
            return False
        return True
    def readback():
        agreed = [p for p in s['products'] if p['status'] == 'agreed']"""
    code = _replace_once(code, old, new)

    old = """        target = integer(vars.get('e_target'), -1)
        if stage in ['all', 'product', 'readback']:"""
    new = """        target = integer(vars.get('e_target'), -1)
        scope = str(vars.get('e_scope') or 'unclear')
        if scope not in ['all', 'one', 'only_one', 'mixed', 'unclear']:
            scope = 'unclear'
        if stage in ['all', 'product', 'readback']:"""
    code = _replace_once(code, old, new)

    old = """        if stage in ['all', 'product', 'readback']:
            if 0 <= target < len(s['products']):
                indices = [target]
            elif stage == 'product':
                indices = [s['index']]
            elif stage == 'readback':
                indices = [i for i, p in enumerate(s['products']) if p['status'] == 'agreed']
            else:
                indices = [i for i, p in enumerate(s['products']) if p['status'] == 'open']
        else:
            indices = []"""
    new = """        if stage == 'product':
            i = s['index']
            indices = [i] if 0 <= i < len(s['products']) and s['products'][i]['status'] in ['open', 'agreed'] else []
        elif stage == 'all':
            if intent in ['yes', 'no', 'refuse', 'non_answer'] or scope == 'all':
                indices = [i for i, p in enumerate(s['products']) if p['status'] == 'open']
            elif 0 <= target < len(s['products']) and s['products'][target]['status'] == 'open':
                indices = [target]
            else:
                indices = []
        elif stage == 'readback':
            if intent == 'yes' or scope == 'all':
                indices = [i for i, p in enumerate(s['products']) if p['status'] == 'agreed']
            elif 0 <= target < len(s['products']) and s['products'][target]['status'] == 'agreed':
                indices = [target]
            else:
                indices = []
        else:
            indices = []"""
    code = _replace_once(code, old, new)

    old = """        elif stage in ['all', 'product', 'readback']:
            if not indices:
                clarify('Please name the product you mean.')"""
    new = """        elif stage == 'scope_clarify':
            focus = integer(s.get('scope_focus'), -1)
            if focus < 0 or focus >= len(s['products']) or s['products'][focus]['status'] in ['recorded', 'excluded']:
                focus_scope(s.get('scope_origin', 'all'))
            elif s.get('scope_origin') == 'readback' and same_readback_commitment(intent, focus, scope, kind, date_value, amount):
                record_next()
            elif intent in ['proposal', 'propose_full', 'hardship_proposal', 'hardship_full'] and (kind != 'none' or amount is not None or intent in ['propose_full', 'hardship_full']):
                if s.get('scope_origin') == 'readback':
                    for i, p in enumerate(s['products']):
                        if i != focus and p['status'] == 'agreed' and (scope in ['only_one', 'mixed'] or p.get('agreement_source') == 'aggregate'):
                            p['status'] = 'open'
                s['index'] = focus
                if s['products'][focus]['status'] == 'agreed':
                    s['products'][focus]['status'] = 'open'
                apply_proposal([focus], kind, date_value, amount, intent)
            elif intent in ['no', 'refuse', 'non_answer']:
                s['index'] = focus
                if s['products'][focus]['status'] == 'agreed':
                    s['products'][focus]['status'] = 'open'
                offer_attempt()
            elif intent == 'yes' and s.get('scope_origin') == 'readback' and len([p for p in s['products'] if p['status'] == 'agreed']) == 1:
                record_next()
            else:
                say('scope_clarify', 'Please answer only about ' + s['products'][focus]['label'] + ': state the payment date you propose for it, or say that you decline this product.')
        elif stage in ['all', 'product', 'readback']:
            # An ambiguous target never becomes consent for all products.
            if stage == 'all' and len(s['products']) > 1 and intent in ['proposal', 'propose_full', 'hardship_proposal', 'hardship_full'] and scope in ['mixed', 'unclear'] and len(indices) == 1 and (kind != 'none' or amount is not None or intent in ['propose_full', 'hardship_full']):
                s['all_offer'] = False
                apply_proposal(indices, kind, date_value, amount, intent)
            elif stage == 'all' and len(s['products']) > 1 and intent in ['proposal', 'propose_full', 'hardship_proposal', 'hardship_full'] and scope in ['mixed', 'unclear']:
                s['all_offer'] = False
                focus_scope('all', target)
            elif stage == 'all' and len(s['products']) > 1 and intent in ['proposal', 'propose_full', 'hardship_proposal', 'hardship_full'] and scope in ['one', 'only_one'] and not indices:
                focus_scope('all')
            elif stage == 'product' and intent in ['proposal', 'propose_full', 'hardship_proposal', 'hardship_full'] and (scope in ['mixed', 'unclear'] and target != s['index']):
                focus_scope('product', s['index'])
            elif stage == 'readback' and same_readback_commitment(intent, target, scope, kind, date_value, amount):
                record_next()
            elif stage == 'readback' and intent in ['proposal', 'propose_full', 'hardship_proposal', 'hardship_full'] and scope == 'only_one' and len(indices) == 1:
                for i, p in enumerate(s['products']):
                    if i != indices[0] and p['status'] == 'agreed':
                        p['status'] = 'open'
                apply_proposal(indices, kind, date_value, amount, intent)
            elif stage == 'readback' and intent in ['proposal', 'propose_full', 'hardship_proposal', 'hardship_full', 'no', 'refuse', 'non_answer'] and scope in ['mixed', 'unclear']:
                focus_scope('readback', target)
            elif stage == 'readback' and intent in ['proposal', 'propose_full', 'hardship_proposal', 'hardship_full'] and not indices:
                focus_scope('readback')
            elif not indices:
                if stage == 'readback':
                    focus_scope('readback')
                else:
                    clarify('Please name the product you mean.')"""
    code = _replace_once(code, old, new)
    old = """    for key in ['e_intent', 'e_answer', 'e_date_kind', 'e_date', 'e_amount', 'e_target', 'e_time']:
        vars.pop(key, None)"""
    new = """    for key in ['e_intent', 'e_answer', 'e_date_kind', 'e_date', 'e_amount', 'e_target', 'e_scope', 'e_time']:
        vars.pop(key, None)"""
    code = _replace_once(code, old, new)
    compile(code, "process", "exec")
    code_field["default"] = code
    return fixed


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("Brief B repair precondition failed")
    return text.replace(old, new, 1)
