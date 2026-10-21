"""Tests for agent modules – verifies parsing logic, syntax validation,
and sandbox execution without requiring a live LLM connection."""

from __future__ import annotations

import textwrap

import pytest

# ---------------------------------------------------------------------------
# Cleaning up LLM replies
# ---------------------------------------------------------------------------


class TestLlmOutput:
    def test_plain_json(self):
        from app.agents.llm_output import parse_json_object
        assert parse_json_object('{"tasks": []}') == {"tasks": []}

    def test_json_in_code_fence(self):
        from app.agents.llm_output import parse_json_object
        assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}

    def test_json_with_text_around_it(self):
        from app.agents.llm_output import parse_json_object
        assert parse_json_object('Here is the plan:\n{"a": 1}\nDone.') == {"a": 1}

    def test_raw_newline_inside_string_is_allowed(self):
        from app.agents.llm_output import parse_json_object
        assert parse_json_object('{"critique": "line one\nline two", "score": 6}')["score"] == 6

    def test_no_json_raises_value_error(self):
        from app.agents.llm_output import parse_json_object
        with pytest.raises(ValueError):
            parse_json_object("this is not JSON at all")

    def test_fence_after_a_sentence(self):
        from app.agents.llm_output import strip_code_fences
        assert strip_code_fences("Sure! Here you go:\n```python\nx = 1\n```") == "x = 1"

    def test_no_fence_returns_text(self):
        from app.agents.llm_output import strip_code_fences
        assert strip_code_fences("  x = 1  ") == "x = 1"

    def test_is_valid_python(self):
        from app.agents.llm_output import is_valid_python
        assert is_valid_python("def f(n: int) -> int:\n    return n")
        assert not is_valid_python("def broken(:\n    pass")


# ---------------------------------------------------------------------------
# Planner output schema
# ---------------------------------------------------------------------------


class TestPlannerTaskItem:
    def test_number_id_is_accepted(self):
        from app.schemas.core import PlannerTaskItem
        assert PlannerTaskItem(id=1, description="x").id == "1"

    @pytest.mark.parametrize(("given", "expected"), [("High", "high"), (" low ", "low"), ("urgent", "medium")])
    def test_priority_is_normalised(self, given, expected):
        from app.schemas.core import PlannerTaskItem
        assert PlannerTaskItem(id="t1", description="x", priority=given).priority == expected


# ---------------------------------------------------------------------------
# Developer and critic: bad LLM output must never replace good code
# ---------------------------------------------------------------------------


class TestDeveloperRevise:
    @pytest.mark.asyncio
    async def test_invalid_python_is_rejected(self, monkeypatch):
        from app.agents.developer import developer_agent
        monkeypatch.setattr(developer_agent, "_ask_llm", lambda prompt: "def broken(:")
        with pytest.raises(ValueError):
            await developer_agent.revise("def ok():\n    return 1", "add docs", "feature")

    @pytest.mark.asyncio
    async def test_valid_python_is_returned(self, monkeypatch):
        from app.agents.developer import developer_agent
        monkeypatch.setattr(developer_agent, "_ask_llm", lambda prompt: "def ok():\n    return 2")
        assert await developer_agent.revise("def ok():\n    return 1", "fix", "feature") == "def ok():\n    return 2"


class TestCritic:
    ORIGINAL = "def ok():\n    return 1"

    @pytest.mark.asyncio
    async def test_invalid_rewrite_keeps_original_code(self, monkeypatch):
        from app.agents.critic import critic_agent
        monkeypatch.setattr(critic_agent, "_ask_for_review", lambda code: '{"critique": "weak", "score": 3}')
        monkeypatch.setattr(critic_agent, "_ask_for_rewrite", lambda code, critique: "def broken(:")
        review = await critic_agent.critique_code(self.ORIGINAL)
        assert review["score"] == 3
        assert review["improved"] == self.ORIGINAL

    @pytest.mark.asyncio
    async def test_high_score_skips_rewrite(self, monkeypatch):
        from app.agents.critic import critic_agent
        monkeypatch.setattr(critic_agent, "_ask_for_review", lambda code: '{"critique": "good", "score": 9}')
        monkeypatch.setattr(critic_agent, "_ask_for_rewrite", lambda *a: pytest.fail("should not rewrite"))
        assert (await critic_agent.critique_code(self.ORIGINAL))["improved"] == self.ORIGINAL

    @pytest.mark.asyncio
    async def test_unreadable_review_raises(self, monkeypatch):
        from app.agents.critic import critic_agent
        monkeypatch.setattr(critic_agent, "_ask_for_review", lambda code: "Looks fine to me!")
        with pytest.raises(ValueError):
            await critic_agent.critique_code(self.ORIGINAL)


class TestOverseerPlan:
    def test_unknown_stages_and_checkpoints_are_dropped(self):
        from app.agents.overseer import overseer_agent
        plan = overseer_agent._parse_plan(
            '{"stages": ["planner", "deploy", "tester"], "checkpoints": ["after_deploy", "after_planner"]}'
        )
        assert plan["stages"] == ["planner", "tester"]
        assert plan["checkpoints"] == ["after_planner"]

    def test_bug_plan_does_not_test_before_there_is_code(self):
        from app.agents.overseer import overseer_agent
        assert overseer_agent._default_plan("bug")["stages"][0] == "developer"


# ---------------------------------------------------------------------------
# Tester Agent – sandbox execution tests
# ---------------------------------------------------------------------------


class TestSandboxExecution:
    """Test the sandboxed pytest runner."""

    @staticmethod
    def _run_sync(code: str, tests: str) -> dict:
        from app.agents.tester import TesterAgent
        return TesterAgent._run_pytest_in_sandbox(code, tests)

    def test_passing_tests(self):
        code = "def add(a, b):\n    return a + b"
        tests = textwrap.dedent("""
        from module_under_test import add

        def test_add_positive():
            assert add(2, 3) == 5

        def test_add_negative():
            assert add(-1, 1) == 0
        """).strip()
        result = self._run_sync(code, tests)
        assert result.status == "pass"

    def test_failing_tests(self):
        code = "def sub(a, b):\n    return a + b  # wrong"
        tests = textwrap.dedent("""
        from module_under_test import sub

        def test_sub():
            assert sub(5, 3) == 2
        """).strip()
        result = self._run_sync(code, tests)
        assert result.status == "fail"
        assert result.errors is not None

    def test_syntax_error_in_code(self):
        code = "def broken(:"
        tests = "def test_placeholder():\n    pass"
        result = self._run_sync(code, tests)
        assert result.status == "fail"


# ---------------------------------------------------------------------------
# Designer, sub-agent composer, message bus log
# ---------------------------------------------------------------------------


class TestDesigner:
    @pytest.mark.asyncio
    async def test_unreadable_reply_raises(self, monkeypatch):
        from app.agents.designer import designer_agent
        from app.schemas.core import PlannerOutput

        monkeypatch.setattr(designer_agent, "_ask_llm", lambda *args: "Sorry, I cannot do that.")
        with pytest.raises(ValueError):
            await designer_agent.run("feature", PlannerOutput(tasks=[]))

    @pytest.mark.asyncio
    async def test_non_text_fields_become_text(self, monkeypatch):
        from app.agents.designer import designer_agent
        from app.schemas.core import PlannerOutput

        reply = '{"architecture": "REST", "components": "API", "api_contracts": {"GET": "/fib/{n}"}}'
        monkeypatch.setattr(designer_agent, "_ask_llm", lambda *args: reply)
        design = await designer_agent.run("feature", PlannerOutput(tasks=[]))
        assert design.components == ["API"]
        assert design.api_contracts == '{"GET": "/fib/{n}"}'


class TestSubAgentCompose:
    @staticmethod
    def _agent(code: str):
        from app.agents.sub_agent_spawner import SpawnedSubAgent
        return SpawnedSubAgent(role="api", label="API Agent", task_description="t", code_output=code)

    @pytest.mark.asyncio
    async def test_invalid_merge_falls_back_to_joined_fragments(self, monkeypatch):
        from app.agents.sub_agent_spawner import sub_agent_spawner

        monkeypatch.setattr(sub_agent_spawner._composer, "generate_reply", lambda **kw: "def broken(:")
        merged = await sub_agent_spawner._compose([self._agent("a = 1"), self._agent("b = 2")], "feature")
        assert merged == "a = 1\n\nb = 2"

    @pytest.mark.asyncio
    async def test_nothing_valid_returns_empty(self, monkeypatch):
        from app.agents.sub_agent_spawner import sub_agent_spawner

        monkeypatch.setattr(sub_agent_spawner._composer, "generate_reply", lambda **kw: "def broken(:")
        assert await sub_agent_spawner._compose([self._agent("def also_broken(:")], "feature") == ""


class TestBusLog:
    @pytest.mark.asyncio
    async def test_messages_are_saved_and_read_back(self, tmp_path):
        from app.memory.agent_bus import AgentBus, load_bus_messages

        bus = AgentBus(project_id=1, run_id=7, log_dir=str(tmp_path))
        await bus.send("critic", "developer", "detailed_critique", {"score": 4})
        saved = load_bus_messages(str(tmp_path), 7)
        assert [(m["from_agent"], m["content"]) for m in saved] == [("critic", {"score": 4})]

    def test_missing_log_gives_empty_list(self, tmp_path):
        from app.memory.agent_bus import load_bus_messages
        assert load_bus_messages(str(tmp_path), 999) == []
