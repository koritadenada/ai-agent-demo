"""End-to-end test of the deployed agents app, as a signed-in user (CLI OAuth token).

Checks every screen's API against SQL on gold, the two app agents, HAL-9000 routing, the confirmed writes (removed
again afterwards) and input validation. Usage:
  python tests/app_e2e.py --profile <profile> --app <app name> --catalog <catalog> [--prefix portcall_] [--skip-hal]
"""
import argparse
import json
import subprocess
import sys

import requests
from databricks.sdk import WorkspaceClient

FAILS = []


def check(ok: bool, what: str):
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--app", default="portcall-agents")
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--prefix", default="portcall_")
    ap.add_argument("--skip-hal", action="store_true")
    a = ap.parse_args()
    w = WorkspaceClient(profile=a.profile)
    gold, app = f"{a.catalog}.{a.prefix}gold", f"{a.catalog}.{a.prefix}app"
    token = json.loads(subprocess.check_output(["databricks", "auth", "token", "--profile", a.profile]))["access_token"]
    url = w.apps.get(a.app).url
    http = requests.Session()
    http.headers["Authorization"] = f"Bearer {token}"
    get = lambda p: http.get(f"{url}/api/{p}", timeout=120)  # noqa: E731
    post = lambda p, b: http.post(f"{url}/api/{p}", json=b, timeout=300)  # noqa: E731
    wh = next(x.id for x in w.warehouses.list() if x.name == "Serverless Starter Warehouse")

    def sql(q):
        r = w.statement_execution.execute_statement(q, wh, wait_timeout="50s")
        return r.result.data_array or [] if r.result else []

    me = get("me").json()
    check(me["user"] == w.current_user.me().user_name, f"runs as the signed-in user ({me['user']})")

    k = get("overview").json()["kpi"]
    holds = int(sql(f"SELECT COUNT(*) FROM {gold}.payment_validation WHERE hold_payment")[0][0])
    check(k["payments_on_hold"] <= holds, f"overview payments on hold {k['payments_on_hold']} (gold {holds})")
    agree = float(sql(f"SELECT ROUND(AVG(CAST(agrees_with_analyst AS INT)) * 100, 1) FROM {gold}.expense_reconciliation")[0][0])
    check(abs(k["agreement_pct"] - agree) < .01, f"overview agreement {k['agreement_pct']}% = gold")

    fdas = get("fdas").json()
    check(len(fdas) == int(sql(f"SELECT COUNT(*) FROM {gold}.port_bill_analysis WHERE analysis_status <> 'NO_DOCUMENTS'")[0][0]),
          f"DA review lists every checked final DA ({len(fdas)})")
    for f in [next(x for x in fdas if not x["hold_payment"]), next(x for x in fdas if x["hold_payment"])]:
        d = get(f"fdas/{f['evaluation_id']}").json()
        check(len(d["lines"]) == f["lines_checked"], f"FDA {f['evaluation_id']}: {len(d['lines'])} lines = lines checked")
        final = float(sql(f"SELECT ROUND(final_amount, 2) FROM {gold}.port_call_costs WHERE evaluation_id = {f['evaluation_id']}")[0][0])
        check(abs(sum(l["final_amount"] for l in d["lines"]) - final) < .05, f"FDA {f['evaluation_id']}: lines add up to the final DA {final}")
        check(all(l["evidence_pages"] for l in d["lines"] if l["verdict"] != "NO_EVIDENCE"), f"FDA {f['evaluation_id']}: every line with evidence cites a page")
        check(all("****" in (d["payment"][c] or "****") for c in ("platform_iban_masked", "document_account_masked")), f"FDA {f['evaluation_id']}: accounts masked")
        pack = next(x for x in d["documents"] if x["doc_type"] == "final_da_pack")
        r = get(f"documents/{pack['file_item_id']}")
        check(r.status_code == 200 and r.content[:5] == b"%PDF-", f"FDA {f['evaluation_id']}: final DA pack PDF opens")
    held = next(x for x in fdas if x["hold_payment"])
    check(next(c for c in get(f"fdas/{held['evaluation_id']}").json()["payment"]["field_checks"] if c["name"] == "account")["status"] == "NO_MATCH",
          "payment on hold shows the account mismatch")

    # confirmed writes, then removed
    r = post(f"fdas/{fdas[0]['evaluation_id']}/decision", {"decision": "approve"})
    check(r.status_code == 422, "an unknown decision is rejected")
    r = post(f"fdas/{fdas[0]['evaluation_id']}/decision", {"decision": "hold", "note": "e2e test"})
    check(r.ok and get(f"fdas/{fdas[0]['evaluation_id']}").json()["decisions"][0]["note"] == "e2e test", "a confirmed decision is saved and shown")
    sql(f"DELETE FROM {app}.analyst_decisions WHERE note = 'e2e test'")

    quotes = get("quotes").json()
    flagged = next(q for q in quotes if q["flagged_lines"])
    q = get(f"quotes/{flagged['proforma_id']}").json()
    check(sum(l["flagged"] for l in q["lines"]) == flagged["flagged_lines"], f"quote {flagged['proforma_id']}: flagged lines match")
    dr = post(f"quotes/{flagged['proforma_id']}/draft", {"instructions": ""})
    check(dr.ok, f"AI Negotiator drafts an email ({dr.status_code})")
    if dr.ok:
        d = dr.json()
        check(d["steps"][0]["tool"] == "get_quote", "AI Negotiator reads the quote first")
        check(d["unverified_amounts"] == [], f"AI Negotiator: every amount found in the data ({d['unverified_amounts']})")
        names = {l["expense_name"] for l in q["lines"] if l["flagged"]}
        check({l["expense_name"] for l in d["lines"]} <= names, "AI Negotiator negotiates only flagged lines")
        check("—" not in d["body"] + d["subject"] and "–" not in d["body"] + d["subject"], "AI Negotiator: no dashes as punctuation")
        r = post(f"quotes/{flagged['proforma_id']}/drafts", {**d, "subject": "e2e test"})
        check(r.ok and get(f"quotes/{flagged['proforma_id']}").json()["drafts"][0]["subject"] == "e2e test", "a confirmed draft is saved and shown")
        sql(f"DELETE FROM {app}.negotiation_drafts WHERE subject = 'e2e test'")

    pc = get(f"port-calls/{fdas[0]['port_call_id']}").json()
    check(len(pc["events"]) > 0 and all(e["event_time"] for e in pc["events"]), f"port call {fdas[0]['port_call_id']}: timeline with times")
    st = post(f"port-calls/{fdas[0]['port_call_id']}/story", {}).json()
    check(bool(st.get("story")) and "(p. " in st["story"], "DA Event Summarizer writes an account with page citations")
    check(all(v.endswith(("v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9")) for v in get("prompts").json().values()),
          f"app prompts come from the registry {get('prompts').json()}")

    if not a.skip_hal:
        for question, agent in [("Which ports have the highest cost per call?", "Port costs and benchmarks"),
                                ("Why are payments on hold?", "DA audit"),
                                ("How long does FDA approval take by port?", "DA operations"),
                                ("What does the pilotage invoice of port call 20217 say?", "Document search"),
                                ("Give me the timeline of port call 20400", "Port call timeline")]:
            r = post("hal", {"messages": [{"role": "user", "content": question}]})
            got = r.json().get("agents", []) if r.ok else r.text[:200]
            check(r.ok and agent in got and bool(r.json()["answer"]), f"HAL-9000 routes '{question}' to {agent} ({got})")

    print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
