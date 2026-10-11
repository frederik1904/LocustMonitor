import json
import re
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*(\$?[\w.-]+)\s*\}\}")
_MISSING = object()

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


def render(template: str, context: Mapping[str, Any]) -> str:
    """Substitute {{name}}, {{dotted.path}} and {{$builtin}} placeholders.

    Unlike Mustache nothing is escaped, and an unknown name is an error rather than
    an empty string. Non-string values are written as JSON (true, null, 1.5).
    """
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in BUILTINS:
            value = BUILTINS[name]()
        else:
            value = _lookup(name, context)
        if value is _MISSING:
            missing.append(name)
            return match.group(0)
        return value if isinstance(value, str) else json.dumps(value)

    result = _PLACEHOLDER.sub(replace, template)
    if missing:
        raise TemplateError(f"no value for: {', '.join(sorted(set(missing)))}")
    return result


def render_any(value: Any, context: Mapping[str, Any]) -> Any:
    """Render every string inside a nested dict/list structure."""
    if isinstance(value, str):
        return render(value, context)
    if isinstance(value, Mapping):
        return {key: render_any(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_any(item, context) for item in value]
    return value
