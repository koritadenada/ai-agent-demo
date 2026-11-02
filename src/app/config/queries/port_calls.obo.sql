-- Port calls with a statement of facts, the stay and the longest wait (operations time is work, not waiting).
-- @param gold STRING = korita_catalog.portcall_gold
-- @param silver STRING = korita_catalog.portcall_silver
WITH sof AS (SELECT DISTINCT proforma_id FROM IDENTIFIER(:silver || '.documents') WHERE doc_type = 'statement_of_facts'),
steps AS (
  SELECT proforma_id, event, LAG(event) OVER w AS previous_event,
         (unix_timestamp(event_time) - unix_timestamp(LAG(event_time) OVER w)) / 3600 AS hours
  FROM IDENTIFIER(:silver || '.port_call_events') WINDOW w AS (PARTITION BY proforma_id ORDER BY event_order)
),
waits AS (
  SELECT proforma_id, COUNT(*) AS events,
         MAX_BY(named_struct('from_event', previous_event, 'to_event', event, 'hours', hours),
                IF(previous_event ILIKE 'commenced%', NULL, hours)) AS longest
  FROM steps GROUP BY proforma_id
)
SELECT c.port_call_id, c.vessel_name, c.port_name, c.agent_name, CAST(c.call_month AS STRING) AS call_month,
       ROUND(c.port_stay_hours, 1) AS port_stay_hours, w.events, w.longest.from_event AS wait_from,
       w.longest.to_event AS wait_to, ROUND(w.longest.hours, 1) AS longest_wait_hours
FROM sof JOIN IDENTIFIER(:gold || '.port_call_costs') c ON c.proforma_id = sof.proforma_id
LEFT JOIN waits w ON w.proforma_id = sof.proforma_id
ORDER BY c.call_month DESC, c.port_call_id DESC
