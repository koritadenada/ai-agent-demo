"""Port-call agents app: the screens the analysts use, on top of the gold tables and the agents.

  Overview             what needs attention today
  DA review            SOF Port Bill Analysis + PDA/FDA Validator per final DA, with the invoice pages; accept,
                       dispute or hold (saved only after the analyst confirms)
  AI Negotiator        open PDA quotes above the benchmark; drafts the email with the evidence
  Port call            DA Event Summarizer: the statement of facts timeline and a written account on demand
  HAL-9000             questions in plain language, answered by the supervisor agent and its Genie agents

Every call runs as the signed-in user (see backend/workspace.py)."""
import json
import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import hal, llm, negotiator, story
from backend.workspace import APP, GOLD, SILVER, Session, session

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Port-call agents")


@app.exception_handler(Exception)
async def errors(_, e: Exception):
    logging.exception("request failed")
    return JSONResponse(status_code=500, content={"detail": str(e)})


LATEST_DECISION = f"""(SELECT * FROM {APP}.analyst_decisions
                       QUALIFY ROW_NUMBER() OVER (PARTITION BY evaluation_id ORDER BY decided_at DESC) = 1)"""


@app.get("/api/me")
def me(s: Session = Depends(session)):
    return {"user": s.user}


@app.get("/api/overview")
def overview(s: Session = Depends(session)):
    kpi = s.sql(f"""
        SELECT
          (SELECT COUNT(*) FROM {GOLD}.port_bill_analysis WHERE analysis_status <> 'NO_DOCUMENTS') AS fdas_checked,
          (SELECT COUNT(*) FROM {GOLD}.port_bill_analysis b LEFT JOIN {LATEST_DECISION} d USING (evaluation_id)
            WHERE b.analysis_status <> 'NO_DOCUMENTS' AND d.decision IS NULL) AS fdas_to_review,
          (SELECT COUNT(*) FROM {GOLD}.payment_validation p LEFT JOIN {LATEST_DECISION} d USING (evaluation_id)
            WHERE p.hold_payment AND d.decision IS NULL) AS payments_on_hold,
          (SELECT COUNT(*) FROM {GOLD}.expense_reconciliation WHERE has_documents AND review_action <> 'accept') AS lines_to_review,
          (SELECT ROUND(SUM(over_invoiced_amount_eur), 2) FROM {GOLD}.expense_reconciliation WHERE has_documents) AS over_invoiced_eur,
          (SELECT COUNT(DISTINCT proforma_id) FROM {GOLD}.quote_benchmark_flags WHERE proforma_state = 'SUBMITTED' AND flagged) AS open_quotes_flagged,
          (SELECT ROUND(SUM(potential_saving_eur), 2) FROM {GOLD}.quote_benchmark_flags WHERE proforma_state = 'SUBMITTED' AND flagged) AS open_quote_savings_eur,
          (SELECT ROUND(AVG(CAST(agrees_with_analyst AS INT)) * 100, 1) FROM {GOLD}.expense_reconciliation) AS agreement_pct
    """)[0]
    return {"kpi": kpi, "fdas": fdas(s)[:6], "quotes": quotes(s)[:5]}


@app.get("/api/fdas")
def fdas(s: Session = Depends(session)):
    return s.sql(f"""
        SELECT b.evaluation_id, b.port_call_id, b.proforma_id, b.port_name, b.agent_name, b.buyer_name,
               CAST(b.call_month AS STRING) AS call_month, b.currency, b.analysis_status, b.lines_checked,
               b.lines_flagged, c.vessel_name, c.vessel_type, ROUND(c.final_amount, 2) AS final_amount,
               c.final_amount_eur, p.overall_status, p.hold_payment, d.decision,
               CAST(d.decided_at AS STRING) AS decided_at, d.decided_by
        FROM {GOLD}.port_bill_analysis b
        JOIN {GOLD}.port_call_costs c ON c.evaluation_id = b.evaluation_id
        LEFT JOIN {GOLD}.payment_validation p ON p.evaluation_id = b.evaluation_id
        LEFT JOIN {LATEST_DECISION} d ON d.evaluation_id = b.evaluation_id
        WHERE b.analysis_status <> 'NO_DOCUMENTS'
        ORDER BY d.decision IS NOT NULL, p.hold_payment DESC, b.lines_flagged DESC, b.port_call_id DESC""")


@app.get("/api/fdas/{evaluation_id}")
def fda(evaluation_id: int, s: Session = Depends(session)):
    head = [f for f in fdas(s) if f["evaluation_id"] == evaluation_id]
    if not head:
        raise HTTPException(404, "No checked final DA with this id")
    lines = s.sql(f"""
        SELECT expense_evaluation_id, expense_section, expense_category, line_name, currency,
               ROUND(quoted_amount, 2) AS quoted_amount, ROUND(final_amount, 2) AS final_amount, invoiced_amount,
               invoiced_currency, invoiced_in_da_currency, roe_source, variance_vs_quote_pct, evidence_pages,
               evidence_confidence, line_match, verdict, explanation, review_action, analyst_verdict,
               agrees_with_analyst, ROUND(benchmark_median_eur, 2) AS benchmark_median_eur, benchmark_level,
               benchmark_sample_size, ROUND(benchmark_gap_pct, 1) AS benchmark_gap_pct, file_item_id
        FROM {GOLD}.expense_reconciliation WHERE evaluation_id = :e
        ORDER BY CASE review_action WHEN 'dispute' THEN 0 WHEN 'review' THEN 1 ELSE 2 END, expense_section, line_name""",
                  e=evaluation_id)
    payment = s.sql(f"""
        SELECT platform_iban_masked, document_account_masked, platform_swift, document_swift, bank_confidence,
               ROUND(final_amount, 2) AS final_amount, document_total, document_currency,
               CAST(document_date AS STRING) AS document_date, CAST(platform_date AS STRING) AS platform_date,
               field_checks, overall_status, hold_payment, file_item_id
        FROM {GOLD}.payment_validation WHERE evaluation_id = :e""", e=evaluation_id)
    documents = s.sql(f"""
        SELECT file_item_id, doc_type, page_count FROM {SILVER}.documents WHERE proforma_id = :p ORDER BY doc_type""",
                      p=head[0]["proforma_id"])
    history = s.sql(f"""
        SELECT decision, note, decided_by, CAST(decided_at AS STRING) AS decided_at
        FROM {APP}.analyst_decisions WHERE evaluation_id = :e ORDER BY decided_at DESC""", e=evaluation_id)
    return {"fda": head[0], "lines": lines, "payment": payment[0] if payment else None, "documents": documents,
            "decisions": history}


class Decision(BaseModel):
    decision: str = Field(pattern="^(accept|dispute|hold)$")
    note: str = Field(default="", max_length=2000)


@app.post("/api/fdas/{evaluation_id}/decision")
def decide(evaluation_id: int, d: Decision, s: Session = Depends(session)):
    f = fda(evaluation_id, s)["fda"]
    s.sql(f"""INSERT INTO {APP}.analyst_decisions
              SELECT uuid(), :e, :pc, :decision, :note, :flagged, :user, current_timestamp()""",
          e=evaluation_id, pc=f["port_call_id"], decision=d.decision, note=d.note, flagged=f["lines_flagged"],
          user=s.user)
    return {"saved": True}


@app.get("/api/documents/{file_item_id}")
def document(file_item_id: int, s: Session = Depends(session)):
    rows = s.sql(f"SELECT path FROM {SILVER}.documents WHERE file_item_id = :f", f=file_item_id)
    if not rows:
        raise HTTPException(404, "No such document")
    pdf = s.w.files.download(rows[0]["path"]).contents.read()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.get("/api/quotes")
def quotes(s: Session = Depends(session)):
    return s.sql(f"""
        SELECT q.proforma_id, q.port_call_id, q.port_name, q.agent_name, q.buyer_name, q.vessel_type, q.size_band,
               CAST(q.call_month AS STRING) AS call_month, c.vessel_name, COUNT(*) AS lines,
               COUNT_IF(q.flagged) AS flagged_lines, ROUND(SUM(q.quoted_amount_eur), 2) AS quoted_eur,
               ROUND(SUM(q.potential_saving_eur) FILTER (WHERE q.flagged), 2) AS saving_eur,
               MAX(n.created_at) IS NOT NULL AS has_draft
        FROM {GOLD}.quote_benchmark_flags q
        JOIN {GOLD}.port_call_costs c ON c.proforma_id = q.proforma_id
        LEFT JOIN {APP}.negotiation_drafts n ON n.proforma_id = q.proforma_id
        WHERE q.proforma_state = 'SUBMITTED'
        GROUP BY ALL ORDER BY flagged_lines DESC, saving_eur DESC NULLS LAST""")


@app.get("/api/quotes/{proforma_id}")
def quote(proforma_id: int, s: Session = Depends(session)):
    q = negotiator.quote(s, proforma_id)
    if not q["quote"]:
        raise HTTPException(404, "No such quote")
    q["drafts"] = s.sql(f"""
        SELECT draft_id, subject, body, lines, unverified_numbers, created_by, CAST(created_at AS STRING) AS created_at
        FROM {APP}.negotiation_drafts WHERE proforma_id = :p ORDER BY created_at DESC""", p=proforma_id)
    return q


class DraftRequest(BaseModel):
    instructions: str = Field(default="", max_length=1000)


@app.post("/api/quotes/{proforma_id}/draft")
def draft(proforma_id: int, r: DraftRequest, s: Session = Depends(session)):
    return negotiator.draft(s, proforma_id, r.instructions)


class Draft(BaseModel):
    subject: str = Field(max_length=300)
    body: str = Field(max_length=10000)
    lines: list = []
    unverified_amounts: list = []
    prompt_version: str = ""
    model: str = ""


@app.post("/api/quotes/{proforma_id}/drafts")
def save_draft(proforma_id: int, d: Draft, s: Session = Depends(session)):
    q = negotiator.quote(s, proforma_id)["quote"]
    s.sql(f"""INSERT INTO {APP}.negotiation_drafts
              SELECT uuid(), :p, :pc, :agent, :subject, :body, :lines, :unverified, :pv, :model, :user, current_timestamp()""",
          p=proforma_id, pc=q["port_call_id"], agent=q["agent_name"], subject=d.subject, body=d.body,
          lines=json.dumps(d.lines), unverified=json.dumps(d.unverified_amounts), pv=d.prompt_version, model=d.model,
          user=s.user)
    return {"saved": True}


@app.get("/api/port-calls/{port_call_id}")
def port_call(port_call_id: int, s: Session = Depends(session)):
    return story.port_call(s, port_call_id)


@app.post("/api/port-calls/{port_call_id}/story")
def port_call_story(port_call_id: int, s: Session = Depends(session)):
    return story.write(s, port_call_id)


class Ask(BaseModel):
    messages: list[dict]


@app.post("/api/hal")
def ask_hal(a: Ask, s: Session = Depends(session)):
    return hal.ask(s, a.messages[-12:])


@app.get("/api/agents")
def agents(s: Session = Depends(session)):
    host = s.w.config.host.rstrip("/")
    rows = s.sql(f"SELECT agent, endpoint_name, resource_id FROM {APP}.agent_registry")
    return [{**r, "url": f"{host}/genie/rooms/{r['resource_id']}" if r["agent"] != "hal_9000" else None} for r in rows]


@app.get("/api/prompts")
def prompts():
    return {n: llm.prompt(n).version for n in ("negotiator", "port_call_story")}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/{path:path}")
def spa(path: str):
    return FileResponse("static/index.html")
