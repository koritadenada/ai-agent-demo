"""Silver evidence per expense line: which pages of the final DA pack support it, in the shape
{expense: {pages, confidence, explanation}}. Built from page_expense_map, no model call."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities.settings import CATALOG, SILVER


@dp.materialized_view(
    name=f"{CATALOG}.{SILVER}.expense_page_evidence",
    comment="Per DA expense line: the pages of the final DA pack that evidence it, the lowest confidence and the explanations",
)
def expense_page_evidence():
    return (
        spark.read.table(f"{CATALOG}.{SILVER}.page_expense_map")
        .filter("page_role = 'supporting_invoice' AND expense_evaluation_id IS NOT NULL")
        .groupBy("proforma_id", "file_item_id", "expense_evaluation_id", "expense_name", "expense_category")
        .agg(
            F.array_sort(F.collect_list("page_number")).alias("pages"),
            F.min("confidence").alias("confidence"),
            F.concat_ws(" ", F.collect_list("explanation")).alias("explanation"),
        )
    )
