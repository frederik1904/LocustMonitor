"""Compare an expected JSON document with the one a response returned."""

import json
from collections.abc import Iterator
from typing import Any

_SHOWN = 3


def describe_differences(expected: Any, actual: Any, *, exact: bool) -> str | None:
    """Say where actual departs from expected, or None when it matches.

    With exact=False, actual may have more: extra object keys and extra items after
    the expected ones in a list are ignored.
    """
    found = list(_differences(expected, actual, exact, "$"))
    if not found:
        return None
    more = f" (and {len(found) - _SHOWN} more)" if len(found) > _SHOWN else ""
    return "; ".join(found[:_SHOWN]) + more


def _differences(expected: Any, actual: Any, exact: bool, path: str) -> Iterator[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            yield f"{path} expected an object, got {_show(actual)}"
            return
        for key, value in expected.items():
            if key not in actual:
                yield f"{path}.{key} is missing"
            else:
                yield from _differences(value, actual[key], exact, f"{path}.{key}")
        if exact:
            for key in sorted(actual.keys() - expected.keys()):
                yield f"{path}.{key} is not expected"
    elif isinstance(expected, list):
        if not isinstance(actual, list):
            yield f"{path} expected a list, got {_show(actual)}"
            return
        if exact and len(actual) != len(expected):
            yield f"{path} expected {len(expected)} items, got {len(actual)}"
        elif len(actual) < len(expected):
            yield f"{path} expected at least {len(expected)} items, got {len(actual)}"
        for index, (wanted, got) in enumerate(zip(expected, actual)):
            yield from _differences(wanted, got, exact, f"{path}[{index}]")
    # bool is checked separately because in Python True == 1.
    elif isinstance(expected, bool) != isinstance(actual, bool) or expected != actual:
        yield f"{path} expected {_show(expected)}, got {_show(actual)}"


def _show(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + "..."
