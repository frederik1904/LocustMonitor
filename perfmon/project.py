"""Open a project folder: read it, then verify what can be verified before anything is sent."""

from pathlib import Path

from perfmon.config.loader import load_project
from perfmon.config.models import ConfigError, Endpoint, Project, Scenario
from perfmon.data.csv import csv_columns
from perfmon.protocols import HANDLERS
from perfmon.template import placeholders


def open_project(root: str | Path) -> Project:
    """Load the project and raise ConfigError listing every problem found in it."""
    project = load_project(root)
    problems = [
        f"endpoint '{endpoint.name}': {problem}"
        for endpoint in project.endpoints.values()
        for problem in HANDLERS[endpoint.protocol].lint(endpoint)
    ]
    for scenario in project.scenarios.values():
        problems.extend(_missing_values(scenario))
    if problems:
        raise ConfigError(f"{Path(root)}: " + "\n  ".join(problems))
    return project


def _missing_values(scenario: Scenario) -> list[str]:
    """Placeholders that no vars, data column or earlier extract will have a value for."""
    problems = []
    available = set(csv_columns(scenario.data.file)) if scenario.data else set()
    for step in scenario.steps:
        known = available | step.vars.keys()
        # A dotted name such as {{user.id}} is satisfied by a value called user.
        missing = sorted(name for name in _needed(step.endpoint) if name not in known and name.split(".")[0] not in known)
        if missing:
            names = ", ".join(f"{{{{{name}}}}}" for name in missing)
            problems.append(
                f"scenario '{scenario.name}', step '{step.name}': no vars, data column or earlier extract provides {names}"
            )
        available |= step.endpoint.extract.keys()
    return problems


def _needed(endpoint: Endpoint) -> set[str]:
    templates = [endpoint.path, endpoint.request or "", endpoint.response or ""]
    templates += [value for value in (*endpoint.query.values(), *endpoint.headers.values()) if isinstance(value, str)]
    return set().union(*(placeholders(template) for template in templates))
