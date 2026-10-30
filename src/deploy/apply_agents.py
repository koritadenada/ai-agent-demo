"""Creates what the bundle has no resource type for on the agent side, idempotently (safe on every setup run):

  1. the HAL-9000 tools as UC functions (src/agents/tools/*.sql): document search and port call timeline
  2. the tables the app writes to (src/agents/state.sql): analyst decisions, negotiation drafts, the agent registry
  3. the HAL-9000 supervisor agent (Agent Bricks): the three Genie agents from the bundle plus the two tools
  4. a row per agent in agent_registry, so the app finds the supervisor endpoint without a redeploy
  5. the app's service principal may read the app prompts (app schema); everything else in the app runs as the user
"""
import argparse
import inspect
import pathlib

from databricks.sdk import WorkspaceClient
from databricks.sdk.common.types.fieldmask import FieldMask
from databricks.sdk.service import supervisoragents as sa
from pyspark.sql import SparkSession

SRC = pathlib.Path(inspect.currentframe().f_code.co_filename).resolve().parent.parent

INSTRUCTIONS = """You are HAL-9000, the assistant of a port call cost team (DA analysts, operators, buyers).
Route every question to the tool that owns the data:
- port_costs: cost per call, final vs quote, benchmarks, potential savings, competing quotes, open quotes flagged above the benchmark.
- da_audit: final DA lines vs quote and invoice page, verdicts, the analyst's own checks, over-invoicing, bank detail checks, payments on hold, document reading quality.
- da_operations: appointments, cancellations, time from appointment to PDA, sailing to FDA and FDA to approval, statement of facts events.
- search_documents: what a PDF says (an invoice, a quote, a statement of facts), when the question is about the wording or content of a document.
- port_call_timeline: the ordered events of one port call when the user gives its port call id.
Rules:
- Answer only from tool results. If no tool has the answer, say so.
- Cite the evidence: port call id, document type and page number for anything read from a document.
- Amounts in EUR unless asked otherwise, 2 decimals. Bank account numbers are masked; never try to unmask them.
- You never change data. To accept, dispute or hold a DA, or to draft a negotiation email, point the user to the DA review or AI Negotiator screens."""

EXAMPLES = [
    ("Which ports are most expensive per call?", ["Use port_costs"]),
    ("Why is the payment for port call 20402 on hold?", ["Use da_audit", "Name the failing field and the masked accounts"]),
    ("How long do FDAs wait for approval in Valencia?", ["Use da_operations"]),
    ("What does the pilotage invoice of port call 20217 say?", ["Use search_documents", "Cite the page number"]),
    ("Give me the timeline of port call 20217", ["Use port_call_timeline"]),
]


def render(text: str, a) -> str:
    return (text.replace("{catalog}", a.catalog).replace("{gold_schema}", a.gold_schema)
                .replace("{silver_schema}", a.silver_schema).replace("{app_schema}", a.app_schema))


def apply_sql(spark, a):
    for f in [*sorted((SRC / "agents" / "tools").glob("*.sql")), SRC / "agents" / "state.sql"]:
        for statement in [s for s in render(f.read_text(), a).split(";\n") if s.strip()]:
            spark.sql(statement)
        print(f"applied {f.relative_to(SRC)}")


def supervisor(w: WorkspaceClient, a) -> sa.SupervisorAgent:
    """Find HAL-9000 by display name or create it; instructions, tools and examples always match this file."""
    agent = next((x for x in w.supervisor_agents.list_supervisor_agents() if x.display_name == a.name), None)
    spec = sa.SupervisorAgent(display_name=a.name, instructions=INSTRUCTIONS,
                              description="HAL-9000: questions about port call costs, DA audits, operations and documents")
    if agent is None:
        agent = w.supervisor_agents.create_supervisor_agent(spec)
        print(f"created supervisor {agent.name}")
    else:
        agent = w.supervisor_agents.update_supervisor_agent(agent.name, spec, update_mask=FieldMask(field_mask=["description", "instructions"]))
        print(f"updated supervisor {agent.name}")

    genie = {
        "port_costs": (a.port_costs_space, "Port call costs, final vs quote, benchmarks, savings, competing quotes, flagged open quotes"),
        "da_audit": (a.da_audit_space, "Final DA audit: lines vs quote and invoice page, verdicts, analyst checks, bank checks, payments on hold, document quality"),
        "da_operations": (a.da_operations_space, "DA workflow durations and counts, cancellations, statement of facts events"),
    }
    functions = {
        "search_documents": "Keyword search over the text of every port call PDF; returns pages with port call id, document type, page number and a snippet",
        "port_call_timeline": "Ordered events of one port call from its statement of facts, with the page of each event",
    }
    for t in list(w.supervisor_agents.list_tools(agent.name)):
        w.supervisor_agents.delete_tool(t.name)
    for tool_id, (space_id, description) in genie.items():
        w.supervisor_agents.create_tool(agent.name, sa.Tool(tool_type="genie_space", description=description,
                                                            genie_space=sa.GenieSpace(id=space_id)), tool_id)
    for tool_id, description in functions.items():
        w.supervisor_agents.create_tool(agent.name, sa.Tool(
            tool_type="uc_function", description=description,
            uc_function=sa.UcFunction(name=f"{a.catalog}.{a.gold_schema}.{tool_id}")), tool_id)
    for e in list(w.supervisor_agents.list_examples(agent.name)):
        w.supervisor_agents.delete_example(e.name)
    for question, guidelines in EXAMPLES:
        w.supervisor_agents.create_example(agent.name, sa.Example(question=question, guidelines=guidelines))
    print(f"tools: {[*genie, *functions]}, examples: {len(EXAMPLES)}")
    return agent


def main():
    ap = argparse.ArgumentParser()
    for name in ("catalog", "gold-schema", "silver-schema", "app-schema", "name", "app-service-principal",
                 "port-costs-space", "da-audit-space", "da-operations-space"):
        ap.add_argument(f"--{name}", required=True)
    a = ap.parse_args()
    spark = SparkSession.builder.getOrCreate()
    apply_sql(spark, a)
    agent = supervisor(WorkspaceClient(), a)
    rows = [("hal_9000", agent.endpoint_name, agent.name), ("port_costs", None, a.port_costs_space),
            ("da_audit", None, a.da_audit_space), ("da_operations", None, a.da_operations_space)]
    spark.createDataFrame(rows, "agent STRING, endpoint_name STRING, resource_id STRING").createOrReplaceTempView("r")
    spark.sql(f"""MERGE INTO {a.catalog}.{a.app_schema}.agent_registry t USING r ON t.agent = r.agent
                  WHEN MATCHED THEN UPDATE SET endpoint_name = r.endpoint_name, resource_id = r.resource_id,
                                               updated_at = current_timestamp()
                  WHEN NOT MATCHED THEN INSERT (agent, endpoint_name, resource_id, updated_at)
                                        VALUES (r.agent, r.endpoint_name, r.resource_id, current_timestamp())""")
    print(f"registered {agent.endpoint_name}")
    sp = f"`{a.app_service_principal}`"
    spark.sql(f"GRANT USE CATALOG ON CATALOG {a.catalog} TO {sp}")
    # the privileges the prompt registry asks for, on the app schema only
    spark.sql(f"GRANT USE SCHEMA, CREATE FUNCTION, EXECUTE, MANAGE ON SCHEMA {a.catalog}.{a.app_schema} TO {sp}")
    print(f"granted the app prompts to the app service principal {a.app_service_principal}")


if __name__ == "__main__":
    main()
