"""Keep uncertain product questions separate from explicit debt disputes."""

from copy import deepcopy


def repair(workflow: dict) -> dict:
    fixed = deepcopy(workflow)
    nodes = fixed["nodes"]
    field = nodes["evaluate"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
    code = field["default"]
    old = """    elif event == 'dispute' or (event in ['other','about_call'] and '?' in raw and any(word in raw.lower() for word in ['card','account','product','loan','debt']) and any(phrase in raw.lower() for phrase in ['are you sure','dont know',"don't know",'recognize','not familiar','what card','which card'])):
        explicit = re.search(r'\\b(not mine|isnt mine|is not mine|never had|never owned|didnt have|did not have|closed|paid off)\\b', raw.lower())
        if '?' in raw and not explicit:"""
    new = """    elif event in ['dispute','product_uncertainty'] or (event in ['other','about_call'] and any(word in raw.lower() for word in ['card','account','product','loan','debt']) and any(phrase in raw.lower() for phrase in ['are you sure','dont know',"don't know",'dont think',"don't think",'not sure','not familiar','recognize','what card','which card','such a card','card like this','more info','information'])):
        explicit = re.search(r'\\b(not mine|isnt mine|is not mine|never had|never owned|didnt have|did not have|closed|paid off)\\b', raw.lower())
        uncertain = event == 'product_uncertainty' or not raw or '?' in raw or any(phrase in raw.lower() for phrase in ['i think','maybe','perhaps','more info','information'])
        if uncertain and not explicit:"""
    if code.count(old) != 1:
        raise ValueError("Product uncertainty repair precondition failed")
    code = code.replace(old, new, 1)
    compile(code, "evaluate", "exec")
    field["default"] = code
    for item in nodes["discussion"].get("extraction_schema", []):
        if item.get("name") == "input_event":
            if "product_uncertainty" in item.get("enum_values", []):
                raise ValueError("Product uncertainty already installed")
            item["enum_values"].append("product_uncertainty")
            item["extraction_prompt"] += " Classify a question, hedge, or request for facts about whether the returned product belongs to this customer as product_uncertainty. This includes 'I don't think I have a card like this' and requests for more information. Use dispute only for a clear, unhedged assertion that the debt or product is not theirs, was never held, was closed, or was paid off. A product_uncertainty is not agreement to pay."
            break
    else:
        raise ValueError("Discussion event extractor missing")
    return fixed
