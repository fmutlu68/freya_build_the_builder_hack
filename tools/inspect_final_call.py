"""Show only user/assistant turns from a Freya call, with identifiers redacted."""
import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import freya


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("call_id")
    args = parser.parse_args()
    call = freya.get_call(args.call_id)
    print("status:", call.get("status"), "ended:", call.get("endedReason"))
    for message in call.get("messages", []):
        if message.get("role") not in {"assistant", "user"}:
            continue
        value = str(message.get("message", ""))
        value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", "[email]", value)
        value = re.sub(r"\b\d{8,}\b", "[number]", value)
        print(message["role"] + ":", value)


if __name__ == "__main__":
    main()
