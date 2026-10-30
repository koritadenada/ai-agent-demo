"""AI Negotiator: drafts a citation-backed negotiation email for an open PDA quote.

A tool-calling loop: the model reads the quote, the price history and competing quotes through tools (plain SQL on
gold, as the signed-in user), then calls submit_draft. The benchmark math is SQL, never the model, and every amount
in the draft is checked against the numbers the tools returned; amounts that are not found are flagged for the
analyst. Nothing is saved or sent here: the analyst edits the draft and saves it explicitly."""
import json
import re

from . import llm
from .workspace import GOLD, Session

TOOLS = [
    {"type": "function", "function": {
        "name": "get_quote",
        "description": "The open PDA quote: port, vessel, agent and every quoted line with its benchmark (EUR).",
        "parameters": {"type": "object", "properties": {"proforma_id": {"type": "integer"}}, "required": ["proforma_id"]}}},
    {"type": "function", "function": {
        "name": "get_price_history",
        "description": "Final amounts (EUR) paid for this expense at this port on past approved calls, newest first.",
        "parameters": {"type": "object", "properties": {"port_name": {"type": "string"}, "expense_category": {"type": "string"}},
                       "required": ["port_name", "expense_category"]}}},
    {"type": "function", "function": {
        "name": "get_competing_quotes",
        "description": "Past requests for quotes for this expense at this port: lowest, accepted and highest quote (EUR).",
        "parameters": {"type": "object", "properties": {"port_name": {"type": "string"}, "expense_category": {"type": "string"}},
                       "required": ["port_name", "expense_category"]}}},
    {"type": "function", "function": {
        "name": "submit_draft",
        "description": "Submit the finished email. Call once, at the end.",
        "parameters": {"type": "object", "required": ["subject", "body", "lines"], "properties": {
            "subject": {"type": "string"},
            "body": {"type": "string", "description": "The email text, plain text with line breaks"},
            "lines": {"type": "array", "items": {"type": "object", "required": ["expense_name", "quoted_eur", "target_eur", "evidence"],
                      "properties": {"expense_name": {"type": "string"}, "quoted_eur": {"type": "number"},
                                     "target_eur": {"type": "number"}, "evidence": {"type": "string"}}}}}}}},
]


def quote(s: Session, proforma_id: int) -> dict:
    head = s.sql(f"""
        SELECT c.port_call_id, c.proforma_id, c.port_name, c.country, c.vessel_name, c.vessel_type, c.size_band,
               c.agent_name, c.buyer_name, CAST(c.call_month AS STRING) AS call_month, c.currency, c.proforma_state
        FROM {GOLD}.port_call_costs c WHERE c.proforma_id = :p""", p=proforma_id)
    lines = s.sql(f"""
        SELECT proforma_expense_id, expense_name, expense_category, currency, ROUND(quoted_amount, 2) AS quoted_amount,
               quoted_amount_eur, ROUND(benchmark_median_eur, 2) AS benchmark_median_eur, benchmark_level,
               benchmark_sample_size, local_port_min_eur, ROUND(region_min_median_eur, 2) AS region_min_median_eur,
               ROUND(gap_to_benchmark_pct, 1) AS gap_to_benchmark_pct, flagged,
               ROUND(potential_saving_eur, 2) AS potential_saving_eur, reasoning
        FROM {GOLD}.quote_benchmark_flags WHERE proforma_id = :p ORDER BY flagged DESC, potential_saving_eur DESC""",
                  p=proforma_id)
    return {"quote": head[0] if head else None, "lines": lines}


def price_history(s: Session, port_name: str, expense_category: str) -> list[dict]:
    return s.sql(f"""
        SELECT CAST(r.call_month AS STRING) AS call_month, r.vessel_name, r.vessel_type, r.size_band,
               r.final_amount_eur, r.port_call_id
        FROM {GOLD}.expense_reconciliation r
        JOIN {GOLD}.port_call_costs c ON c.evaluation_id = r.evaluation_id
        WHERE r.port_name = :port AND r.expense_category = :cat AND c.evaluation_state IN ('APPROVED', 'PAID')
        ORDER BY r.call_month DESC, r.port_call_id DESC LIMIT 8""", port=port_name, cat=expense_category)


def competing_quotes(s: Session, port_name: str, expense_category: str) -> list[dict]:
    return s.sql(f"""
        SELECT CAST(call_month AS STRING) AS call_month, vessel_type, size_band, quotes_received,
               lowest_amount_eur, accepted_amount_eur, highest_amount_eur
        FROM {GOLD}.rfq_comparison
        WHERE port_name = :port AND expense_category = :cat AND quotes_received > 1
        ORDER BY call_month DESC LIMIT 5""", port=port_name, cat=expense_category)


def _numbers(obj) -> set[str]:
    """Every number in the tool results, as it would be written with 2 decimals."""
    found = set()

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            found.add(f"{o:,.2f}")
        elif isinstance(o, str):
            found.update(m for m in re.findall(r"\d{1,3}(?:,\d{3})*\.\d{2}", o))
    walk(obj)
    return found


def unverified_amounts(body: str, results: list) -> list[str]:
    known = _numbers(results)
    amounts = re.findall(r"\d{1,3}(?:,\d{3})*\.\d{2}(?!\d)(?!\s*%)", body)
    return sorted({a for a in amounts if a not in known})


def draft(s: Session, proforma_id: int, instructions: str = "") -> dict:
    p = llm.prompt("negotiator")
    system = p.template.replace("{{instructions}}", instructions.strip() or "none")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": f"Draft the negotiation email for the open PDA quote {proforma_id}."}]
    steps, results = [], []
    run = {
        "get_quote": lambda a: quote(s, int(a["proforma_id"])),
        "get_price_history": lambda a: price_history(s, a["port_name"], a["expense_category"]),
        "get_competing_quotes": lambda a: competing_quotes(s, a["port_name"], a["expense_category"]),
    }
    for _ in range(10):
        msg = llm.chat(s.w, p.model, messages, TOOLS, effort="medium")
        calls = msg.get("tool_calls") or []
        if not calls:
            messages += [{"role": "assistant", "content": llm.text(msg) or "(no text)"},
                         {"role": "user", "content": "Call submit_draft with the email now."}]
            continue
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            name, args = c["function"]["name"], json.loads(c["function"].get("arguments") or "{}")
            if name == "submit_draft":
                return {**args, "unverified_amounts": unverified_amounts(args.get("body", ""), results),
                        "steps": steps, "prompt_version": p.version, "model": p.model}
            out = run[name](args) if name in run else {"error": f"unknown tool {name}"}
            results.append(out)
            steps.append({"tool": name, "args": args, "rows": len(out["lines"]) if isinstance(out, dict) and "lines" in out
                          else len(out) if isinstance(out, list) else 1})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out, default=str)})
    raise RuntimeError("The negotiator did not finish the draft")
