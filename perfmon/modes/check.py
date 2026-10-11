"""Functional check: run every scenario once, without load, and say what passed."""

from dataclasses import dataclass
from typing import Any

from locust.clients import HttpSession
from locust.event import EventHook

from perfmon.config.models import Project
from perfmon.runner import run_scenario
from perfmon.template import TemplateError


@dataclass(frozen=True)
class StepOutcome:
    scenario: str
    request: str  # "GET http://host/path", or the endpoint that could not be built
    status: int | None
    elapsed_ms: float | None
    failure: str | None

    @property
    def passed(self) -> bool:
        return self.failure is None


def check_project(project: Project, host: str, only: list[str] | None = None) -> list[StepOutcome]:
    """Run the named scenarios (default: all) once each against host."""
    outcomes: list[StepOutcome] = []
    current = ""

    def record(request_type: str, url: str, response_time: float, response: Any, exception: Any, **_: Any) -> None:
        outcomes.append(
            StepOutcome(
                scenario=current,
                request=f"{request_type} {url}",
                status=response.status_code or None,
                elapsed_ms=response_time,
                failure=str(exception) if exception else None,
            )
        )

    # The same session class Locust users get, so a check exercises exactly what a load test sends.
    request_event = EventHook()
    request_event.add_listener(record)
    for name in only or sorted(project.scenarios):
        current = name
        client = HttpSession(host, request_event, user=None)
        try:
            run_scenario(project.scenarios[name], client)
        except TemplateError as error:
            outcomes.append(StepOutcome(name, "(request not sent)", None, None, str(error)))
    return outcomes


def format_report(outcomes: list[StepOutcome]) -> str:
    lines: list[str] = []
    scenario = None
    for outcome in outcomes:
        if outcome.scenario != scenario:
            scenario = outcome.scenario
            lines.append(scenario)
        verdict = "PASS" if outcome.passed else "FAIL"
        status = outcome.status if outcome.status is not None else "-"
        elapsed = f"{outcome.elapsed_ms:.0f} ms" if outcome.elapsed_ms is not None else "-"
        lines.append(f"  {verdict}  {outcome.request}  [{status}, {elapsed}]")
        if outcome.failure:
            lines.append(f"        {outcome.failure}")
    failed = sum(not outcome.passed for outcome in outcomes)
    lines.append("")
    lines.append(f"{len(outcomes) - failed} passed, {failed} failed")
    return "\n".join(lines)
