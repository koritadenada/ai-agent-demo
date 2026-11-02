-- The bank detail check of one final DA, field by field.
-- @param gold STRING = korita_catalog.portcall_gold
-- @param evaluation_id BIGINT = 60217
SELECT overall_status, hold_payment, to_json(field_checks) AS field_checks
FROM IDENTIFIER(:gold || '.payment_validation') WHERE evaluation_id = :evaluation_id
