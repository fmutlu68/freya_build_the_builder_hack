"""Condensed view of a masked call dump: turns, node changes, tool calls, extracted vars.

Usage: python3 tools/view_call.py DUMP.json [--max N] [--code]
"""
import json
import sys


def short(x, n=300):
    s = x if isinstance(x, str) else json.dumps(x, default=str)
    return s if len(s) <= n else s[:n] + "…"


def main():
    path = sys.argv[1]
    limit = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 10**9
    show_code = "--code" in sys.argv
    call = json.load(open(path))["call"]
    count = 0
    for m in call.get("messages") or []:
        role, text = m.get("role"), m.get("message") or ""
        line = None
        if role in ("user", "assistant", "bot"):
            line = f"{m.get('nodeId','')[:14]:14} {role.upper()[:4]}: {text}"
        elif role == "system":
            try:
                ev = json.loads(text)
            except Exception:
                ev = {"event": "raw", "text": text}
            kind = ev.get("event")
            if kind == "node_enter":
                line = f"   --> node {ev.get('node')}"
            elif kind in ("function_call_start", "function_call_complete"):
                fn = ev.get("function")
                if fn == "code_exec" and not show_code:
                    if kind == "function_call_complete":
                        line = f"   [code] {short(ev.get('result') or ev.get('output'), 220)}"
                else:
                    payload = ev.get("args") if kind.endswith("start") else (ev.get("result") or ev.get("output"))
                    line = f"   [{fn} {kind.split('_')[-1]}] {short(payload, 400)}"
            elif kind in ("variables_extracted", "extraction", "variable_extracted"):
                line = f"   [extract] {short(ev, 300)}"
            elif kind == "route_evaluated":
                line = f"   [route] {short(ev, 200)}"
            else:
                line = f"   [{kind}] {short(ev, 160)}"
        if line:
            print(line)
            count += 1
            if count >= limit:
                break


if __name__ == "__main__":
    main()
