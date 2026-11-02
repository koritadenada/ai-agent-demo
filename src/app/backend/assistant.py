"""Port Assistant: a custom tool-calling agent that answers questions in plain language.

It runs in the app as the signed-in user, so every tool answers with the user's own permissions:
  ask_port_costs, ask_da_audit, ask_da_operations   the three Genie agents (Genie Conversation API)
  search_documents, port_call_timeline              UC functions on the documents (plain SQL)
The model picks the tools, may call several, and answers only from what they return. Its prompt comes from the
prompt registry (port_assistant); each run is traced to the MLflow experiment when one is configured. It never
writes: decisions and drafts happen on their own screens, after a confirm."""
import json
import os

from . import llm
from .workspace import GOLD, Session

try:  # tracing is optional: without it the agent works the same
    import mlflow

    if os.environ.get("MLFLOW_EXPERIMENT_ID"):
        mlflow.set_tracking_uri("databricks")
        mlflow.set_experiment(experiment_id=os.environ["MLFLOW_EXPERIMENT_ID"])
    trace = mlflow.trace
except Exception:  # noqa: BLE001
    def trace(fn=None, **_):
        return fn if fn else (lambda f: f)

GENIE = {  # tool name -> (Genie space id from the app resources, label shown to the user, what it answers)
    "ask_port_costs": (os.environ.get("PORT_COSTS_SPACE_ID"), "Port costs and benchmarks",
                       "Port call costs, final vs quote, benchmarks, potential savings, competing quotes, open quotes flagged above the benchmark"),
    "ask_da_audit": (os.environ.get("DA_AUDIT_SPACE_ID"), "DA audit",
                     "Final DA lines vs quote and invoice page, verdicts, the analyst's own checks, over-invoicing, bank detail checks, payments on hold, document reading quality"),
    "ask_da_operations": (os.environ.get("DA_OPERATIONS_SPACE_ID"), "DA operations",
                          "Appointments, cancellations, time from appointment to PDA, sailing to FDA and FDA to approval, statement of facts events"),
}
LABELS = {**{k: v[1] for k, v in GENIE.items()}, "search_documents": "Document search", "port_call_timeline": "Port call timeline"}

TOOLS = [
    *[{"type": "function", "function": {
        "name": name, "description": f"Ask the {label} Genie agent: {about}. Ask one precise question in plain language.",
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}}
      for name, (_, label, about) in GENIE.items()],
    {"type": "function", "function": {
        "name": "search_documents",
        "description": "Keyword search over the text of every port call PDF (PDA quotes, final DA packs, statements of facts). Returns pages with port call, document type, page number and a snippet.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string", "description": "Words to look for, for example: pilotage invoice"},
            "port_call": {"type": "integer", "description": "Only this port call id, when the question names one"}}}}},
    {"type": "function", "function": {
        "name": "port_call_timeline",
        "description": "The ordered events of one port call from its statement of facts, with the page of each event.",
        "parameters": {"type": "object", "properties": {"port_call": {"type": "integer"}}, "required": ["port_call"]}}},
]


def ask_genie(s: Session, space_id: str, question: str) -> dict:
    """One Genie question; returns its text, the SQL it ran and the first rows of the result."""
    m = s.w.genie.start_conversation_and_wait(space_id, question)
    out = {"status": m.status.value if m.status else None}
    for att in m.attachments or []:
        if att.text and att.text.content:
            out["text"] = att.text.content
        if att.query:
            out["sql"] = att.query.query
            r = s.w.genie.get_message_attachment_query_result(space_id, m.conversation_id, m.id, att.attachment_id)
            sr = r.statement_response
            out["columns"] = [c.name for c in sr.manifest.schema.columns]
            out["rows"] = ((sr.result.data_array if sr.result else None) or [])[:30]
            out["row_count"] = sr.manifest.total_row_count
    if m.error:
        out["error"] = str(m.error)
    return out


@trace(span_type="TOOL")
def run_tool(s: Session, name: str, args: dict):
    if name in GENIE:
        return ask_genie(s, GENIE[name][0], args["question"])
    if name == "search_documents":
        return s.sql(f"SELECT * FROM {GOLD}.search_documents(:q, CAST(:pc AS BIGINT))",
                     q=args["query"], pc=args.get("port_call"))
    if name == "port_call_timeline":
        return s.sql(f"SELECT * FROM {GOLD}.port_call_timeline(:pc)", pc=int(args["port_call"]))
    return {"error": f"unknown tool {name}"}


@trace(span_type="AGENT")
def ask(s: Session, history: list[dict]) -> dict:
    p = llm.prompt("port_assistant")
    messages = [{"role": "system", "content": p.template},
                *[{"role": m["role"], "content": m["content"]} for m in history]]
    used = []
    for _ in range(8):
        msg = llm.chat(s.w, p.model, messages, TOOLS)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"answer": llm.text(msg), "agents": used, "prompt_version": p.version}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            name, args = c["function"]["name"], json.loads(c["function"].get("arguments") or "{}")
            if LABELS.get(name) and LABELS[name] not in used:
                used.append(LABELS[name])
            try:
                out = run_tool(s, name, args)
            except Exception as e:  # a failing tool is reported to the model, which can try another
                out = {"error": str(e).split(". Config:")[0]}
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out, default=str)[:20000]})
    return {"answer": "I could not finish this answer; please ask a narrower question.", "agents": used,
            "prompt_version": p.version}
