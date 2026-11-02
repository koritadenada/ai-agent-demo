"""End-to-end test of the deployed agents app (AppKit), as a signed-in user (CLI OAuth token).

Checks the screens' queries against SQL on gold, the PDFs, the three agents (Port Assistant routing, Quote
Negotiator, Timeline Summarizer), the chat history in Lakebase, the traces in Unity Catalog, the confirmed writes
(removed again afterwards) and input validation. Usage:
  python tests/app_e2e.py --profile <profile> --catalog <catalog> [--app portcall-agents] [--prefix portcall_] [--skip-routing]
"""
import argparse
import json
import subprocess
import sys
import time

import requests
from databricks.sdk import WorkspaceClient

FAILS = []


def check(ok: bool, what: str):
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def sse(response) -> list[dict]:
    events = []
    for line in response.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--app", default="portcall-agents")
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--prefix", default="portcall_")
    ap.add_argument("--skip-routing", action="store_true")
    a = ap.parse_args()
    w = WorkspaceClient(profile=a.profile)
    gold, silver, app = (f"{a.catalog}.{a.prefix}{s}" for s in ("gold", "silver", "app"))
    token = json.loads(subprocess.check_output(["databricks", "auth", "token", "--profile", a.profile]))["access_token"]
    url = w.apps.get(a.app).url
    http = requests.Session()
    http.headers["Authorization"] = f"Bearer {token}"
    wh = next(x.id for x in w.warehouses.list() if x.name == "Serverless Starter Warehouse")

    def sql(q):
        r = w.statement_execution.execute_statement(q, wh, wait_timeout="50s")
        return (r.result.data_array or []) if r.result else []

    def query(key, **params):
        typed = {k: {"__sql_type": "BIGINT" if isinstance(v, int) else "STRING", "value": str(v)} for k, v in params.items()}
        r = http.post(f"{url}/api/analytics/query/{key}", json={"parameters": typed, "format": "JSON_ARRAY"}, stream=True, timeout=180)
        result = next((e for e in sse(r) if e.get("type") == "result"), {})
        return result.get("data", [])

    def chat(agent, message, thread=None):
        body = {"agent": agent, "message": message, **({"threadId": thread} if thread else {})}
        events = sse(http.post(f"{url}/api/agents/chat", json=body, stream=True, timeout=600))
        text = "".join(e.get("delta", "") for e in events if e.get("type") == "response.output_text.delta")
        calls = [e["item"] for e in events if e.get("type") == "response.output_item.added" and e.get("item", {}).get("type") == "function_call"]
        outputs = {e["item"].get("call_id"): e["item"].get("output") for e in events
                   if e.get("type") == "response.output_item.done" and e.get("item", {}).get("type") == "function_call_output"}
        thread_id = next((e["data"]["threadId"] for e in events if e.get("type") == "appkit.metadata" and "threadId" in e.get("data", {})), None)
        failed = next((e.get("error") for e in events if e.get("type") in ("error", "response.failed")), None)
        return text, calls, outputs, thread_id, failed

    def traces():   # agent -> traces in its own experiment (Delta tables in the agent's schema)
        exp = agent_experiments(w, a)
        return {agent: int(sql(f"SELECT COUNT(DISTINCT trace_id) FROM {a.catalog}.{a.prefix}{agent.replace('-', '_')}"
                               f".experiment_{w.get_workspace_id()}_{exp[agent]}_otel_spans")[0][0]) for agent in exp}

    def traced(agent, at_least, wait=120):   # traces are exported shortly after a turn ends
        deadline = time.time() + wait
        while (n := traces()[agent]) < at_least and time.time() < deadline:
            time.sleep(10)
        return n

    me = http.get(f"{url}/api/config", timeout=60).json()
    check(me["user"] == w.current_user.me().user_name, f"runs as the signed-in user ({me['user']})")
    check(all("@production v" in v for v in me["prompts"].values()), f"agent prompts come from the registry {me['prompts']}")

    k = query("overview_kpis", gold=gold, app=app)[0]
    holds = int(sql(f"SELECT COUNT(*) FROM {gold}.payment_validation WHERE hold_payment")[0][0])
    check(int(k["payments_on_hold"]) <= holds, f"overview payments on hold {k['payments_on_hold']} (gold {holds})")
    agree = float(sql(f"SELECT ROUND(AVG(CAST(agrees_with_analyst AS INT)) * 100, 1) FROM {gold}.expense_reconciliation")[0][0])
    check(abs(float(k["agreement_pct"]) - agree) < .01, f"overview agreement {k['agreement_pct']}% = gold")

    fdas = query("fdas", gold=gold, app=app)
    check(len(fdas) == int(sql(f"SELECT COUNT(*) FROM {gold}.port_bill_analysis WHERE analysis_status <> 'NO_DOCUMENTS'")[0][0]),
          f"DA review lists every checked final DA ({len(fdas)})")
    for f in [next(x for x in fdas if x["hold_payment"] == "false"), next(x for x in fdas if x["hold_payment"] == "true")]:
        e = int(f["evaluation_id"])
        lines = query("fda_lines", gold=gold, evaluation_id=e)
        check(len(lines) == int(f["lines_checked"]), f"FDA {e}: {len(lines)} lines = lines checked")
        final = float(sql(f"SELECT ROUND(final_amount, 2) FROM {gold}.port_call_costs WHERE evaluation_id = {e}")[0][0])
        check(abs(sum(float(l["final_amount"]) for l in lines) - final) < .05, f"FDA {e}: lines add up to the final DA {final}")
        raw = query("fda_payment", gold=gold, evaluation_id=e)[0]["field_checks"]
        checks = raw if isinstance(raw, list) else json.loads(raw)
        account = next(c for c in checks if c["name"] == "account")
        check("****" in account["explanation"], f"FDA {e}: account numbers masked")
        if f["hold_payment"] == "true":
            check(account["status"] == "NO_MATCH", f"FDA {e}: the payment on hold shows the account mismatch")
        docs = query("documents", gold=gold, silver=silver, evaluation_id=e, port_call_id=0)
        pack = next(d for d in docs if d["doc_type"] == "final_da_pack")
        r = http.get(f"{url}/api/files/files/raw", params={"path": pack["volume_path"]}, timeout=120)
        check(r.ok and r.content[:5] == b"%PDF-", f"FDA {e}: the final DA pack PDF opens as the user")

    e = int(fdas[0]["evaluation_id"])
    r = http.post(f"{url}/api/fdas/{e}/decision", json={"decision": "approve"}, timeout=60)
    check(r.status_code == 422, "an unknown decision is rejected")
    r = http.post(f"{url}/api/fdas/{e}/decision", json={"decision": "hold", "note": "e2e test"}, timeout=120)
    saved = query("fda_decisions", app=app, evaluation_id=e)
    check(r.ok and saved and saved[0]["note"] == "e2e test", "a confirmed decision is saved and read back")
    sql(f"DELETE FROM {app}.analyst_decisions WHERE note = 'e2e test'")

    start = traces()
    quotes = query("quotes", gold=gold, app=app)
    q = next(x for x in quotes if int(x["flagged_lines"]) > 0)
    p = int(q["proforma_id"])
    text, calls, outputs, _, failed = chat("quote-negotiator", f"Draft the negotiation email for the open PDA quote {p}.")
    submit = next((c for c in calls if c["name"] == "submit_draft"), None)
    check(not failed and calls and calls[0]["name"] == "get_quote", f"Quote Negotiator reads the quote first ({[c['name'] for c in calls]})")
    if submit:
        draft = json.loads(submit["arguments"])
        unverified = json.loads(outputs.get(submit["call_id"]) or "{}").get("unverified_amounts")
        check(unverified == [], f"Quote Negotiator: every amount found in the data ({unverified})")
        flagged = {l["expense_name"] for l in query("quote_lines", gold=gold, proforma_id=p) if l["flagged"] == "true"}
        check({l["expense_name"] for l in draft["lines"]} <= flagged, "Quote Negotiator negotiates only flagged lines")
        check(not any(d in draft["body"] + draft["subject"] for d in ("—", "–")), "Quote Negotiator: no dashes as punctuation")
        r = http.post(f"{url}/api/quotes/{p}/drafts", json={**draft, "subject": "e2e test", "unverified_amounts": []}, timeout=120)
        check(r.ok and query("quote_drafts", app=app, proforma_id=p)[0]["subject"] == "e2e test", "a confirmed draft is saved and read back")
        sql(f"DELETE FROM {app}.negotiation_drafts WHERE subject = 'e2e test'")
    else:
        check(False, f"Quote Negotiator submits a draft ({failed})")

    calls_with_sof = query("port_calls", gold=gold, silver=silver)
    sofs = int(sql(f"SELECT COUNT(DISTINCT proforma_id) FROM {silver}.documents WHERE doc_type = 'statement_of_facts'")[0][0])
    check(len(calls_with_sof) == sofs, f"Port calls lists every call with a statement of facts ({len(calls_with_sof)})")
    pc = int(calls_with_sof[0]["port_call_id"])
    text, calls, _, thread, failed = chat("timeline-summarizer", f"Write the account of port call {pc}.")
    check(not failed and "(p. " in text and [c["name"] for c in calls] == ["get_port_call"], "Timeline Summarizer writes the account with page citations")
    check(thread not in [t["id"] for t in http.get(f"{url}/api/agents/threads", timeout=60).json().get("threads", [])],
          "one-shot agents leave nothing in the chat history")
    for agent in ("quote-negotiator", "timeline-summarizer"):
        n = traced(agent, start[agent] + 1)
        check(n > start[agent], f"{agent} turns are traced to its own experiment ({start[agent]} -> {n})")

    before = traces()
    text, calls, _, thread, failed = chat("port-assistant", "Give me the timeline of port call 20400")
    check(not failed and "port_call_timeline" in [c["name"] for c in calls], "Port Assistant answers with the timeline tool")
    text2, _, _, thread2, _ = chat("port-assistant", "And how long did the vessel wait at anchorage?", thread)
    check(thread2 == thread and bool(text2), "a follow-up continues the same conversation")
    saved = http.get(f"{url}/api/agents/threads/{thread}", timeout=60).json()
    check(len([m for m in saved.get("messages", []) if m["role"] in ("user", "assistant") and m["content"]]) >= 4,
          "the conversation is kept in Lakebase (questions and answers)")
    check(any(t["id"] == thread for t in http.get(f"{url}/api/agents/threads", timeout=60).json()["threads"]), "it is listed in the user's conversations")
    http.delete(f"{url}/api/agents/threads/{thread}", timeout=60)
    n = traced("port-assistant", before["port-assistant"] + 2)
    check(n >= before["port-assistant"] + 2, f"each Port Assistant turn is a trace in its own experiment ({before['port-assistant']} -> {n})")
    exp = agent_experiments(w, a)["port-assistant"]
    roots = sql(f"""SELECT name, COUNT(*) FROM {a.catalog}.{a.prefix}port_assistant.experiment_{w.get_workspace_id()}_{exp}_otel_spans
                   WHERE coalesce(parent_span_id, '') = '' AND time > current_timestamp() - INTERVAL 15 MINUTES GROUP BY name""")
    check(bool(roots) and all(r[0] == "port-assistant" for r in roots), f"its traces start at the agent turn ({roots})")

    if not a.skip_routing:
        for question, tool in [("Which ports have the highest cost per call?", "ask_port_costs"),
                               ("Why are payments on hold?", "ask_da_audit"),
                               ("How long does FDA approval take by port?", "ask_da_operations"),
                               ("What does the pilotage invoice of port call 20217 say?", "search_documents"),
                               ("Give me the timeline of port call 20400", "port_call_timeline")]:
            text, calls, _, thread, failed = chat("port-assistant", question)
            names = [c["name"] for c in calls]
            check(not failed and tool in names and bool(text), f"Port Assistant routes '{question}' to {tool} ({names})")
            if thread:
                http.delete(f"{url}/api/agents/threads/{thread}", timeout=60)

    print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
    sys.exit(1 if FAILS else 0)


def agent_experiments(w: WorkspaceClient, a) -> dict:
    """Agent id -> its MLflow experiment (the app's <agent>-experiment resources)."""
    res = w.apps.get(a.app).resources or []
    return {r.name.removesuffix("-experiment"): r.experiment.experiment_id for r in res if r.experiment}


if __name__ == "__main__":
    main()
