-- The PDFs of one DA, by its final DA or its port call (pass 0 for the other), with their path in the volume.
-- @param gold STRING = korita_catalog.portcall_gold
-- @param silver STRING = korita_catalog.portcall_silver
-- @param evaluation_id BIGINT = 60217
-- @param port_call_id BIGINT = 0
SELECT d.file_item_id, d.doc_type, d.page_count, regexp_replace(d.path, '^/Volumes/[^/]+/[^/]+/[^/]+/', '') AS volume_path
FROM IDENTIFIER(:silver || '.documents') d
JOIN IDENTIFIER(:gold || '.port_call_costs') c ON c.proforma_id = d.proforma_id
WHERE c.evaluation_id = :evaluation_id OR c.port_call_id = :port_call_id
ORDER BY d.doc_type
