"""Conservative static checks; not a policy judge or a full OpenAPI implementation."""
import ast
import json
import re


def resolve(spec, value, seen=()):
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = value["$ref"]
        if not ref.startswith("#/") or ref in seen:
            raise ValueError(f"Unsupported external/cyclic reference: {ref}")
        target = spec
        for part in ref[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return resolve(spec, {**target, **{k: v for k, v in value.items() if k != "$ref"}}, seen + (ref,))
    return value


def operations(spec):
    out = {}
    for path, item in spec.get("paths", {}).items():
        item = resolve(spec, item)
        for method in ("get", "post", "put", "patch", "delete"):
            if method not in item:
                continue
            op = item[method]
            servers = op.get("servers", item.get("servers", spec.get("servers", [])))
            if not servers:
                raise ValueError("OpenAPI must supply an explicit server URL")
            body = resolve(spec, op.get("requestBody", {}))
            schema = body.get("content", {}).get("application/json", {}).get("schema", {})
            if op.get("parameters") or item.get("parameters"):
                raise ValueError(f"v1 supports JSON-body operations, not path/query parameters: {path}")
            for server in servers:
                if "{" in server["url"] or "{" in path:
                    raise ValueError(f"v1 requires concrete OpenAPI URLs: {path}")
                out[(server["url"].rstrip("/") + path, method.upper())] = resolve(spec, schema)
    if not out:
        raise ValueError("No supported OpenAPI operations")
    return out


def validate(workflow, spec):
    errors = []
    def fail(path, message):
        errors.append(f"{path}: {message}")
    try:
        ops = operations(spec)
    except (ValueError, KeyError, TypeError) as exc:
        return [f"OpenAPI: {exc}"]
    if not isinstance(workflow, dict):
        return ["workflow must be an object"]
    nodes = workflow.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        return ["nodes must be a nonempty object"]
    globals_ = workflow.get("global_nodes", {})
    if not isinstance(globals_, dict):
        return ["global_nodes must be an object"]
    names = set(nodes) | set(globals_)
    if workflow.get("initial_node") not in nodes:
        fail("initial_node", "must reference a regular node")
    if "agent_config" in workflow:
        fail("agent_config", "omit; fixed phone model is platform-owned")
    if workflow.get("test_variables"):
        fail("test_variables", "omit static customer/test data; use runtime variables")

    def snippet(code, path):
        if not isinstance(code, str):
            fail(path, "Python code must be a string"); return
        if re.search(r"\{\{\s*[A-Za-z_][A-Za-z0-9_.]*\s*\}\}", code):
            fail(path, "avoid template braces in Python; read vars instead")
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    if any(m.split('.')[0] not in {"json", "re", "datetime", "math"} for m in mods):
                        fail(path, "unsupported/network-capable import in phone code")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "exec", "eval", "__import__"}:
                    fail(path, "dynamic execution/file access not supported in phone code")
        except SyntaxError as exc:
            fail(path, f"invalid Python: {exc.msg}, line {exc.lineno}")

    def body_check(actual, expected, path):
        expected = resolve(spec, expected)
        if any(k in expected for k in ("oneOf", "anyOf", "allOf")):
            fail(path, "v1 validator does not support composed request schemas"); return
        if not isinstance(actual, dict):
            fail(path, "field must be a JSON schema object"); return
        typ = expected.get("type", "object" if "properties" in expected else None)
        if typ and actual.get("type") != typ:
            fail(path, f"type must be {typ}")
        default = actual.get("default")
        templated = isinstance(default, str) and re.fullmatch(r"\{\{[^{}]+\}\}", default)
        if "enum" in expected:
            declared = actual.get("enum", [])
            if templated or "default" not in actual:
                if not declared or any(x not in expected["enum"] for x in declared):
                    fail(path, "model-filled enum must be a nonempty subset of OpenAPI enum")
            elif default not in expected["enum"]:
                fail(path, "literal default is outside OpenAPI enum")
        if "default" in actual and not templated and typ:
            types = {"string": str, "number": (float, int), "integer": int, "boolean": bool, "object": dict, "array": list}
            if typ in types and (not isinstance(default, types[typ]) or (typ in {"integer", "number"} and isinstance(default, bool))):
                fail(path, "literal default has incompatible type")
        if typ == "object":
            props = actual.get("properties", {})
            ep = expected.get("properties", {})
            if not isinstance(props, dict):
                fail(path, "properties must be an object"); return
            for required in expected.get("required", []):
                if required not in props or required not in actual.get("required", []):
                    fail(path, f"missing required field/declaration: {required}")
            for k, field in props.items():
                if k not in ep:
                    fail(path + "/" + k, "field not declared in OpenAPI")
                else:
                    body_check(field, ep[k], path + "/" + k)
                    if "default" not in field and field.get("type") not in {"object", "array"}:
                        fail(path + "/" + k, "Freya body leaf needs a default/template")
        elif typ == "array":
            body_check(actual.get("items", {}), expected.get("items", {}), path + "/items")

    def tool(t, path):
        if not isinstance(t, dict) or t.get("type") != "function":
            fail(path, "tool must have type=function"); return
        f = t.get("function", {})
        if not f.get("name"):
            fail(path, "function name required")
        p = f.get("parameters", {}).get("properties", {})
        handler = f.get("handler")
        for key in ("pre_process_code", "post_process_code"):
            if t.get(key): snippet(t[key], path + "/" + key)
        if handler == "__function__:api_call":
            key = (p.get("url", {}).get("default"), p.get("method", {}).get("default"))
            if key not in ops:
                fail(path, "URL + method defaults must match a supplied OpenAPI operation")
            else:
                body_check(p.get("body", {}), ops[key], path + "/body")
        elif handler == "__function__:code_exec":
            snippet(p.get("code", {}).get("default"), path + "/code")
        elif handler != "__function__:end_call":
            fail(path, "unsupported handler; only supplied bank API, code_exec and end_call allowed")

    def target(value, path, is_global=False):
        if value not in names and not (is_global and value == "__previous__"):
            fail(path, f"unknown target: {value}")

    def condition(c, path):
        if not isinstance(c, dict):
            fail(path, "condition must be an object"); return
        if "conditions" in c:
            if c.get("logic") not in {"or", "and"} or not isinstance(c["conditions"], list) or not c["conditions"]:
                fail(path, "nonempty condition group with or/and required"); return
            for child in c["conditions"]: condition(child, path)
        else:
            op = c.get("operator")
            if op not in {"always", "matches_intent", "equals", "not_equals", "contains", "greater_than", "less_than", "is_set", "is_not_set"}:
                fail(path, "unknown condition operator")
            if op not in {"always", "matches_intent"} and not c.get("variable"):
                fail(path, "variable required")
            if op in {"equals", "not_equals", "contains", "greater_than", "less_than"} and "operand" not in c:
                fail(path, "operand required")

    try:
        for key, n in {**nodes, **globals_}.items():
            path = "nodes/" + key
            if not isinstance(n, dict):
                fail(path, "node must be an object"); continue
            kind = n.get("node_type")
            if kind not in {"conversation", "code", "api_request", "end_call"}:
                fail(path, "unsupported node_type")
            if n.get("name") != key: fail(path, "node.name must equal its map key")
            if kind == "conversation" and n.get("pre_actions"): fail(path, "conversation pre_actions are silently stripped")
            if kind != "conversation" and n.get("tools"): fail(path, "tools only allowed on conversation nodes")
            if kind == "conversation":
                schema = n.get("extraction_schema", [])
                if len(schema) > 8:
                    fail(path, f"conversation node defines {len(schema)} extraction fields; keep extraction schemas stage-scoped (at most 8 fields per node) to prevent model latency hangup timeouts")
            for i, field in enumerate(n.get("extraction_schema", [])):
                if not isinstance(field, dict):
                    fail(f"{path}/extraction_schema/{i}", "field must be an object")
                    continue
                description = " ".join(str(field.get(k) or "") for k in ("description", "extraction_prompt"))
                if field.get("type") == "string" and re.search(r"(?:return|output|emit|produce)\s+(?:one\s+|a\s+|an\s+)?(?:valid\s+|complete\s+)?(?:json\s+object|object\s+as\s+json)", description, re.I):
                    fail(f"{path}/extraction_schema/{i}", "do not serialize several fields as a JSON object inside one string; define typed extraction fields")
            for field in ("passthrough_default_transition", "max_turn_transition"):
                if n.get(field): target(n[field], path + "/" + field, key in globals_)
            for t in n.get("transitions", []):
                target(t.get("target_node"), path + "/transitions", key in globals_)
                condition(t.get("condition"), path + "/transitions")
            if kind == "end_call":
                if n.get("transitions"): fail(path, "end_call cannot have outgoing transitions")
                tool(n.get("terminal"), path + "/terminal")
            for field in ("tools", "pre_actions"):
                for i, t in enumerate(n.get(field, [])): tool(t, f"{path}/{field}/{i}")
        for i, t in enumerate(workflow.get("tools", [])): tool(t, f"tools/{i}")
    except (TypeError, KeyError, AttributeError, ValueError) as exc:
        fail("structure", f"malformed/unsupported structure: {exc}")
    return errors


if __name__ == "__main__":
    import sys
    problems = validate(json.load(open(sys.argv[1])), json.load(open(sys.argv[2])))
    print(json.dumps({"errors": problems}, indent=2))
    sys.exit(bool(problems))
