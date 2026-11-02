-- The statement of facts timeline of one port call, with the page of each event.
-- @param gold STRING = korita_catalog.portcall_gold
-- @param silver STRING = korita_catalog.portcall_silver
-- @param port_call_id BIGINT = 20400
SELECT e.event_order, e.event, CAST(e.event_time AS STRING) AS event_time, e.event_time_text, e.page_number, e.file_item_id
FROM IDENTIFIER(:silver || '.port_call_events') e
JOIN IDENTIFIER(:gold || '.port_call_costs') c ON c.proforma_id = e.proforma_id
WHERE c.port_call_id = :port_call_id ORDER BY e.event_order
