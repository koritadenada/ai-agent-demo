-- What needs attention: final DAs without a decision, payments on hold, over-invoicing, open quotes to negotiate.
-- @param gold STRING = korita_catalog.portcall_gold
-- @param app STRING = korita_catalog.portcall_app
SELECT
  (SELECT COUNT(*) FROM IDENTIFIER(:gold || '.port_bill_analysis') WHERE analysis_status <> 'NO_DOCUMENTS') AS fdas_checked,
  (SELECT COUNT(*) FROM IDENTIFIER(:gold || '.port_bill_analysis') b LEFT JOIN (SELECT * FROM IDENTIFIER(:app || '.analyst_decisions') QUALIFY ROW_NUMBER() OVER (PARTITION BY evaluation_id ORDER BY decided_at DESC) = 1) d USING (evaluation_id)
    WHERE b.analysis_status <> 'NO_DOCUMENTS' AND d.decision IS NULL) AS fdas_to_review,
  (SELECT COUNT(*) FROM IDENTIFIER(:gold || '.payment_validation') p LEFT JOIN (SELECT * FROM IDENTIFIER(:app || '.analyst_decisions') QUALIFY ROW_NUMBER() OVER (PARTITION BY evaluation_id ORDER BY decided_at DESC) = 1) d USING (evaluation_id)
    WHERE p.hold_payment AND d.decision IS NULL) AS payments_on_hold,
  (SELECT ROUND(SUM(over_invoiced_amount_eur), 2) FROM IDENTIFIER(:gold || '.expense_reconciliation') WHERE has_documents) AS over_invoiced_eur,
  (SELECT COUNT(DISTINCT proforma_id) FROM IDENTIFIER(:gold || '.quote_benchmark_flags') WHERE proforma_state = 'SUBMITTED' AND flagged) AS open_quotes_flagged,
  (SELECT ROUND(SUM(potential_saving_eur), 2) FROM IDENTIFIER(:gold || '.quote_benchmark_flags') WHERE proforma_state = 'SUBMITTED' AND flagged) AS open_quote_savings_eur,
  (SELECT ROUND(AVG(CAST(agrees_with_analyst AS INT)) * 100, 1) FROM IDENTIFIER(:gold || '.expense_reconciliation')) AS agreement_pct
