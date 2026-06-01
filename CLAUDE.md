# Decision HQ — CLAUDE.md

## Project Overview

Multi-agent AI council system. A user submits a decision or dilemma; 8 AI personas debate it across multiple rounds; The Chair synthesizes a final JSON report.

## Architecture

- `personas.py` — All system prompts. One constant per agent, named `{AGENT_NAME_UPPER}_PROMPT`. The Chair uses `CHAIR_SYSTEM_PROMPT`.
- `orchestrator.py` — Pipeline logic: ego-check → debate loop → final synthesis. All LLM calls are async.
- `llm_client.py` — Azure OpenAI wrapper. `LLMClientFactory.create_client()` is the only entry point.
- `config.yaml` — Agent registry. Adding a new agent requires an entry here AND a matching prompt constant in `personas.py`.

## Adding a New Council Member

1. Add a `NEWNAME_PROMPT` constant to `personas.py`
2. Add the agent under `agents:` in `config.yaml`
3. Update the chair's Socratic JSON schema in `orchestrator.py` (around line 99) to include the new agent key
4. Update the final synthesis JSON schema (around line 133) to include the new agent in `member_arguments`

The orchestrator auto-discovers agents from `config.yaml` and loads their prompts via `getattr(personas, f"{agent_name.upper()}_PROMPT")` — so the naming convention must be exact.

## Agent Temperatures (Rationale)

| Agent | Temp | Reason |
|-------|------|--------|
| moderator (Chair) | 0.1 | Deterministic, structured JSON output |
| legal_ethics_guard | 0.3 | Precision over creativity |
| grit_craft | 0.5 | Balanced, methodical |
| the_executioner | 0.5 | Pragmatic, grounded |
| wealth_alchemist | 0.7 | Opportunistic reasoning |
| macro_predictor | 0.7 | Pattern synthesis |
| the_cynic | 0.6 | Controlled pessimism |
| human_factor | 0.6 | Empathetic nuance |
| the_hacker | 0.8 | Creative, lateral thinking |

## Pipeline Stages

1. **Ego-Check** — Chair analyzes user's hidden biases and sends a secret directive to all agents
2. **Debate Loop** — All agents respond in parallel each round; Chair issues per-agent Socratic challenges between rounds
3. **Final Synthesis** — Chair produces the structured JSON report

The Chair uses `json_mode=True` in rounds 2+ and the final synthesis. Agents never use JSON mode — they return free text.

## Environment

Requires a `.env` file with:
```
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_VERSION=
```

## Key Conventions

- Never use `sync` OpenAI calls — everything goes through `async/await` and `asyncio.gather()`
- Agent histories are stored per-agent and isolated — agents never see each other's Socratic questions
- The Chair's inter-round challenges are delivered via each agent's `history` list, not broadcast
