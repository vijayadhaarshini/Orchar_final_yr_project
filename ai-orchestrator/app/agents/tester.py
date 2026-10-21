"""Tester agent: asks the LLM to write pytest tests, then runs them.

The tests run through app.utils.sandbox, which is the only place
in the app that runs AI-written code.
"""

from __future__ import annotations

import ast
import asyncio
import re
from textwrap import dedent

from app.schemas.core import TestResult
from app.services.llm import build_assistant_agent
from app.utils.sandbox import run_pytest

# The generated code is saved under this name, so tests must import it by this name.
MODULE_NAME = "module_under_test"

SYSTEM_PROMPT = (
    "You are a senior Python test engineer.\n"
    "You write thorough pytest unit tests. "
    "Return ONLY valid pytest code — no explanations, no Markdown, no code fences."
)

# The LLM often guesses the wrong module name. These patterns catch the usual guesses.
_WRONG_FROM_IMPORT = re.compile(
    r"^from\s+(your_module|app|main|module|solution|code|src\.?\w*)\s+import", re.MULTILINE
)
_WRONG_IMPORT = re.compile(r"^import\s+(your_module|app|main|module|solution|code)\s*$", re.MULTILINE)
_WRONG_PATCH_TARGET = re.compile(r'patch\((["\'])(?!' + MODULE_NAME + r'[."\'])([^"\']+)\1')
_APP_VARIABLE = re.compile(r"^(\w+)\s*=\s*(?:FastAPI|APIRouter)\s*\(", re.MULTILINE)


# ---------------------------------------------------------------------------
# Reading the generated code
# ---------------------------------------------------------------------------

def _async_function_names(code: str) -> set[str]:
    """Names of all `async def` functions in the code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # The code is broken, but we still want a best guess for the prompt.
        return set(re.findall(r"^async def (\w+)", code, re.MULTILINE))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}


def _is_fastapi_module(code: str) -> bool:
    return bool(
        re.search(r"\b(from|import)\s+fastapi\b", code)
        or "FastAPI()" in code
        or "APIRouter()" in code
    )


def _app_variable_name(code: str) -> str:
    """Name of the variable that holds the FastAPI app, for example `app`."""
    match = _APP_VARIABLE.search(code)
    return match.group(1) if match else "app"


# ---------------------------------------------------------------------------
# Fixing common LLM mistakes in the generated tests
# ---------------------------------------------------------------------------

def _fix_patch_target(match: re.Match) -> str:
    # patch("some.other.path.func") -> patch("module_under_test.func")
    quote, target = match.group(1), match.group(2)
    return f"patch({quote}{MODULE_NAME}.{target.split('.')[-1]}{quote}"


def _wrap_async_calls(tests: str, async_names: set[str]) -> str:
    """Turn `func(...)` into `asyncio.run(func(...))` for async functions."""
    fixed_lines: list[str] = []
    for line in tests.splitlines():
        if not line.lstrip().startswith(("def ", "async def ", "#")):
            for name in async_names:
                if f"asyncio.run({name}(" not in line:
                    line = re.sub(rf"(?<![\w.])({re.escape(name)}\([^)]*\))", r"asyncio.run(\1)", line)
        fixed_lines.append(line)

    fixed = "\n".join(fixed_lines)
    return fixed if "import asyncio" in fixed else f"import asyncio\n{fixed}"


def _sanitize_tests(tests: str, async_names: set[str], is_fastapi: bool) -> str:
    tests = re.sub(r"^```(?:python)?\s*", "", tests, flags=re.IGNORECASE)
    tests = re.sub(r"\s*```\s*$", "", tests).strip()

    tests = _WRONG_FROM_IMPORT.sub(f"from {MODULE_NAME} import", tests)
    tests = _WRONG_IMPORT.sub(f"import {MODULE_NAME}", tests)
    tests = _WRONG_PATCH_TARGET.sub(_fix_patch_target, tests)

    if is_fastapi:
        # FastAPI turns a ValueError into an HTTP error response,
        # so the test will never see a raw ValueError.
        tests = re.sub(r"pytest\.raises\(\s*ValueError\s*\)", "pytest.raises(Exception)", tests)
    elif async_names:
        tests = _wrap_async_calls(tests, async_names)

    return tests


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class TesterAgent:
    """Writes pytest tests for generated code and runs them."""

    def __init__(self) -> None:
        self._assistant = build_assistant_agent("tester_agent", SYSTEM_PROMPT)

    @staticmethod
    def _prompt_plain(code: str, feature_description: str, async_names: set[str]) -> str:
        async_note = ""
        if async_names:
            names = sorted(async_names)
            async_note = (
                f"\nASYNC FUNCTIONS in this module: {', '.join(names)}\n"
                f"Call them with asyncio.run(), e.g.: asyncio.run({names[0]}(...))\n"
                "Add 'import asyncio' at the top of your test file.\n"
            )

        return dedent(f"""
            Write pytest unit tests for the following Python module.

            STRICT RULES:
            1. The module is saved as '{MODULE_NAME}.py'. Import ONLY as:
                   from {MODULE_NAME} import <name>   OR   import {MODULE_NAME}
               Never use any other module name.
            2. mock.patch() target MUST start with '{MODULE_NAME}.' e.g.:
                   with patch('{MODULE_NAME}.some_function'):
            3. Only test behaviour explicitly visible in the code. Do NOT assume
               exceptions are raised unless you see an explicit `raise` for that case.
            {async_note}
            Feature description:
            {feature_description}

            Module code:
            {code}

            Return ONLY valid pytest code.
        """).strip()

    @staticmethod
    def _prompt_fastapi(code: str, feature_description: str, app_var: str) -> str:
        return dedent(f"""
            Write pytest integration tests for the following FastAPI application.

            STRICT RULES:
            1. The module is saved as '{MODULE_NAME}.py'. Import the app as:
                   from {MODULE_NAME} import {app_var}
            2. Use FastAPI's TestClient for ALL requests — never call route functions directly:
                   from fastapi.testclient import TestClient
                   client = TestClient({app_var})
                   response = client.get("/endpoint")
                   assert response.status_code == 200
            3. For error cases, check response.status_code (e.g. 400, 422) and response.json(),
               NOT pytest.raises(ValueError). FastAPI wraps Python exceptions as HTTP responses.
            4. mock.patch() target MUST be '{MODULE_NAME}.<function_name>'.
            5. Only test behaviour explicitly visible in the code.

            Feature description:
            {feature_description}

            Module code:
            {code}

            Return ONLY valid pytest code.
        """).strip()

    def _ask_llm_for_tests(self, prompt: str) -> str:
        reply = self._assistant.generate_reply(messages=[{"role": "user", "content": prompt}])
        return str(reply).strip()

    @staticmethod
    def _run_pytest_in_sandbox(code: str, tests: str) -> TestResult:
        # If the LLM forgot to import the module, add the import for it.
        if f"import {MODULE_NAME}" not in tests and f"from {MODULE_NAME}" not in tests:
            tests = f"from {MODULE_NAME} import *\n\n{tests}"

        result = run_pytest(code, tests, module_name=MODULE_NAME)
        return TestResult(
            status="pass" if result.passed else "fail",
            coverage=result.coverage,
            errors=None if result.passed else result.output,
        )

    async def run(self, code: str, feature_description: str) -> tuple[TestResult, str]:
        """Write tests for `code`, clean them up, and run them.

        Returns the result and the test code, so the tests can be shown to the user.
        """
        async_names = _async_function_names(code)
        is_fastapi = _is_fastapi_module(code)

        if is_fastapi:
            prompt = self._prompt_fastapi(code, feature_description, _app_variable_name(code))
        else:
            prompt = self._prompt_plain(code, feature_description, async_names)

        raw_tests = await asyncio.to_thread(self._ask_llm_for_tests, prompt)
        tests = _sanitize_tests(raw_tests, async_names, is_fastapi)
        result = await asyncio.to_thread(self._run_pytest_in_sandbox, code, tests)
        return result, tests


tester_agent = TesterAgent()
