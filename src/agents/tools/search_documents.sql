-- HAL-9000 tool: keyword search over the text of every PDF page (PDA quotes, final DA packs, statements of facts).
-- Ranked by how many of the words appear on the page, then how often, optionally for one port call; account numbers are masked in
-- the snippet, like in gold.
CREATE OR REPLACE FUNCTION {catalog}.{gold_schema}.search_documents(
  query STRING COMMENT 'Words to look for, for example: pilotage invoice',
  port_call BIGINT DEFAULT NULL COMMENT 'Only the documents of this port call id, when the question names one'
)
RETURNS TABLE (port_call_id BIGINT, vessel_name STRING, port_name STRING, doc_type STRING, file_item_id BIGINT,
               page_number INT, words_matched INT, snippet STRING)
COMMENT 'Searches the text of all port call documents and returns the best matching pages with a snippet and the page number to cite'
RETURN
  WITH words AS (
    -- a crude stem (first 5 letters) so pilotage also finds pilot fees and pilots
    SELECT transform(filter(split(lower(query), '[^a-z0-9]+'), w -> length(w) > 2), w -> left(w, 5)) AS w
  ),
  pages AS (
    SELECT p.*, regexp_replace(p.page_text, '<[^>]+>', ' ') AS text
    FROM {catalog}.{silver_schema}.document_pages p
    WHERE p.page_error IS NULL
  ),
  scored AS (
    SELECT pages.*, size(filter(words.w, x -> instr(lower(pages.text), x) > 0)) AS words_matched,
           aggregate(words.w, 0, (n, x) -> n + size(split(lower(pages.text), x)) - 1) AS occurrences,
           greatest(instr(lower(pages.text), words.w[0]) - 120, 1) AS start_at
    FROM pages CROSS JOIN words
  )
  SELECT c.port_call_id, c.vessel_name, c.port_name, s.doc_type, s.file_item_id, s.page_number, s.words_matched,
         regexp_replace(regexp_replace(substr(regexp_replace(s.text, '\\s+', ' '), s.start_at, 400),
                        '[A-Z]{2}[0-9]{2}( ?[A-Z0-9]{4}){2,7}( ?[A-Z0-9]{1,4})?', '[account masked]'),
                        '[0-9][0-9 -]{7,}[0-9]', '[number masked]') AS snippet
  FROM scored s
  LEFT JOIN {catalog}.{gold_schema}.port_call_costs c ON c.proforma_id = s.proforma_id
  WHERE s.words_matched > 0 AND (port_call IS NULL OR c.port_call_id = port_call)
  ORDER BY s.words_matched DESC, s.occurrences DESC, c.port_call_id DESC, s.page_number
  LIMIT 10;
