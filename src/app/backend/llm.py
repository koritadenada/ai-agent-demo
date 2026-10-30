"""Model calls and prompts. Prompts come from the MLflow Prompt Registry (app schema) by alias, read as the app's
service principal, cached for a few minutes, with the repo default as the fallback."""
import json
import logging
import os
import time
from dataclasses import dataclass

from databricks.sdk import WorkspaceClient

from prompts import DEFAULTS

from .workspace import APP, app_client

log = logging.getLogger(__name__)
ALIAS = os.environ.get("PROMPT_ALIAS", "production")
DEFAULT_MODEL = os.environ.get("AGENT_LLM_ENDPOINT", "databricks-claude-sonnet-5-5")
_cache: dict[str, tuple[float, "Prompt"]] = {}


@dataclass(frozen=True)
class Prompt:
    template: str
    model: str
    version: str


def prompt(name: str) -> Prompt:
    hit = _cache.get(name)
    if hit and time.time() < hit[0]:
        return hit[1]
    default = DEFAULTS[name]
    try:
        v = app_client().api_client.do(
            "GET", f"/api/2.0/mlflow/unity-catalog/prompts/{APP}.{name}/versions/by-alias/{ALIAS}")
        tags = {t["key"]: t["value"] for t in v.get("tags", [])}
        template = v["template"]
        template = json.loads(template) if template.startswith('"') else template
        p = Prompt(template, tags.get("model") or default["model"] or DEFAULT_MODEL, f"{name}@{ALIAS} v{v['version']}")
        ttl = 300
    except Exception as e:  # registry not seeded or not readable: keep working with the repo default
        log.warning("prompt %s from repo default (%s)", name, str(e).split(". Config:")[0])
        p = Prompt(default["template"], default["model"] or DEFAULT_MODEL, f"{name}@repo-default")
        ttl = 30  # retry the registry soon
    _cache[name] = (time.time() + ttl, p)
    return p


def chat(w: WorkspaceClient, model: str, messages: list[dict], tools: list[dict] | None = None,
         max_tokens: int = 4000, effort: str | None = "low") -> dict:
    """One chat completion on a serving endpoint (OpenAI format, tools optional); returns the message. Reasoning
    blocks, when the model returns them, stay in the message so a tool loop can pass them back unchanged."""
    body = {"messages": messages, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    if effort:
        body["reasoning_effort"] = effort
    r = w.api_client.do("POST", f"/serving-endpoints/{model}/invocations", body=body)
    return r["choices"][0]["message"]


def text(message: dict) -> str:
    """The text of a message, without reasoning blocks."""
    c = message.get("content")
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return c or ""
