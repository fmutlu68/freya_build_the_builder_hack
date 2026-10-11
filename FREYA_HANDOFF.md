# FREYA × YC — Local Codex handoff

Snapshot: 10 October 2026, approximately 14:47 Europe/Istanbul (UTC+3).
This is a context snapshot, not an official rules document. Read the actual kit and newer organizer announcements before relying on details. Talk to the user in Turkish; code and technical notes may be English.

## Objective and working agreement

Furkan is participating in the Build the Builder hackathon and wants focused help building a competitive, reproducible system. The builder reads customer documents and tool API specifications and produces a complete Freya workflow JSON. Freya runs the resulting customer-facing agent; the builder can run locally and use any allowed model/coding-agent approach.

Two-person team, but the teammate has a Sunday deadline elsewhere and may have limited availability. Plan implementation primarily around Furkan; teammate can help with focused architecture/experiment reviews. Participation has been confirmed; do not reopen eligibility concerns.

Furkan explicitly prefers NEW workflows for successive experiments, rather than repeatedly updating one workflow. Respect this preference and record candidate -> workflow_id -> agent_id -> results. Address capacity if it becomes a real issue.

Keep explanations concrete, progress toward implementation, and avoid restarting strategy discussions or imposing a large framework before measuring a baseline. Do not claim a test passed unless actually run. Keep secrets out of committed files and traces. Do not change the fixed phone-agent model or bypass event restrictions.

## Available source files

The user should place these in the local project:
- The extracted `build-the-builder-v3.zip` kit (folder `build-the-builder`).
- `identity.json`: a single identity conversation node exported by the user, NOT the full agent.
- Kickoff transcript originally uploaded as `Pasted text.txt`; suggested local name `kickoff-transcript.txt`.
- This handoff.

Official page: https://www.freyavoice.ai/hackathon#overview (also #data, #evaluation, #submit, #rules).
Do not assume paths from the previous cloud workspace exist locally.

Kit source map:
- `README.md`, `VERSION`: v3 setup, rules, troubleshooting.
- `briefs/brief-a.md`: 47 rules, single-product collection.
- `briefs/brief-b.md`: additional multi-product rules; read/pass A AND B for B.
- `tools/openapi.json`: bank tool contract.
- `public-test-set.json`: 13 public cases including synthetic identity facts.
- `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md`.
- `freya.py`: API client, workflow creation/update/export, simulation.
- `examples/base-agent.json`: two-node example, identity -> collection.
- `examples/agent_builder.py`: Claude Agent SDK builder.
- `.claude/skills/build-phone-agent/SKILL.md`: starter builder guidance.
- `tools/run_cases.py`, `tools/score.py`: simulation and ledger scoring.
- `env.example`: local credential configuration template.

## Actual progress — do not overstate

The previous assistant read the website (including embedded public cases), README, example builder, its skill, freya.py, relevant workflow/API documentation, identity node, test runner/scorer sections, tool schema, and kickoff transcript. It did NOT comprehensively inspect every page of every technical document or implement a custom builder.

NO live Freya API call, workflow deployment, or simulation was performed by the previous assistant. NO measured baseline or implemented fix exists from that chat. Credentials/model access in the user's local environment are not known. Commands were proposed; the user has not reported executing them yet. Inspect the local working tree before acting in case work has since happened.

## Immediate next task

Get one end-to-end `PUB-01` test running, using the official runner to create the mock customer session. Establish whether an issue is platform/session/tool plumbing or agent behavior before improving the builder.

1. Locate the extracted kit; read local instructions and README. Verify Python >=3.10 and required environment-variable presence without printing secrets. Preserve existing env files.
2. Use `FREYA_API_KEY` and `FREYA_BANK_TEAM_KEY` (a team-chosen stable value of >=16 characters). Do not confuse the bank team key with the Freya workspace API key.
3. Create a NEW uniquely named workflow from `examples/base-agent.json` via `freya.create_workflow(name, workflow)`. Record returned workflow_id and agent_id.
4. Run from kit root:
   `python3 tools/run_cases.py AGENT_ID --only PUB-01 --out results/baseline-pub01.json`
5. If failed, read the call transcript/tool arguments/results and ledger. `freya.get_call(call_id)["messages"]` exposes transcript and tool calls. API docs also describe trace events including `function_call_start`, `function_call_complete`, `route_evaluated`.
6. Once plumbing works, measure the supplied builder on A and A+B. Choose builder provider according to actual local access; do not assume Claude credentials or that a Codex subscription is an API key.

Example creation code (requires configured environment, run in kit root):
```python
import json
from datetime import datetime
import freya
with open("examples/base-agent.json") as f:
    workflow = json.load(f)
name = "baseline-" + datetime.now().strftime("%Y%m%d-%H%M%S")
print(json.dumps(freya.create_workflow(name, workflow), indent=2))
```

## Unresolved identity/date-of-birth issue

User tried the preloaded agent in text chat and could not get past date of birth despite supplying what they believed was correct. No call trace or request/response has been supplied, so root cause is NOT confirmed.

Concrete findings:
- `identity.json` is just a node named `identity`, with verify_identity and end_call tools and a transition to `collection` when `verify_identity_response.data.all_verified` equals true/True.
- Full workflow requires `initial_node` and a `nodes` map, with referenced targets present.
- `verify_identity` requires customer_id, field, answer. `field` is date_of_birth or phone_last4 in the public schema. Date answer must be YYYY-MM-DD; unreadable format returns ok=false without counting as a wrong answer.
- `verified` refers to the individual answer; `all_verified` requires both security questions. A correct DOB alone must NOT be treated as a failure just because all_verified remains false.
- The supplied base agent test_variables contain first_name, last_name, title, now, but NO customer_id.
- `run_cases.py` calls POST `/v1/practice/sessions` with `{"case":"PUB-01"}` through the team-authenticated helper, then passes returned `variables` to the simulation. Those include a valid customer_id for that mock session.
- A direct UI chat might lack this session/customer_id. This is a strong hypothesis, not a verified diagnosis. The correct answers are the synthetic customer's facts, not the user's real DOB.
- PUB-01: Daniel Reyes; date_of_birth 1988-03-14; phone_last4 4471. These are test fixtures, never generic production/builder rules.
- Wrong attempts accumulate within a session; use fresh test sessions when appropriate.
- The uploaded node's null fields are mostly OPTIONAL CONFIGURATION, not missing customer variables. Actual templated variables use `{{customer_id}}`, etc.
- Documentation says to omit null fields, but base-agent.json itself contains nulls. Do not claim nulls caused the DOB failure. Validate actual platform behavior and produce clean payloads as needed.

## Runtime facts from the kit

- Workflow root: initial_node, nodes (OBJECT/map), optional system_prompt, global_nodes, test_variables, context_variables, tools. Export wrapper is different from this raw workflow.
- `freya.export_workflow(workflow_id, path)` writes workflow_id, agent_id, updated_at, and workflow fetched from the platform. Submit the full export, not a node.
- Extraction, routing and dialogue use separate model calls/prompts. Routing does not see task_message. Put transition logic in transitions/routing configuration, not only dialogue prose.
- The dialogue model can call only current-node tools. Deterministic variable conditions do not need a model call.
- Conversation nodes keep tools; code/api_request nodes use pre_actions. Unsupported fields can be stripped silently. Read exact format before generating.
- Code nodes/hooks are allowed and encouraged for deterministic calculations/state. Learn their actual sandbox/API from docs, rather than inventing syntax.
- Updates require publishing; `freya.save_workflow` handles update+publish. User prefers new candidates; keep fresh candidate IDs explicit.
- Omit agent_config in generated payloads per kit guidance. Phone model is fixed by AGENT_LLM in freya.py (v3 defaults experimental-5); do not alter it. Builder model choice is separate.
- One simulation job at a time per workspace; a simulation may contain concurrent calls internally. Do not confuse these limits.
- Ten-case run is documented as 3–11 minutes. --only, --out, --reps, --style are supported by run_cases.py. Styles: pieces, corrects, talkative, asks_back, in_words.
- Agent delays can cause customer hangups. Runner reports slowest-turn statistics; do not attribute every failure to prompts.

## Starter builder already exists

`examples/agent_builder.py` runs Claude Agent SDK with a skill, file/edit/shell tools, trace logging, and long foreground command timeouts. It asks the coding agent to read specs, write workflow, deploy, test and repair. Thus implementing any test/repair loop alone is not a competitive novelty.

README reports the v3 builder passed A's 10 cases in ONE run; that is an organizer claim, not our measurement or evidence of 3-repeat reliability. README separately reports the static two-node base agent passed 2/13 in one run.

The example logs messages to traces/<timestamp>.jsonl. Inspect trace completeness and overall wall-clock budget; max_turns/individual command timeouts are not a 30-minute total run deadline. Hidden tool schema must be an explicit runtime input; starter guidance references tools/openapi.json, so do not accidentally pin all builds to the public API.

## Scoring and rules as documented (subject to new announcements)

- 13 public cases: A has 10, B has 3. Identity/third-party handling, deadlines/holidays, hardship, minimum amounts, already-paid, restructuring, tool failure/retry, multiple products and differing deadlines.
- Seven public bank tools: verify_identity, get_account, create_promise, add_note, schedule_callback, transfer_to_agent, close_call.
- Bank API records invalid business decisions too; it does not enforce all policy. Successful HTTP/tool result is insufficient proof of correct action.
- Case requires correct ledger outcome AND policy adherence AND honesty. No partial credit. Conversation checks are judge-model assessed.
- Written final: two unseen briefs, 30 cases each, three runs per case; case passes only if all three pass. Score = passed cases / 60. Tie-breaks: promised amount on passed cases, shorter build time, earlier submission.
- Hidden docs include one clean spec and one mixed-source bundle (email, policy extract, superseding memo, code list). Tool names reportedly stay the same but fields/enums may change.
- Written builder budget: <=30 minutes per brief INCLUDING tests. Do not confuse with the 3-hour final submission window.
- Phone agent may call only provided bank API; fixed phone model. Builder may use other models. Synthetic data only. Do not probe/load-test platform.
- Written rules prohibit hand-editing final agents and inserting hidden-brief-specific facts into builder code/prompts after release. Runtime automatic extraction of the supplied brief is the intended operation.

## Conflicts to keep visible, not silently resolve

| Topic | Written site/kit | Kickoff transcript |
|---|---|---|
| Final deliverables | Full workflow exports, builder code/commit/run command/traces | Around 38:17: currently a single JSON; details tomorrow |
| Final domain | Collection calls with changed policies | Around 33–36 min: banking OR insurance; avoid collection-specific builder |
| Manual final edits | Disallowed; reproducible automated generation | Around 29–32 min: ambiguous allowance for manual work, then reproducibility/traces emphasized |
| Test quota | No final numerical quota in inspected text | Around 36:30–37 min: platform quota to be announced; local testing unrestricted |
| Times | Hidden Sun Oct 11 17:00 UTC / close 20:00 UTC = 20:00/23:00 Istanbul | Says 5–8, evaluations 8–11, no unambiguous timezone; may change |
| Capacity | Site 10 workflows | V3 README 200 workflows |
| Voice | Written benchmark is text | Kickoff mentions chat first, optional-sounding voice for final; clarify |

Check newer organizer announcements for these. Until clarified, preserve reproducible code/traces, automate generation and do not assume additional test budget or manual tuning rights. Do not send organizer messages without the user's instruction.

## Proposed development strategy, not implemented architecture

First measure baseline. Keep reusable Freya engineering knowledge separate from per-brief business rules. A coding-agent-plus-skills builder is explicitly encouraged; no need to create a large orchestration framework immediately.

Candidate improvements guided by observed failures:
1. Extract source-linked requirements, exceptions and document precedence; verify coverage against original documents so extraction loss is caught.
2. Parse each supplied OpenAPI contract; generate correct fields/enums dynamically.
3. Generate workflow with explicit preconditions, deterministic gates, scoped tools and product-specific state where applicable.
4. Validate structure, references, schemas and generated computation before paid/slow simulations.
5. Test, classify root cause, apply targeted repair, retain best validated candidate and budget time for export.
6. Use repeated public runs and varied speaking styles. Practice-only success is insufficient generalization evidence.
7. Generate local checks/personas if helpful, but a different local model is NOT proof of Freya runtime behavior. Do not invent an unprovided endpoint for custom test sessions.

Possible error classes: missed rule, wrong tool/field, ordering/precondition, lost state, duplicate side effect, false completion claim, latency/budget. Prioritize passing cases over tie-break promised amount.

## Maintaining continuity locally

After the initial inspection, put concise stable project instructions into AGENTS.md (merge with existing content; do not overwrite it). Keep evolving state, exact commands, latest measured results and next action in a separate STATUS.md. This handoff is a dated historical snapshot; new evidence should supersede it explicitly.

First response should briefly state what exists locally, then start the PUB-01 setup/debug task. If credentials are absent, do all useful offline inspection and identify the exact missing environment variables. Avoid another broad strategy-only response.
