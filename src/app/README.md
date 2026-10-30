# Agents app

The screens the DA analysts use, one per AI service, on top of the gold tables and the agents. A Databricks App
(FastAPI and one static page, no build step), deployed by the bundle (`resources/app.yml`).

| Screen | AI service | What it does | Code |
|---|---|---|---|
| DA review | SOF Port Bill Analysis, PDA/FDA Validator | Each final DA line by line against the quote and its invoice page (the PDF opens on that page), bank details against the platform; accept, dispute or hold | [`main.py`](main.py) |
| Open quotes | AI Negotiator | Open PDA quotes against the benchmark; an agent drafts the negotiation email | [`backend/negotiator.py`](backend/negotiator.py) |
| Port calls | DA Event Summarizer | The statement of facts timeline, and a written account on demand | [`backend/story.py`](backend/story.py) |
| Ask HAL-9000 | HAL-9000 | Questions in plain language, answered by the supervisor agent | [`backend/hal.py`](backend/hal.py) |

**Runs as the signed-in user.** Every query, model call, Genie question and PDF read uses the user's token
(on-behalf-of-user auth, `user_api_scopes`), so Unity Catalog decides what each person sees. The app's service
principal only reads the app prompts.

**Beyond a Genie agent:**

- **AI Negotiator** is a tool-calling agent: it reads the quote (`get_quote`), what the port charged before
  (`get_price_history`) and past competing quotes (`get_competing_quotes`), then calls `submit_draft`. The benchmark
  math stays in SQL. Every amount in the draft is checked against the numbers the tools returned; any that is not
  found is shown to the analyst before saving.
- **DA Event Summarizer** writes the account from the structured events, citing the page of each one; it is not
  stored.
- **HAL-9000** is an Agent Bricks supervisor agent (created by the setup job, `src/deploy/apply_agents.py`) over
  the three Genie agents (`resources/agents.genie.yml`) and two UC functions (`src/agents/tools`): document search
  and the port call timeline.

**Nothing is written without a confirm.** Decisions go to `analyst_decisions`, saved drafts to `negotiation_drafts`
(app schema); nothing is sent to the agent.

**Prompts change without a deploy.** `negotiator` and `port_call_story` are in the prompt registry (app schema,
alias `production`, experiment `portcall-agent-prompts`); [`prompts.py`](prompts.py) only seeds version 1. The
model is `agent_llm_endpoint` unless a prompt version has a `model` tag.

**Run it locally** against a workspace (uses your CLI profile instead of the user token):

```bash
cd src/app
CATALOG=<catalog> GOLD_SCHEMA=portcall_gold SILVER_SCHEMA=portcall_silver APP_SCHEMA=portcall_app \
DATABRICKS_WAREHOUSE_ID=<id> DATABRICKS_CONFIG_PROFILE=<profile> uvicorn main:app --port 8765
```

**Test the deployed app:** `python tests/app_e2e.py --profile <profile> --catalog <catalog>` checks every screen
against gold, both agents, the HAL-9000 routing, the confirmed writes (removed again) and input validation.
