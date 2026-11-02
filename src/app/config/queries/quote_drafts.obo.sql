-- Negotiation drafts saved for one quote.
-- @param app STRING = korita_catalog.portcall_app
-- @param proforma_id BIGINT = 50419
SELECT subject, created_by, CAST(created_at AS STRING) AS created_at
FROM IDENTIFIER(:app || '.negotiation_drafts') WHERE proforma_id = :proforma_id ORDER BY created_at DESC
