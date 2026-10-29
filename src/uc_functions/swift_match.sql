-- SWIFT/BIC check: 8 and 11 character forms of the same head office are equivalent (XXX branch).
CREATE OR REPLACE FUNCTION {catalog}.{gold_schema}.swift_match(
  platform_swift STRING, document_swift STRING, extraction_confidence DOUBLE)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'MATCH or NO_MATCH: platform SWIFT vs the SWIFT printed on a document, 8 vs 11 characters aware'
AS $$
import re

CONFIDENCE_FLOOR = 0.8

def norm(value):
    code = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    return code[:8] if len(code) == 11 and code.endswith("XXX") else code

if extraction_confidence is None or extraction_confidence < CONFIDENCE_FLOOR:
    return "NO_MATCH"
a, b = norm(platform_swift), norm(document_swift)
return "MATCH" if a and len(a) in (8, 11) and a == b else "NO_MATCH"
$$;
