"""Fetch Freya call records for failed rows of a run_cases result and save masked copies.

Usage: python3 tools/dump_failed_calls.py RESULT.json OUTDIR [--all]
customer_id values and auth-like strings are masked before writing.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import freya  # noqa: E402


def mask(text, ids):
    for cid in ids:
        text = text.replace(cid, "[CUSTOMER_ID]")
    text = re.sub(r"\bc_[0-9a-f]{8}-[0-9a-f]{3,}\b", "[CUSTOMER_ID]", text)
    text = re.sub(r"(?i)Bearer\s+[^\s\"\\]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bfak_[A-Za-z0-9_-]+", "[REDACTED]", text)
    return text


def main():
    result, out = Path(sys.argv[1]), Path(sys.argv[2])
    include_all = "--all" in sys.argv
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads(result.read_text())
    rows = []
    for item in data.get("all_rows") or data.get("rows") or []:
        rows.extend(item if isinstance(item, list) else [item])
    ids = [r["customer_id"] for r in rows if r.get("customer_id")]
    for row in rows:
        if row.get("pass") and not include_all:
            continue
        call = freya.get_call(row["call_id"])
        path = out / f"{row['id']}-{row['call_id'][:8]}.json"
        path.write_text(mask(json.dumps({"row": row, "call": call}, indent=1, default=str), ids))
        print(row["id"], "->", path)


if __name__ == "__main__":
    main()
