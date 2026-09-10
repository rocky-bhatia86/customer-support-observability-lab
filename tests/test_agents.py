import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import support_ai.agents.drafter as drafter_module
import support_ai.agents.orchestrator as orchestrator_agent_module
import support_ai.agents.quality_checker as checker_module
from support_ai.config import Config
from support_ai.llm_client import LLMResult
from support_ai.models import Ticket
from support_ai.workflow import WorkflowRunner


def _config(**overrides):
    defaults = dict(
        api_key="test-key",
        model_name="gpt-4o-mini",
        temperature=0.2,
        max_agent_iterations=5,
        checker_prompt_version="v1",
    )
    defaults.update(overrides)
    return Config(**defaults)


def test_workflow_resolves_on_first_accept(monkeypatch):
    monkeypatch.setattr(
        orchestrator_agent_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult("billing", 10, 2, "test-model"),
    )
    monkeypatch.setattr(
        drafter_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult("Here is your answer.", 50, 20, "test-model"),
    )
    monkeypatch.setattr(
        checker_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult(
            '{"verdict": "ACCEPT", "reason": "grounded and relevant"}', 30, 10, "test-model",
        ),
    )

    runner = WorkflowRunner(_config())
    result = runner.run(Ticket(id="T-1", text="I was charged twice."))

    assert result.status == "RESOLVED"
    assert result.iterations == 1
    assert result.final_response == "Here is your answer."
    assert result.total_prompt_tokens > 0


def test_workflow_escalates_after_max_iterations(monkeypatch):
    monkeypatch.setattr(
        orchestrator_agent_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult("billing", 10, 2, "test-model"),
    )
    monkeypatch.setattr(
        drafter_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult("A draft.", 50, 20, "test-model"),
    )
    monkeypatch.setattr(
        checker_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult(
            '{"verdict": "REJECT_AND_RETRIEVE", "reason": "not specific enough"}', 30, 10, "test-model",
        ),
    )

    runner = WorkflowRunner(_config(max_agent_iterations=3))
    result = runner.run(Ticket(id="T-2", text="Ambiguous ticket."))

    assert result.status == "ESCALATED_MAX_ITERATIONS"
    assert result.iterations == 3


def test_classify_parses_category_and_agent_plan(monkeypatch):
    monkeypatch.setattr(
        orchestrator_agent_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult(
            '{"category": "billing", "agents": ["account_data", "kb_retrieval"]}',
            10, 5, "test-model",
        ),
    )
    agent = orchestrator_agent_module.OrchestratorAgent(_config())
    category, agents, _ = agent.classify(Ticket(id="T-3", text="Was I charged twice?"))

    assert category == "billing"
    assert agents == ["account_data", "kb_retrieval"]


def test_classify_falls_back_to_defaults_on_unparseable_response(monkeypatch):
    monkeypatch.setattr(
        orchestrator_agent_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult("not json", 10, 5, "test-model"),
    )
    agent = orchestrator_agent_module.OrchestratorAgent(_config())
    category, agents, _ = agent.classify(Ticket(id="T-4", text="Whatever"))

    assert category == "how-to"
    assert agents == ["kb_retrieval"]


def test_workflow_only_runs_the_planned_specialist_agents(monkeypatch):
    monkeypatch.setattr(
        orchestrator_agent_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult(
            '{"category": "billing", "agents": ["account_data"]}', 10, 2, "test-model",
        ),
    )
    monkeypatch.setattr(
        drafter_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult("Here is your answer.", 50, 20, "test-model"),
    )
    monkeypatch.setattr(
        checker_module, "call_llm",
        lambda config, messages, temperature=None, version=None: LLMResult(
            '{"verdict": "ACCEPT", "reason": "grounded and relevant"}', 30, 10, "test-model",
        ),
    )

    runner = WorkflowRunner(_config())
    result = runner.run(Ticket(id="T-5", text="What's my current plan?", account_id="ACC-1001"))

    agents_used = {s.agent for s in result.steps}
    assert "account_data" in agents_used
    assert "kb_retrieval" not in agents_used
    assert "impact_diagnostics" not in agents_used
    assert "account_access" not in agents_used
