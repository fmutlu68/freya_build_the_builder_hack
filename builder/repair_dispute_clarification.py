"""Guarded repair for ambiguous product questions in the Brief A candidate."""

from copy import deepcopy


def repair(workflow: dict) -> dict:
    fixed = deepcopy(workflow)
    if fixed.get("initial_node") != "initialize":
        raise ValueError("Unexpected workflow")
    node = fixed["nodes"]["evaluate"]
    code_field = node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
    code = code_field["default"]
    old = """    elif event == 'dispute':
        finish('no_promise','dispute','I understand that you dispute this debt.')"""
    new = """    elif stage == 'product_clarification':
        reply = re.sub(r'[^a-z0-9 ]', '', raw.lower()).strip()
        if reply in ['no', 'no i do not dispute it', 'no i dont dispute it', 'i recognize it']:
            speak('negotiate', 'Thank them for clarifying. Restate only the recorded product ' + str(vars.get('product_label')) + ' and past-due amount ' + str(vars.get('full_amount')) + '. Ask whether they can pay the full amount today.')
        else:
            finish('no_promise','dispute','I understand you may not recognize this account. I can only see the bank record available for this call and cannot establish the account history here. I will not ask for a payment promise. Please contact Freya Bank through an official channel to review it.')
    elif event == 'dispute' or (event in ['other','about_call'] and '?' in raw and any(word in raw.lower() for word in ['card','account','product','loan','debt']) and any(phrase in raw.lower() for phrase in ['are you sure','dont know',"don't know",'recognize','not familiar','what card','which card'])):
        explicit = re.search(r'\\b(not mine|isnt mine|is not mine|never had|never owned|didnt have|did not have|closed|paid off)\\b', raw.lower())
        if '?' in raw and not explicit:
            speak('product_clarification', 'Acknowledge their uncertainty. State only the bank record returned by the account tool: ' + str(vars.get('product_label')) + ', past-due amount ' + str(vars.get('full_amount')) + '. Say you cannot determine from this call why they do not recognize it. Ask exactly: Do you dispute that this account is yours? Do not request payment now.')
        else:
            finish('no_promise','dispute','I understand you dispute this account. I can only see the bank record available for this call and cannot establish the account history here. I will not ask for a payment promise. Please contact Freya Bank through an official channel to review it.')"""
    if code.count(old) != 1:
        raise ValueError("Dispute repair precondition failed; generated code changed")
    code = code.replace(old, new, 1)
    compile(code, "evaluate", "exec")
    code_field["default"] = code
    for field in fixed["nodes"]["discussion"].get("extraction_schema", []):
        if field.get("name") == "input_event":
            field["extraction_prompt"] = field.get("extraction_prompt", "") + " Classify dispute only for a clear claim that the debt/product is not theirs or was closed/paid off. A question about whether a product exists, without a clear denial, is uncertainty; classify as other."
            break
    else:
        raise ValueError("Discussion event extractor missing")
    return fixed
