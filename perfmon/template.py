import json
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

PLACEHOLDER = re.compile(r"\{\{\s*(\$?[\w.-]+)\s*\}\}")
_MISSING = object()

BUILTINS = {
    "$uuid": lambda: str(uuid.uuid4()),
    "$timestamp": lambda: int(time.time()),
    "$isotime": lambda: datetime.now(UTC).isoformat(),
}


_ENV = "$env."  # {{$env.NAME}} reads the environment variable NAME


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


def placeholders(template: str) -> set[str]:
    """The names a template needs values for (built-ins excluded)."""
    names = {match.group(1) for match in PLACEHOLDER.finditer(template)} - BUILTINS.keys()
    return {name for name in names if not name.startswith(_ENV)}


def environment_variables(template: str) -> set[str]:
    """The environment variables a template reads through {{$env.NAME}}."""
    names = {match.group(1) for match in PLACEHOLDER.finditer(template)}
    return {name.removeprefix(_ENV) for name in names if name.startswith(_ENV)}


def substitute(
    template: str,
    context: Mapping[str, Any],
    null_text: Callable[[re.Match[str]], str] | None,
    value_text: Callable[[re.Match[str], Any], str] | None = None,
) -> tuple[str, list[str]]:
    """Fill in the placeholders; return the text and the names that resolved to null."""
    missing: list[str] = []
    nulls: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in BUILTINS:
            value = BUILTINS[name]()
        elif name.startswith(_ENV):
            value = os.environ.get(name.removeprefix(_ENV), _MISSING)
        else:
            value = _lookup(name, context)
        if value is _MISSING:
            missing.append(name)
            return match.group(0)
        if value is None:
            nulls.append(name)
            return null_text(match) if null_text else ""
        return value_text(match, value) if value_text else to_text(value)

    result = PLACEHOLDER.sub(replace, template)
    if missing:
        raise TemplateError(f"no value for: {_names(missing)}")
    return result, nulls


def to_text(value: Any) -> str:
    # Non-string values are written as JSON (true, 1.5, ["a"]).
    return value if isinstance(value, str) else json.dumps(value)


def _names(names: list[str]) -> str:
    return ", ".join(sorted(set(names)))


def render(template: str, context: Mapping[str, Any]) -> str:
    """Substitute {{name}}, {{dotted.path}} and {{$builtin}} placeholders.

    Unlike Mustache nothing is escaped, and an unknown name is an error rather than
    an empty string. A null value is an error too: here there is nothing to leave out.
    """
    result, nulls = substitute(template, context, None)
    if nulls:
        raise TemplateError(
            f"{_names(nulls)} is null, which can only leave out a whole header, query parameter or JSON value"
        )
    return result


def render_optional(template: str, context: Mapping[str, Any]) -> str | None:
    """Like render, but a template that is exactly one null placeholder gives None (leave it out)."""
    whole = PLACEHOLDER.fullmatch(template.strip())
    if whole and whole.group(1) not in BUILTINS and _lookup(whole.group(1), context) is None:
        return None
    return render(template, context)


def render_mapping(mapping: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, str]:
    """Render header or query values, leaving out the entries that come out null."""
    rendered = {}
    for key, value in mapping.items():
        text = render_optional(value, context) if isinstance(value, str) else value
        if text is not None:
            rendered[key] = to_text(text)
    return rendered
