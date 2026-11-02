-- Decisions taken on one final DA, newest first.
-- @param app STRING = korita_catalog.portcall_app
-- @param evaluation_id BIGINT = 60217
SELECT decision, note, decided_by, CAST(decided_at AS STRING) AS decided_at
FROM IDENTIFIER(:app || '.analyst_decisions') WHERE evaluation_id = :evaluation_id ORDER BY decided_at DESC
