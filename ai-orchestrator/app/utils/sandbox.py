"""Runs AI-written code and its tests in a separate Python process.

The code we run here comes from an LLM, so we do not trust it:
- it runs in a new temp folder that is deleted afterwards
- it does NOT get our environment variables (no API key, no DB password)
- it is stopped if it runs too long
- we never pip install anything it asks for. Missing packages are faked.

This is not a full sandbox. The code can still read files on this
machine and use the internet. For that level of safety, run it in Docker.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from app.config import settings
from app.utils.logging import log_structured

# Only these variables are passed to the test process.
# Windows needs SYSTEMROOT, or Python will not even start.
_SAFE_ENV_KEYS = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG")


@dataclass(frozen=True)
class SandboxResult:
    passed: bool
    coverage: float  # percent, 0-100
    output: str      # what pytest printed, useful when tests fail


def _safe_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _SAFE_ENV_KEYS if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def missing_modules(code: str) -> list[str]:
    """Names the code imports that are not installed here.

    find_spec only looks the name up. It does not run the package,
    so a bad name cannot do anything.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return sorted(name for name in names if find_spec(name) is None)


def run_pytest(
    code: str,
    tests: str,
    module_name: str = "module_under_test",
    timeout: int | None = None,
) -> SandboxResult:
    """Save the code and tests to a temp folder and run pytest on them."""
    timeout = timeout or settings.AGENT_TIMEOUT_SECONDS

    # Broken code fails right away. No need to start a process for it.
    try:
        fakes = missing_modules(code)
    except SyntaxError as exc:
        return SandboxResult(passed=False, coverage=0.0, output=f"SyntaxError in generated code: {exc}")

    with tempfile.TemporaryDirectory(prefix="ai_orchestrator_") as tmp:
        folder = Path(tmp)
        (folder / f"{module_name}.py").write_text(code, encoding="utf-8")
        (folder / f"test_{module_name}.py").write_text(tests, encoding="utf-8")

        # pytest loads conftest.py first, so the fake packages
        # are in place before the code tries to import them.
        if fakes:
            lines = ["import sys", "from unittest.mock import MagicMock"]
            lines += [f"sys.modules.setdefault({name!r}, MagicMock())" for name in fakes]
            (folder / "conftest.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

        command = [
            sys.executable, "-I", "-m", "pytest", f"test_{module_name}.py",
            "-q", "--tb=short", "--maxfail=5", "--disable-warnings", "-p", "no:cacheprovider",
            f"--cov={module_name}", "--cov-report=term-missing",
        ]
        try:
            done = subprocess.run(
                command, cwd=folder, env=_safe_env(),
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            log_structured("sandbox_timeout", timeout=timeout)
            message = f"Tests took longer than {timeout}s and were stopped."
            return SandboxResult(passed=False, coverage=0.0, output=message)

    output = f"{done.stdout}\n{done.stderr}".strip()
    # pytest-cov prints a line like "TOTAL   20   2   90%".
    match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
    result = SandboxResult(
        passed=done.returncode == 0,
        coverage=float(match.group(1)) if match else 0.0,
        output=output,
    )
    log_structured("sandbox_result", passed=result.passed, coverage=result.coverage, faked=fakes)
    return result
