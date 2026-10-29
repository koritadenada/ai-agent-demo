"""Silver events: ai_query turns each statement of facts into an ordered timeline of port-call events."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import CATALOG, LLM_ENDPOINT, SILVER, json_literal, sql_str

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "sof_events",
        "strict": True,
        "schema": {
            "type": "object", "additionalProperties": False, "required": ["events"],
            "properties": {"events": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["event", "event_time"],
                "properties": {
                    "event": {"type": "string", "description": "Short event name, e.g. Pilot on board, All fast"},
                    "event_time": {"type": "string", "description": "ISO timestamp YYYY-MM-DDTHH:MM"},
                }}}},
        },
    },
}
PROMPT = "List every timed event in this statement of facts, in the order they happened. Text:\n"
EVENTS = "STRUCT<events: ARRAY<STRUCT<event: STRING, event_time: STRING>>>"


@dp.table(
    name=f"{CATALOG}.{SILVER}.port_call_events",
    comment="Timeline of each port call read from its statement of facts, one row per event",
    cluster_by=["proforma_id"],
)
def port_call_events():
    pages = (
        spark.readStream.table(f"{CATALOG}.{SILVER}.document_pages")
        .filter("doc_type = 'statement_of_facts' AND page_error IS NULL")
    )
    answer = F.expr(
        f"ai_query({sql_str(LLM_ENDPOINT)}, concat({sql_str(PROMPT)}, page_text), "
        f"responseFormat => {json_literal(RESPONSE_FORMAT)}, failOnError => false)"
    )
    return (
        pages.withColumn("answer", answer)
        .select("file_item_id", "proforma_id", "page_number",
                F.posexplode(F.from_json("answer.result", EVENTS).events).alias("event_order", "e"))
        .select("file_item_id", "proforma_id", "page_number", (F.col("event_order") + 1).alias("event_order"),
                F.col("e.event").alias("event"), F.expr("try_to_timestamp(e.event_time)").alias("event_time"))
    )
