-- Gold never stores a full account number: country code and the last 4 characters only.
CREATE OR REPLACE FUNCTION {catalog}.{gold_schema}.mask_account(account STRING)
RETURNS STRING
COMMENT 'Masks an IBAN or account number, keeping the first 2 and last 4 characters'
RETURN CASE
  WHEN account IS NULL THEN NULL
  WHEN length(regexp_replace(account, '\\s', '')) <= 6 THEN '****'
  ELSE concat(left(regexp_replace(account, '\\s', ''), 2), '** **** ', right(regexp_replace(account, '\\s', ''), 4))
END;
