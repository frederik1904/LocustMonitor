"""Open a project folder: read it, then verify what can be verified before anything is sent."""

import os
from pathlib import Path

from perfmon.config.loader import load_project
from perfmon.config.models import ConfigError, DataBinding, Endpoint, Project, Scenario, Step
from perfmon.data.csv import csv_columns
from perfmon.protocols import HANDLERS
from perfmon.template import environment_variables, placeholders


def open_project(root: str | Path) -> Project:
    """Load the project and raise ConfigError listing every problem found in it."""
    project = load_project(root)
    problems = [
        f"endpoint '{endpoint.name}': {problem}"
        for endpoint in project.endpoints.values()
        for problem in HANDLERS[endpoint.meta.protocol].lint(endpoint)
    ]
    for scenario in project.scenarios.values():
        problems.extend(_missing_values(scenario))
    problems.extend(_unset_environment_variables(project))
    if problems:
        raise ConfigError(f"{Path(root)}: " + "\n  ".join(problems))
    return project


def _missing_values(scenario: Scenario) -> list[str]:
    """Placeholders that no vars, data column or earlier extract will have a value for."""
    problems: list[str] = []
    # What the setup knows and extracts is there for every iteration.
    after_setup = _walk(scenario, scenario.setup, _columns(scenario.setup_data), problems)
    _walk(scenario, scenario.steps, after_setup | _columns(scenario.data), problems)
    return problems


def _walk(scenario: Scenario, steps: tuple[Step, ...], available: set[str], problems: list[str]) -> set[str]:
    """Check each step against the names available when it runs; return the names available afterwards."""
    available = set(available)
    for step in steps:
        known = available | step.vars.keys()
        # A dotted name such as {{user.id}} is satisfied by a value called user.
        missing = sorted(
            name for name in _needed(step.endpoint) if name not in known and name.split(".")[0] not in known
        )
        if missing:
            names = ", ".join(f"{{{{{name}}}}}" for name in missing)
            where = f"scenario '{scenario.name}', step '{step.name}'"
            problems.append(f"{where}: no vars, data column or earlier extract provides {names}")
        available |= step.endpoint.meta.extract.keys()
    return available


def _unset_environment_variables(project: Project) -> list[str]:
    used = {step.endpoint.name: step.endpoint for scenario in project.scenarios.values() for step in _steps(scenario)}
    problems = []
    for endpoint in used.values():
        for name in sorted(set().union(*(environment_variables(text) for text in _templates(endpoint)))):
            if name not in os.environ:
                problems.append(f"endpoint '{endpoint.name}': the environment variable {name} is not set")
    return problems


def _steps(scenario: Scenario) -> tuple[Step, ...]:
    return scenario.setup + scenario.steps


def _columns(data: DataBinding | None) -> set[str]:
    return set(csv_columns(data.file)) if data else set()


def _needed(endpoint: Endpoint) -> set[str]:
    return set().union(*(placeholders(template) for template in _templates(endpoint)))


def _templates(endpoint: Endpoint) -> list[str]:
    meta = endpoint.meta
    texts = [meta.path, endpoint.request or "", endpoint.response or ""]
    return texts + [value for value in (*meta.query.values(), *meta.headers.values()) if isinstance(value, str)]
