"""HAL-9000: forwards the conversation to the supervisor agent (Agent Bricks) as the signed-in user, so its Genie
agents and tools answer with the user's own permissions. The endpoint comes from agent_registry (setup job)."""
from .workspace import APP, Session

AGENT_NAMES = {"port_costs": "Port costs and benchmarks", "da_audit": "DA audit", "da_operations": "DA operations",
               "search_documents": "Document search", "port_call_timeline": "Port call timeline"}


def endpoint(s: Session) -> str:
    rows = s.sql(f"SELECT endpoint_name FROM {APP}.agent_registry WHERE agent = 'hal_9000'")
    if not rows or not rows[0]["endpoint_name"]:
        raise RuntimeError("HAL-9000 is not set up yet: run the setup job")
    return rows[0]["endpoint_name"]


def _text(item: dict) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content or [] if isinstance(c, dict))


def ask(s: Session, messages: list[dict]) -> dict:
    r = s.w.api_client.do("POST", f"/serving-endpoints/{endpoint(s)}/invocations",
                          body={"input": [{"role": m["role"], "content": m["content"]} for m in messages]})
    used, answer = [], ""
    for item in r.get("output", []):
        if item.get("type") == "function_call":
            name = item.get("name", "")
            key = next((k for k in AGENT_NAMES if k in name), name)
            label = AGENT_NAMES.get(key, name)
            if label not in used:
                used.append(label)
        elif item.get("type") == "message" and item.get("role", "assistant") == "assistant":
            answer = _text(item) or answer
    return {"answer": answer, "agents": used}
