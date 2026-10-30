-- One row per final DA pack: bank account, SWIFT, total and date printed on the document vs the system of record
-- (the bank account and the invoice date of the evaluation, the final amount of its lines), before money moves.
-- The model only reads the fields; every verdict is a deterministic rule, and the account rules are Unity Catalog
-- functions (src/uc_functions) so agents can reuse them. A low-confidence extraction never produces a MATCH: a false
-- MATCH is strictly worse than a false NO_MATCH. field_checks holds one verdict per field with its explanation.
CREATE OR REFRESH MATERIALIZED VIEW payment_validation
COMMENT 'Bank details, total and date printed on each final DA pack vs the platform, one verdict per field; account numbers stored masked'
AS
WITH pack AS (
  SELECT b.*
  FROM ${catalog}.${silver_schema}.doc_bank_details b
  JOIN ${catalog}.${silver_schema}.documents d USING (file_item_id)
  WHERE d.doc_type = 'final_da_pack'
),
checked AS (
  SELECT c.port_call_id, c.evaluation_id, c.proforma_id, pack.file_item_id, c.port_name, c.region, c.agent_name,
         c.call_month, c.currency, c.evaluation_state,
         acc.iban AS platform_iban, acc.swift AS platform_swift, pack.account_number AS document_account,
         pack.swift AS document_swift, pack.bank_confidence, pack.document_date, pack.date_confidence,
         CAST(ev.invoice_date AS DATE) AS platform_date,
         c.final_amount, pack.total_amount AS document_total, pack.currency AS document_currency,
         ${catalog}.${gold_schema}.bank_account_match(acc.iban, pack.account_number, pack.bank_confidence) AS account_status,
         ${catalog}.${gold_schema}.swift_match(acc.swift, pack.swift, pack.bank_confidence)                AS swift_status,
         CASE WHEN pack.currency = c.currency AND ABS(pack.total_amount - c.final_amount) <= 0.01
              THEN 'MATCH' ELSE 'NO_MATCH' END                                                          AS amount_status,
         CASE WHEN pack.date_confidence >= 0.8 AND pack.document_date = CAST(ev.invoice_date AS DATE)
              THEN 'MATCH' ELSE 'NO_MATCH' END                                                          AS date_status
  FROM pack
  JOIN port_call_costs c ON c.proforma_id = pack.proforma_id
  LEFT JOIN ${catalog}.${silver_schema}.bank_account acc ON acc.id = c.bank_account_id AND acc.__END_AT IS NULL
  LEFT JOIN ${catalog}.${silver_schema}.evaluation ev ON ev.id = c.evaluation_id AND ev.__END_AT IS NULL
  WHERE c.evaluation_id IS NOT NULL
)
SELECT
  port_call_id, evaluation_id, proforma_id, file_item_id, port_name, region, agent_name, call_month, currency,
  evaluation_state,
  ${catalog}.${gold_schema}.mask_account(platform_iban)    AS platform_iban_masked,
  ${catalog}.${gold_schema}.mask_account(document_account) AS document_account_masked,
  platform_swift, document_swift, bank_confidence, final_amount, document_total, document_currency,
  document_date, platform_date, account_status, swift_status, amount_status, date_status,
  ARRAY(
    NAMED_STRUCT('name', 'account', 'status', account_status, 'confidence', bank_confidence,
      'explanation', FORMAT_STRING('Document %s, platform %s', ${catalog}.${gold_schema}.mask_account(document_account),
                                   ${catalog}.${gold_schema}.mask_account(platform_iban))),
    NAMED_STRUCT('name', 'swift', 'status', swift_status, 'confidence', bank_confidence,
      'explanation', FORMAT_STRING('Document %s, platform %s', document_swift, platform_swift)),
    NAMED_STRUCT('name', 'amount', 'status', amount_status, 'confidence', CAST(NULL AS DOUBLE),
      'explanation', FORMAT_STRING('Document %s %s, final lines %s %s', FORMAT_NUMBER(document_total, 2), document_currency,
                                   FORMAT_NUMBER(final_amount, 2), currency)),
    NAMED_STRUCT('name', 'date', 'status', date_status, 'confidence', date_confidence,
      'explanation', FORMAT_STRING('Document %s, platform %s', CAST(document_date AS STRING), CAST(platform_date AS STRING)))
  ) AS field_checks,
  CASE WHEN account_status = 'MATCH' AND swift_status = 'MATCH' AND amount_status = 'MATCH' AND date_status = 'MATCH'
       THEN 'MATCH' ELSE 'NO_MATCH' END AS overall_status,
  NOT (account_status = 'MATCH' AND swift_status = 'MATCH') AS hold_payment
FROM checked;
