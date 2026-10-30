"""DA Event Summarizer: the port call timeline (structured events from the statement of facts, stored by the
document pipeline) and a written account generated on demand, never stored, with the page of each event."""
from . import llm
from .workspace import GOLD, SILVER, Session


def port_call(s: Session, port_call_id: int) -> dict:
    head = s.sql(f"""
        SELECT c.port_call_id, c.proforma_id, c.evaluation_id, c.vessel_name, c.imo, c.vessel_type, c.gross_tonnage,
               c.port_name, c.country, c.agent_name, c.buyer_name, c.port_call_state, c.currency,
               CAST(c.schedule_date_in AS STRING) AS schedule_date_in, CAST(c.schedule_date_out AS STRING) AS schedule_date_out,
               ROUND(c.port_stay_hours, 1) AS port_stay_hours, ROUND(c.quoted_amount, 2) AS quoted_amount,
               ROUND(c.final_amount, 2) AS final_amount, c.variance_pct, c.evaluation_state,
               CAST(c.appointment_created_at AS STRING) AS appointment_created_at,
               CAST(c.pda_submitted_at AS STRING) AS pda_submitted_at, CAST(c.fda_created_at AS STRING) AS fda_created_at,
               CAST(c.fda_approved_at AS STRING) AS fda_approved_at, ROUND(c.fda_approval_hours, 1) AS fda_approval_hours
        FROM {GOLD}.port_call_costs c WHERE c.port_call_id = :pc""", pc=port_call_id)
    if not head:
        return {"port_call": None, "events": [], "documents": []}
    proforma = head[0]["proforma_id"]
    events = s.sql(f"""
        SELECT e.event_order, e.event, CAST(e.event_time AS STRING) AS event_time, e.event_time_text, e.page_number,
               e.file_item_id
        FROM {SILVER}.port_call_events e WHERE e.proforma_id = :p ORDER BY e.event_order""", p=proforma)
    documents = s.sql(f"""SELECT file_item_id, doc_type, page_count FROM {SILVER}.documents
                          WHERE proforma_id = :p ORDER BY doc_type""", p=proforma)
    return {"port_call": head[0], "events": events, "documents": documents}


def write(s: Session, port_call_id: int) -> dict:
    data = port_call(s, port_call_id)
    pc = data["port_call"]
    if not pc or not data["events"]:
        return {"story": None, "reason": "No statement of facts has been read for this port call yet"}
    p = llm.prompt("port_call_story")
    header = (f"{pc['vessel_name']} ({pc['vessel_type']}, {pc['gross_tonnage']} GT) at {pc['port_name']}, "
              f"agent {pc['agent_name']}, port call {pc['port_call_id']}")
    events = "\n".join(f"{e['event_order']}. {e['event_time'] or e['event_time_text']}: {e['event']} (p. {e['page_number']})"
                       for e in data["events"])
    milestones = "\n".join(f"{k.replace('_', ' ')}: {pc[k]}" for k in
                           ("appointment_created_at", "pda_submitted_at", "fda_created_at", "fda_approved_at",
                            "fda_approval_hours") if pc.get(k) is not None)
    text = (p.template.replace("{{port_call}}", header).replace("{{events}}", events)
            .replace("{{milestones}}", milestones or "none"))
    msg = llm.chat(s.w, p.model, [{"role": "user", "content": text}])
    return {"story": llm.text(msg), "prompt_version": p.version, "model": p.model}
