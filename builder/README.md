# Codex Freya builder

Run from the kit root, Python 3.10+ and a logged-in `codex` CLI required:

```bash
source env.sh
python3 -m builder.run briefs/brief-a.md --openapi tools/openapi.json \
  --model gpt-6.1-sol --reasoning-effort medium
# Brief B is an A-based replacement specification. Supply A as reference;
# evaluate the resulting B agent against B cases, not as a joint A+B score.
python3 -m builder.run briefs/brief-a.md briefs/brief-b.md --openapi tools/openapi.json \
  --model gpt-6.1-sol --reasoning-effort medium
```

The model ID above was present in the local catalog and successfully smoke-tested
with this account on 2026-10-11. Model and effort are required CLI inputs, passed
explicitly to `codex exec`; no global configuration is edited and no fallback model
is selected. ChatGPT login is reused. Claude SDK and separate model API keys are
not needed. `FREYA_API_KEY` is used only by Python for deployment. The generation
process does not receive it. `FREYA_BANK_TEAM_KEY` is unnecessary for this builder.

Each run creates `runs/build-<UTC>-<suffix>/` containing input copies/hashes,
generation instructions and platform documents, prompts, Codex events/stderr,
candidate JSON, validation results, trace.jsonl, candidate IDs, summary.json and,
on success, `workflow.export.json` fetched from Freya. Event logs and workflow JSON
are separate. Runner source snapshots/hashes are included in new runs. Runs are gitignored; review before sharing. A temporary generation
workspace contains only supplied inputs/instructions/docs. Each attempt is a fresh
Codex execution with previous candidate/errors passed through files; it does not
depend on the development conversation. The Codex tool sandbox is read-only.

Total budget defaults to and cannot exceed 1800 seconds. The generator stops at
the deadline minus the default 180-second deployment/export reserve. At most two
repairs follow the first generation (`--max-repairs`). A process-group timeout
stops the child; the global deadline also covers platform I/O. API validation
precedes create. Every accepted new run creates a new workflow, never replaces
another candidate. An ambiguous create/network timeout is NOT automatically
retried; check trace/candidate IDs and the named workflow before rerunning.

Scope: concrete-server OpenAPI JSON with JSON request bodies and local `$ref`s.
Static validation checks node references, tool placement, Python syntax and
request URL/method/body types/required fields/enums. Composed schemas and path/query
parameters are explicitly unsupported in v1. It cannot prove arbitrary hook
semantics, all runtime templates, policy adherence, or generated calculations.
Platform dry run is also schema validation, not a successful customer call.

`repair_*.py` modules reproduce changes to earlier, specifically shaped Brief A
candidates. The normal `python3 -m builder.run` path does not import or apply
them. They are historical experiments, not a general policy engine; some
published results are flagged in `COMPLIANCE_AUDIT.md` as brief-incompatible.

No public tests run automatically. Hidden briefs have no practice cases/answer
key; the practice bank accepts only PUB-01..PUB-13, not custom customer sessions.
Use the official public runner separately for development when appropriate.
Missing credentials or network failures preserve artifacts and mark failure;
`tests: not_run` never becomes PASS. Export success means generated/deployed,
not benchmark success. `candidate.json` allows export recovery without recreating.

First measured build: `runs/build-20261010T211124Z-859ec3`, Brief A + supplied
OpenAPI, Sol medium, 760.98 seconds, 17 nodes, no repair required. Local validation,
platform dry run, create and full export succeeded. Readback preserved all submitted
fields and phone model experimental-5. No public simulation was run. This first run
predated the runner-source snapshot addition; its prompts/inputs/docs/events remain
available. Later maintenance added source snapshots and closed subprocess pipes.

Checks: `python3 -m unittest discover -s tests -p 'test_builder.py'`.
CLI/repair reference: https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex
