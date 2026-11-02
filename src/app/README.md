# Agents app

The screens the DA analysts use, one per AI service, on top of the gold tables and the agents. An
[AppKit](https://databricks.github.io/appkit/) app (TypeScript, React), deployed by the bundle (`resources/app.yml`).

| Screen | AI service | What it does | Code |
|---|---|---|---|
| Overview, DA review | Bill Reconciler, Payment Validator | Each final DA line by line against the quote and its invoice page (the PDF opens on that page), bank details against the platform; accept, dispute or hold | [`review.tsx`](client/src/pages/review.tsx) |
| Open quotes | Quote Negotiator | Open PDA quotes against the benchmark; an agent drafts the negotiation email | [`negotiator.tsx`](client/src/pages/negotiator.tsx), [agent](server/agents/quote-negotiator/agent.ts) |
| Port calls | Timeline Summarizer | The statement of facts timeline, and a written account on demand | [`portcalls.tsx`](client/src/pages/portcalls.tsx), [agent](server/agents/timeline-summarizer/agent.ts) |
| Port Assistant | Port Assistant | Questions in plain language, with the user's conversations on the side | [`assistant.tsx`](client/src/pages/assistant.tsx), [agent](server/agents/port-assistant/agent.ts) |

**AppKit plugins** ([`server/server.ts`](server/server.ts)):

| Plugin | Used for |
|---|---|
| `agents` | The three agents (`server/agents/<id>/agent.ts`), chat over `/api/agents/chat`, traces to MLflow |
| `analytics` | The screens' queries, [`config/queries/*.obo.sql`](config/queries), and the two confirmed writes |
| `files` | The PDFs of the documents volume |
| `genie` | The three Genie agents (`resources/agents.genie.yml`), asked by the Port Assistant |
| `lakebase` | The chat history (Lakebase project `portcall-agents`, `resources/lakebase.yml`) |

**Runs as the signed-in user.** Every query, model call, Genie question and PDF read uses the user's token
(on-behalf-of-user auth, `user_api_scopes`), so Unity Catalog decides what each person sees. The app's service
principal only reads the app prompts, writes the traces and keeps the chat history.

**The agents:**

- **Port Assistant** is a tool-calling agent. Its tools are the three Genie agents and two UC functions
  (`src/agents/tools`): document search and the port call timeline. It can call several for one question.
- **Quote Negotiator** reads the quote (`get_quote`), what the port charged before (`get_price_history`) and past
  competing quotes (`get_competing_quotes`), then calls `submit_draft`. The benchmark math stays in SQL. Every amount
  in the draft is checked against the data; any that is not found is shown to the analyst before saving.
- **Timeline Summarizer** writes the account from the structured events, citing the page of each one.

**Chat history in Lakebase.** Port Assistant conversations are kept in the `chat` schema of the Lakebase database
([`threads.ts`](server/lib/threads.ts), the agents plugin's thread store): a follow-up continues the thread, and each
user sees only their own. The Quote Negotiator and the Timeline Summarizer are one-shot and keep nothing.

**Traces in Unity Catalog.** Every agent turn (model calls, tool calls, Genie questions) is traced to the
`portcall-agent-traces` experiment, stored as Delta tables in the app schema (`experiment_*_otel_spans` and the
views next to it), so traces are queried with SQL like any other table.

**Nothing is written without a confirm.** Decisions go to `analyst_decisions`, saved drafts to `negotiation_drafts`
(app schema), as the analyst; nothing is sent to the port agent.

**Prompts change without a deploy.** `port_assistant`, `negotiator` and `port_call_story` are in the prompt registry
(app schema, alias `production`); the app reads them every 5 minutes. [`config/prompts.json`](config/prompts.json)
only seeds the first version. The model is `agent_llm_endpoint`.

**Run it locally** against a deployed bundle (uses your CLI profile instead of the user token):

```bash
cd src/app
cp .env.example .env          # fill in the ids from `databricks bundle summary`
npm install
npm run dev                   # http://localhost:8000
```

After changing a query in `config/queries`, run `npm run typegen:queries` to refresh the typed results in
`shared/appkit-types`. `npm run typecheck`, `npm run lint` and `npm run build` are the checks before a deploy.

**Test the deployed app:** `python tests/app_e2e.py --profile <profile> --catalog <catalog>` checks every screen
against gold, the three agents and the Port Assistant routing, the chat history, the traces, the confirmed writes
(removed again) and input validation.
