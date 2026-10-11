"""What the rest of the program works with: files read and names resolved."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from perfmon.config.schema import ApiProtocol, DataMode, HttpMethod, ValidationSpec


class ConfigError(Exception):
    """A problem in the endpoint/scenario files, always prefixed with the offending path."""


@dataclass(frozen=True)
class DataBinding:
    file: Path
    mode: DataMode = DataMode.SHARED
    seed: int | None = None


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str
    protocol: ApiProtocol
    method: HttpMethod
    query: dict[str, Any]
    headers: dict[str, str]
    extract: dict[str, str]
    validation: ValidationSpec | None
    request: str | None
    request_content_type: str | None
    response: str | None
    vars: dict[str, Any]


@dataclass(frozen=True)
class Step:
    name: str  # unique within the scenario
    endpoint: Endpoint
    vars: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    name: str
    steps: tuple[Step, ...]
    data: DataBinding | None = None
    weight: int = 1


@dataclass(frozen=True)
class Project:
    endpoints: dict[str, Endpoint]
    scenarios: dict[str, Scenario]
