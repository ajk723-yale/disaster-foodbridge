"""The chat agent must have no way to finalize, approve, or write plans."""
import ast
from pathlib import Path

from src import agent, config

WRITE_NAMES = {"finalize_plan", "finalize_and_store", "add_commitments", "mark_dispatched", "mark_delivered",
               "cancel_commitments", "set_status", "connect"}


def test_agent_tools_are_read_only(monkeypatch):
    monkeypatch.setattr(config, "PORTKEY_API_KEY", "test-not-a-real-key")
    agent._agent.cache_clear()
    try:
        names = set(agent._agent()._function_toolset.tools)
    finally:
        agent._agent.cache_clear()
    assert names == {"get_shelter_reports", "get_warehouse_inventory", "calculate_shelter_needs",
                     "calculate_allocation", "prepare_supply_request"}
    assert not any("final" in n or "approve" in n or "dispatch" in n for n in names)


def test_agent_code_never_references_write_functions():
    for path in ("src/agent.py", "src/agent_tools.py", "src/drafts.py"):
        tree = ast.parse(Path(path).read_text())
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
               {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
               {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert not (used & WRITE_NAMES), f"{path} references {used & WRITE_NAMES}"


def test_instructions_send_staff_to_the_review_section():
    assert "cannot finalize" in agent.INSTRUCTIONS and "Review & finalize" in agent.INSTRUCTIONS
