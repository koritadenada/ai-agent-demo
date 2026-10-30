-- HAL-9000 tool: the timeline of one port call, read from its statement of facts, with the page of every event.
CREATE OR REPLACE FUNCTION {catalog}.{gold_schema}.port_call_timeline(
  port_call BIGINT COMMENT 'The port call id, for example 20217'
)
RETURNS TABLE (port_call_id BIGINT, vessel_name STRING, port_name STRING, event_order INT, event STRING,
               event_time TIMESTAMP, page_number INT)
COMMENT 'Events of one port call in order (arrival, pilot, all fast, operations, sailing), from its statement of facts'
RETURN
  SELECT c.port_call_id, c.vessel_name, c.port_name, e.event_order, e.event, e.event_time, e.page_number
  FROM {catalog}.{silver_schema}.port_call_events e
  JOIN {catalog}.{gold_schema}.port_call_costs c ON c.proforma_id = e.proforma_id
  WHERE c.port_call_id = port_call
  ORDER BY e.event_order;
