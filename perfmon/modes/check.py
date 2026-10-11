"""Functional check: run every scenario once, without load, and say what passed."""

from dataclasses import dataclass
from typing import Any

from locust.clients import HttpSession
from locust.event import EventHook

from perfmon.config.models import Project
from perfmon.data.pool import DataPool
from perfmon.runner import run_scenario, run_setup
from perfmon.template import TemplateError


@dataclass(frozen=True)
class StepOutcome:
    scenario: str
    request: str  # "GET http://host/path", or the endpoint that could not be built
    status: int | None
    elapsed_ms: float | None
    failure: str | None
    skipped: bool = False  # not sent because an earlier step of the scenario failed

    @property
    def passed(self) -> bool:
        return self.failure is None and not self.skipped


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
    pool = DataPool(project)
    for name in only or sorted(project.scenarios):
        current = name
        client = HttpSession(host, request_event, user=None)
        scenario = project.scenarios[name]
        try:
            setup = run_setup(scenario, client, pool.next_setup_row(scenario))
            skipped = list(setup.skipped)
            if setup.passed:
                skipped += run_scenario(scenario, client, pool.next_row(scenario), setup.values).skipped
            else:
                skipped += [step.name for step in scenario.steps]
        except TemplateError as error:
            outcomes.append(StepOutcome(name, "(request not sent)", None, None, str(error)))
            continue
        outcomes.extend(StepOutcome(name, step, None, None, None, skipped=True) for step in skipped)
    return outcomes


def format_report(outcomes: list[StepOutcome]) -> str:
    lines: list[str] = []
    scenario = None
    for outcome in outcomes:
        if outcome.scenario != scenario:
            scenario = outcome.scenario
            lines.append(scenario)
        if outcome.skipped:
            lines.append(f"  SKIP  {outcome.request}  (an earlier step failed)")
            continue
        verdict = "PASS" if outcome.passed else "FAIL"
        status = outcome.status if outcome.status is not None else "-"
        elapsed = f"{outcome.elapsed_ms:.0f} ms" if outcome.elapsed_ms is not None else "-"
        lines.append(f"  {verdict}  {outcome.request}  [{status}, {elapsed}]")
        if outcome.failure:
            lines.append(f"        {outcome.failure}")
    skipped = sum(outcome.skipped for outcome in outcomes)
    failed = sum(outcome.failure is not None for outcome in outcomes)
    lines.append("")
    lines.append(f"{len(outcomes) - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return "\n".join(lines)
