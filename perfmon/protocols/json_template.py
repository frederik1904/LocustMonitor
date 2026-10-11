"""Placeholder rendering that understands JSON: escaping inside strings and leaving out null values."""

import json
import re
from collections.abc import Mapping
from functools import cache
from typing import Any

from perfmon.template import PLACEHOLDER, TemplateError, substitute, to_text

_OMIT = "__perfmon_omit__"
_MISSING = object()


def render_json(template: str, context: Mapping[str, Any]) -> str:
    """Render a JSON document.

    A value placed inside a string is escaped, so quotes and line breaks in it stay valid JSON.
    A key or list item whose whole value is a null placeholder is removed.
    """
    in_string = _placeholders_inside_strings(template)

    def value_text(match: re.Match[str], value: Any) -> str:
        text = to_text(value)
        return json.dumps(text, ensure_ascii=False)[1:-1] if match.start() in in_string else text

    def null_text(match: re.Match[str]) -> str:
        quoted = template[match.start() - 1 : match.start()] == '"' and template[match.end() : match.end() + 1] == '"'
        return _OMIT if quoted else f'"{_OMIT}"'

    result, nulls = substitute(template, context, null_text, value_text)
    if not nulls:
        return result
    problem = f"{', '.join(sorted(set(nulls)))} is null, which can only leave out a whole JSON value"
    try:
        document = json.loads(result)
    except ValueError as error:
        raise TemplateError(f"{problem} ({error})") from error
    pruned = _prune(document)
    if pruned is _MISSING or _OMIT in json.dumps(pruned):
        raise TemplateError(problem)
    return json.dumps(pruned, ensure_ascii=False)


def _prune(value: Any) -> Any:
    if value == _OMIT:
        return _MISSING
    if isinstance(value, dict):
        return {key: kept for key, item in value.items() if (kept := _prune(item)) is not _MISSING}
    if isinstance(value, list):
        return [kept for item in value if (kept := _prune(item)) is not _MISSING]
    return value


@cache
def _placeholders_inside_strings(template: str) -> frozenset[int]:
    """Start offsets of the placeholders that sit inside a JSON string literal."""
    spans = {match.start(): match.end() for match in PLACEHOLDER.finditer(template)}
    found = set()
    inside = escaped = False
    position = 0
    while position < len(template):
        if position in spans:
            if inside:
                found.add(position)
            position = spans[position]
            continue
        character = template[position]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = inside
        elif character == '"':
            inside = not inside
        position += 1
    return frozenset(found)
