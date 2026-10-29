-- Deterministic, asymmetric account check: a false MATCH is strictly worse than a false NO_MATCH.
-- MATCH when the normalised IBANs are equal, or when the document shows a domestic account number that is
-- the anchored tail of the IBAN (at least 8 digits). Below the confidence floor the answer is always NO_MATCH.
CREATE OR REPLACE FUNCTION {catalog}.{gold_schema}.bank_account_match(
  platform_iban STRING, document_account STRING, extraction_confidence DOUBLE)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'MATCH or NO_MATCH: platform IBAN vs the account printed on a document (IBAN or domestic tail)'
AS $$
import re

CONFIDENCE_FLOOR = 0.8

def norm(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())

if extraction_confidence is None or extraction_confidence < CONFIDENCE_FLOOR:
    return "NO_MATCH"
iban, doc = norm(platform_iban), norm(document_account)
if not iban or not doc:
    return "NO_MATCH"
if iban == doc:
    return "MATCH"
# Domestic format: digits only, long enough to be meaningful, and the exact end of the IBAN
if doc.isdigit() and len(doc) >= 8 and iban.endswith(doc):
    return "MATCH"
return "NO_MATCH"
$$;
