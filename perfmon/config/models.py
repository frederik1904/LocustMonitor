"""What the rest of the program works with: files read and names resolved."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from perfmon.config.schema import ApiProtocol, HttpMethod, ValidationSpec


class ConfigError(Exception):
    """A problem in the endpoint/scenario files, always prefixed with the offending path."""


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str
    protocol: ApiProtocol
    method: HttpMethod
    headers: dict[str, str]
    extract: dict[str, str]
    validation: ValidationSpec | None
    standalone: bool
    request: str | None
    request_content_type: str | None
    response: str | None
    data: Path | None
    vars: dict[str, Any]


@dataclass(frozen=True)
class Step:
    endpoint: Endpoint
    vars: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    name: str
    steps: tuple[Step, ...]
    data: Path | None = None
    weight: int = 1


@dataclass(frozen=True)
class Project:
    endpoints: dict[str, Endpoint]
    scenarios: dict[str, Scenario]
