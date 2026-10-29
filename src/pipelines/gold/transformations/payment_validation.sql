-- One row per final DA pack: bank details on the document vs the bank account on the evaluation, total vs the FDA.
-- The account rules are Unity Catalog functions (src/uc_functions) so agents can reuse them. A low-confidence
-- extraction never produces a MATCH: a false MATCH is worse than a false NO_MATCH.
CREATE OR REFRESH MATERIALIZED VIEW payment_validation
COMMENT 'Bank details and totals printed on each final DA pack vs the platform bank account; account numbers stored masked'
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
         pack.swift AS document_swift, pack.bank_confidence,
         c.final_amount, pack.total_amount AS document_total, pack.currency AS document_currency,
         ${catalog}.${gold_schema}.bank_account_match(acc.iban, pack.account_number, pack.bank_confidence) AS account_status,
         ${catalog}.${gold_schema}.swift_match(acc.swift, pack.swift, pack.bank_confidence)                AS swift_status,
         CASE WHEN pack.currency = c.currency AND ABS(pack.total_amount - c.final_amount) <= 0.01
              THEN 'MATCH' ELSE 'NO_MATCH' END                                                          AS amount_status
  FROM pack
  JOIN port_call_costs c ON c.proforma_id = pack.proforma_id
  LEFT JOIN ${catalog}.${silver_schema}.bank_account acc ON acc.id = c.bank_account_id AND acc.__END_AT IS NULL
  WHERE c.evaluation_id IS NOT NULL
)
SELECT
  port_call_id, evaluation_id, proforma_id, file_item_id, port_name, region, agent_name, call_month, currency,
  evaluation_state,
  ${catalog}.${gold_schema}.mask_account(platform_iban)    AS platform_iban_masked,
  ${catalog}.${gold_schema}.mask_account(document_account) AS document_account_masked,
  platform_swift, document_swift, bank_confidence, final_amount, document_total, document_currency,
  account_status, swift_status, amount_status,
  CASE WHEN account_status = 'MATCH' AND swift_status = 'MATCH' AND amount_status = 'MATCH' THEN 'MATCH' ELSE 'NO_MATCH' END
    AS overall_status,
  NOT (account_status = 'MATCH' AND swift_status = 'MATCH') AS hold_payment
FROM checked;
