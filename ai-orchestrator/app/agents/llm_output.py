"""Helpers for cleaning up what the LLM sends back.

LLMs often wrap answers in ``` fences or add a sentence before the JSON,
even when told not to. These helpers deal with that in one place.
"""

from __future__ import annotations

import ast
import json
import re

# A ``` block, with an optional language name after the opening fence.
_FENCED_BLOCK = re.compile(r"```[\w+-]*[ \t]*\n(.*?)```", re.DOTALL)


def strip_code_fences(text: str) -> str:
    """Return the inside of the first ``` block, or the whole text if there is none."""
    text = text.strip()
    match = _FENCED_BLOCK.search(text)
    return match.group(1).strip() if match else text


def parse_json_object(text: str) -> dict:
    """Parse the first {...} object in the text.

    Raises ValueError if there is no object or it is not valid JSON.
    """
    text = strip_code_fences(text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found in LLM reply: {text[:200]!r}")
    # strict=False lets raw newlines and tabs appear inside strings,
    # which LLMs often produce.
    data = json.loads(text[start : end + 1], strict=False)
    if not isinstance(data, dict):
        raise ValueError("LLM reply is JSON, but not an object.")
    return data


def is_valid_python(code: str) -> bool:
    try:
        ast.parse(code)
    except SyntaxError:
        return False
    return True
