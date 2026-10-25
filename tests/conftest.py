import pytest

from src import config


@pytest.fixture(autouse=True)
def isolated_finalization_db(tmp_path_factory, monkeypatch):
    """Every test gets its own (initially absent) finalization database."""
    path = tmp_path_factory.mktemp("db") / "finalization.db"
    monkeypatch.setattr(config, "FINALIZATION_DB_PATH", str(path))
    return str(path)


@pytest.fixture(autouse=True)
def offline_safety_screen(monkeypatch):
    """Tests never reach the network through the safety screen's model layer."""
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    from src import injection_guard
    monkeypatch.setattr(injection_guard, "_screen_agent",
                        lambda: Agent(TestModel(custom_output_args={"suspicious": []}),
                                      output_type=injection_guard.InstructionScreen))
