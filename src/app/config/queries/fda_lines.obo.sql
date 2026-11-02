-- The lines of one final DA: quote, final, invoice pages and the verdict with its explanation.
-- @param gold STRING = korita_catalog.portcall_gold
-- @param evaluation_id BIGINT = 60217
SELECT expense_evaluation_id, expense_section, line_name, currency, ROUND(quoted_amount, 2) AS quoted_amount,
       ROUND(final_amount, 2) AS final_amount, invoiced_amount, invoiced_currency, variance_vs_quote_pct,
       evidence_pages, verdict, explanation, review_action, file_item_id
FROM IDENTIFIER(:gold || '.expense_reconciliation') WHERE evaluation_id = :evaluation_id
ORDER BY CASE review_action WHEN 'dispute' THEN 0 WHEN 'review' THEN 1 ELSE 2 END, expense_section, line_name
