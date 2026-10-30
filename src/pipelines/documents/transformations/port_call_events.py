"""Silver events: ai_query turns each statement of facts into an ordered timeline of port-call events.
One call per document, not per page, so a timeline that runs over several pages stays in one order. Each event keeps
the page it is printed on, for citations. Structured on purpose: Genie and the agents query the events; a narrative is written on demand, not stored.
The prompt and the model come from the prompt registry (sof_events)."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import AI_TABLE_PROPERTIES, CATALOG, SILVER, json_literal, prompt, sql_str

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "sof_events",
        "strict": True,
        "schema": {
            "type": "object", "additionalProperties": False, "required": ["events"],
            "properties": {"events": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["event", "event_time", "page_number"],
                "properties": {
                    "event": {"type": "string", "description": "Short event name, e.g. Pilot on board, All fast"},
                    "event_time": {"type": "string", "description": "ISO timestamp YYYY-MM-DDTHH:MM"},
                    "page_number": {"type": "integer", "description": "Page the event is printed on"},
                }}}},
        },
    },
}
PROMPT = prompt("sof_events")
EVENTS = "STRUCT<events: ARRAY<STRUCT<event: STRING, event_time: STRING, page_number: INT>>>"
# The whole document, with a marker before each page so the model can cite the page of every event
DOCUMENT_TEXT = ("array_join(transform(pages, p -> concat('--- Page ', p.page_number, ' ---\\n', p.extracted_text)), "
                 "'\\n\\n')")


@dp.table(
    name=f"{CATALOG}.{SILVER}.port_call_events",
    comment="Timeline of each port call read from its statement of facts, one row per event",
    cluster_by=["proforma_id"],
    table_properties=AI_TABLE_PROPERTIES,
)
def port_call_events():
    docs = (
        spark.readStream.table(f"{CATALOG}.{SILVER}.documents")
        .filter("doc_type = 'statement_of_facts' AND page_count > 0")
    )
    answer = F.expr(
        f"ai_query({sql_str(PROMPT.model)}, replace({sql_str(PROMPT.template)}, '{{{{document_text}}}}', "
        f"{DOCUMENT_TEXT}), responseFormat => {json_literal(RESPONSE_FORMAT)}, failOnError => false)"
    )
    return (
        docs.withColumn("answer", answer)
        .select("file_item_id", "proforma_id",
                F.posexplode(F.from_json("answer.result", EVENTS).events).alias("event_order", "e"))
        .select("file_item_id", "proforma_id", F.col("e.page_number").alias("page_number"),
                (F.col("event_order") + 1).alias("event_order"),
                F.col("e.event").alias("event"),
                # ISO as asked, or the date as printed (06 Oct 2026 11:29) when the model copies it
                F.expr("coalesce(try_to_timestamp(e.event_time), try_to_timestamp(e.event_time, 'd MMM yyyy HH:mm'))")
                .alias("event_time"),
                F.col("e.event_time").alias("event_time_text"),
                F.lit(PROMPT.version).alias("prompt_version"))
    )
