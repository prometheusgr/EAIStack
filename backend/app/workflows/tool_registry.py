"""Name -> tool-factory lookup for YAML-referenced tools.

A plain dict, not a dynamic loader — matching docs/AGENT_LIBRARY.md's own
stance on app.agents.registry ("a plain dict...with one real agent
registered today, there is nothing to auto-discover"). A YAML workflow
step can only reference a tool name present here; schema validation
(app.workflows.schema) checks membership against this dict at load time,
so a workflow definition can never reach an unregistered tool.

Every factory has the uniform signature (token: str, mcp_url: str) ->
StructuredTool, matching how app.mcp_client.doc_search_client already
binds tools to one caller's forwarded credentials per request — the
workflow engine reuses that same closure pattern rather than inventing a
new one.
"""

from typing import Callable

from langchain_core.tools import StructuredTool

from app.mcp_client import make_search_knowledge_base_tool

ToolFactory = Callable[[str, str], StructuredTool]

_TOOL_REGISTRY: dict[str, ToolFactory] = {
    "search_knowledge_base": make_search_knowledge_base_tool,
}


def get_tool_factory(name: str) -> ToolFactory | None:
    """Look up a registered tool factory by name, or None if unregistered."""
    return _TOOL_REGISTRY.get(name)


def is_registered_tool(name: str) -> bool:
    """Whether name is a known tool — used by schema validation to reject
    a workflow definition that references an unregistered tool.
    """
    return name in _TOOL_REGISTRY
