"""Workspace access for one request: as the signed-in user when deployed (on-behalf-of-user auth), so Unity Catalog
governs every query, model call and file read with the user's own permissions; as the CLI profile when run locally."""
import os
from dataclasses import dataclass
from decimal import Decimal

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState
from fastapi import Request

CATALOG = os.environ["CATALOG"]
GOLD = f"{CATALOG}.{os.environ['GOLD_SCHEMA']}"
SILVER = f"{CATALOG}.{os.environ['SILVER_SCHEMA']}"
APP = f"{CATALOG}.{os.environ['APP_SCHEMA']}"
WAREHOUSE_ID = os.environ["DATABRICKS_WAREHOUSE_ID"]


@dataclass
class Session:
    w: WorkspaceClient
    user: str

    def sql(self, statement: str, **params) -> list[dict]:
        """Run a statement on the warehouse; parameters are bound (:name), never formatted into the text."""
        items = [StatementParameterListItem(name=k, value=None if v is None else str(v), type=_type(v))
                 for k, v in params.items()]
        r = self.w.statement_execution.execute_statement(statement=statement, warehouse_id=WAREHOUSE_ID,
                                                         parameters=items, wait_timeout="50s")
        while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
            r = self.w.statement_execution.get_statement(r.statement_id)
        if r.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(r.status.error.message if r.status.error else str(r.status.state))
        if not r.manifest or not r.manifest.schema.columns:
            return []
        cols = [(c.name, c.type_name.value if c.type_name else "STRING") for c in r.manifest.schema.columns]
        rows = (r.result.data_array if r.result else None) or []
        return [{n: _cast(v, t) for (n, t), v in zip(cols, row)} for row in rows]


def _type(v) -> str:
    if isinstance(v, bool):
        return "BOOLEAN"
    if isinstance(v, int):
        return "BIGINT"
    if isinstance(v, (float, Decimal)):
        return "DOUBLE"
    return "STRING"


def _cast(v, t: str):
    if v is None:
        return None
    if t in ("INT", "LONG", "SHORT", "BYTE"):
        return int(v)
    if t in ("DOUBLE", "FLOAT", "DECIMAL"):
        return float(v)
    if t == "BOOLEAN":
        return v == "true"
    if t in ("ARRAY", "STRUCT", "MAP"):
        import json
        return json.loads(v)
    return v


def session(request: Request) -> Session:
    token = request.headers.get("x-forwarded-access-token")
    if token:
        host = os.environ["DATABRICKS_HOST"]
        w = WorkspaceClient(host=host if host.startswith("http") else f"https://{host}", token=token, auth_type="pat")
        return Session(w, request.headers.get("x-forwarded-email", "unknown"))
    w = WorkspaceClient(profile=os.environ.get("DATABRICKS_CONFIG_PROFILE"))  # local development
    return Session(w, w.current_user.me().user_name)


def app_client() -> WorkspaceClient:
    """The app's own service principal: only used to read prompts from the registry."""
    if os.environ.get("DATABRICKS_CLIENT_ID"):
        return WorkspaceClient()
    return WorkspaceClient(profile=os.environ.get("DATABRICKS_CONFIG_PROFILE"))
