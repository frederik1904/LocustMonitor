import json
import re
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*(\$?[\w.-]+)\s*\}\}")
_MISSING = object()
_OMIT = "__perfmon_omit__"

BUILTINS = {
    "$uuid": lambda: str(uuid.uuid4()),
    "$timestamp": lambda: int(time.time()),
    "$isotime": lambda: datetime.now(UTC).isoformat(),
}


class TemplateError(Exception):
    pass


def _lookup(name: str, context: Mapping[str, Any]) -> Any:
    if name in context:
        return context[name]
    value: Any = context
    for part in name.split("."):
        if isinstance(value, Mapping) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return _MISSING
    return value


def _substitute(
    template: str, context: Mapping[str, Any], null_text: Callable[[re.Match[str]], str] | None
) -> tuple[str, list[str]]:
    """Fill in the placeholders; return the text and the names that resolved to null."""
    missing: list[str] = []
    nulls: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = BUILTINS[name]() if name in BUILTINS else _lookup(name, context)
        if value is _MISSING:
            missing.append(name)
            return match.group(0)
        if value is None:
            nulls.append(name)
            return null_text(match) if null_text else ""
        return _to_text(value)

    result = _PLACEHOLDER.sub(replace, template)
    if missing:
        raise TemplateError(f"no value for: {_names(missing)}")
    return result, nulls


def _to_text(value: Any) -> str:
    # Non-string values are written as JSON (true, 1.5, ["a"]).
    return value if isinstance(value, str) else json.dumps(value)


def _names(names: list[str]) -> str:
    return ", ".join(sorted(set(names)))


def render(template: str, context: Mapping[str, Any]) -> str:
    """Substitute {{name}}, {{dotted.path}} and {{$builtin}} placeholders.

    Unlike Mustache nothing is escaped, and an unknown name is an error rather than
    an empty string. A null value is an error too: here there is nothing to leave out.
    """
    result, nulls = _substitute(template, context, None)
    if nulls:
        raise TemplateError(f"{_names(nulls)} is null, which can only leave out a whole header, query parameter or JSON value")
    return result


def render_optional(template: str, context: Mapping[str, Any]) -> str | None:
    """Like render, but a template that is exactly one null placeholder gives None (leave it out)."""
    whole = _PLACEHOLDER.fullmatch(template.strip())
    if whole and whole.group(1) not in BUILTINS and _lookup(whole.group(1), context) is None:
        return None
    return render(template, context)


def render_mapping(mapping: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, str]:
    """Render header or query values, leaving out the entries that come out null."""
    rendered = {}
    for key, value in mapping.items():
        text = render_optional(value, context) if isinstance(value, str) else value
        if text is not None:
            rendered[key] = _to_text(text)
    return rendered


def render_json(template: str, context: Mapping[str, Any]) -> str:
    """Render a JSON body; a key or list item whose whole value is a null placeholder is removed."""

    def null_text(match: re.Match[str]) -> str:
        quoted = template[match.start() - 1 : match.start()] == '"' and template[match.end() : match.end() + 1] == '"'
        return _OMIT if quoted else f'"{_OMIT}"'

    result, nulls = _substitute(template, context, null_text)
    if not nulls:
        return result
    problem = f"{_names(nulls)} is null, which can only leave out a whole JSON value"
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
