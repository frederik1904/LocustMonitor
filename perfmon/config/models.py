"""What the rest of the program works with: files read and names resolved."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from perfmon.config.schema import DataMode, EndpointFile, ProjectFile, Targets


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
    meta: EndpointFile  # everything written in meta.yaml
    request: str | None
    request_content_type: str | None
    response: str | None
    targets: Targets = field(default_factory=Targets)  # the endpoint's own, completed by the project's


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
    setup: tuple[Step, ...] = ()  # run once per virtual user, before its first iteration
    setup_data: DataBinding | None = None


@dataclass(frozen=True)
class Project:
    endpoints: dict[str, Endpoint]
    scenarios: dict[str, Scenario]
    settings: ProjectFile = field(default_factory=ProjectFile)  # project.yaml
    name: str = "project"  # the project folder's name, used to label reports
