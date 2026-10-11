"""Run scenarios under load with Locust, driven by a mode that decides how many users run and for how long."""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import gevent
from locust.env import Environment
from locust.runners import Runner
from locust.stats import RequestStats

from perfmon.config.models import Project, Scenario
from perfmon.runner import RunResult
from perfmon.users import build_user_classes

_STOP_TIMEOUT = 10  # seconds


@dataclass
class Iterations:
    """How the iterations of a scenario ended.

    An iteration is incomplete when one of its steps failed. The steps after it are never
    sent, so they appear in no request statistic and are counted here instead.
    """

    total: int = 0
    incomplete: int = 0
    steps_not_sent: int = 0
    setups_failed: int = 0  # virtual users that stopped because their setup failed

    def add(self, result: RunResult, is_setup: bool) -> None:
        if is_setup:
            self.setups_failed += not result.passed
            return
        self.total += 1
        self.incomplete += not result.passed
        self.steps_not_sent += len(result.skipped)

    @property
    def incomplete_percent(self) -> float:
        return 100 * self.incomplete / self.total if self.total else 0.0


@dataclass
class Window:
    """The requests and iterations completed since the previous window was taken."""

    response_times: list[float] = field(default_factory=list)
    failures: int = 0
    iterations: Iterations = field(default_factory=Iterations)

    @property
    def requests(self) -> int:
        return len(self.response_times)

    @property
    def error_percent(self) -> float:
        return 100 * self.failures / self.requests if self.requests else 0.0

    def percentile(self, fraction: float) -> float:
        ordered = sorted(self.response_times)
        return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)] if ordered else 0.0


class LoadControl:
    """What a mode can do to the running test."""

    def __init__(self, runner: Runner, scenario_count: int, say: Callable[[str], None]) -> None:
        self._runner = runner
        self._window = Window()
        self.iterations: dict[str, Iterations] = {}  # per scenario, over the whole run
        self.scenario_count = scenario_count
        self.say = say

    def record(self, response_time: float, exception: Any, **_: Any) -> None:
        self._window.response_times.append(response_time)
        self._window.failures += exception is not None

    def observe(self, scenario: Scenario, result: RunResult, is_setup: bool) -> None:
        self._window.iterations.add(result, is_setup)
        self.iterations.setdefault(scenario.name, Iterations()).add(result, is_setup)

    def set_users(self, total: int) -> None:
        """Raise the number of virtual users to total; the new ones start within about a second."""
        self._runner.start(total, spawn_rate=max(1, total - self._runner.user_count))

    def wait(self, seconds: float) -> None:
        gevent.sleep(seconds)

    def take_window(self) -> Window:
        window, self._window = self._window, Window()
        return window


class LoadMode(Protocol):
    """A way of applying load: how users are paced and how their number changes over the run."""

    pacing: float  # seconds between the starts of a user's iterations
    users_per_scenario: int | None  # pin every scenario to this many users instead of sharing them by weight
    failures_fail_the_run: bool
    check_bodies: bool  # compare response bodies as the endpoints' validate blocks ask, or judge on status alone

    def drive(self, load: LoadControl) -> list[str]:
        """Apply the load from start to finish; return the mode's own findings as lines of text."""
        ...


@dataclass(frozen=True)
class LoadReport:
    text: str
    requests: int
    failures: int


def run_load(
    project: Project,
    host: str,
    mode: LoadMode,
    only: list[str] | None = None,
    say: Callable[[str], None] = print,
) -> LoadReport:
    """Run the named scenarios (default: all) against host the way the mode prescribes."""
    # The user classes report to the control, which needs the runner, which needs the user classes.
    control: list[LoadControl] = []
    user_classes = build_user_classes(
        project,
        host=host,
        only=only,
        pacing=mode.pacing,
        users_per_scenario=mode.users_per_scenario,
        check_bodies=mode.check_bodies,
        observe=lambda scenario, result, is_setup: control[0].observe(scenario, result, is_setup),
    )
    # stop_timeout lets a user finish the iteration it is in, so a chain's clean-up steps still run.
    environment = Environment(user_classes=list(user_classes.values()), host=host, stop_timeout=_STOP_TIMEOUT)
    runner = environment.create_local_runner()
    load = LoadControl(runner, len(user_classes), say)
    control.append(load)
    environment.events.request.add_listener(load.record)
    try:
        findings = mode.drive(load)
    finally:
        runner.quit()
    stats = environment.stats
    text = "\n".join([*findings, "", format_stats(stats), "", format_iterations(load.iterations)]).strip()
    return LoadReport(text, stats.total.num_requests, stats.total.num_failures)


def _table(rows: list[tuple[str, ...]]) -> list[str]:
    """Rows as aligned text: the first column left-aligned, the numbers right-aligned."""
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    return [
        "  ".join(
            cell.ljust(width) if column == 0 else cell.rjust(width)
            for column, (cell, width) in enumerate(zip(row, widths, strict=True))
        )
        for row in rows
    ]


def format_stats(stats: RequestStats) -> str:
    """Requests, failures and response times per step, then the distinct failure messages."""
    rows: list[tuple[str, ...]] = [("Step", "Requests", "Failures", "p50 ms", "p95 ms", "p99 ms", "Avg ms", "Req/s")]
    for entry in sorted(stats.entries.values(), key=lambda entry: entry.name):
        rows.append(
            (
                f"{entry.method} {entry.name}",
                str(entry.num_requests),
                str(entry.num_failures),
                f"{entry.get_response_time_percentile(0.50):.0f}",
                f"{entry.get_response_time_percentile(0.95):.0f}",
                f"{entry.get_response_time_percentile(0.99):.0f}",
                f"{entry.avg_response_time:.0f}",
                f"{entry.total_rps:.1f}",
            )
        )
    lines = _table(rows)
    if stats.errors:
        lines += ["", "Failures:"]
        lines += [
            f"  {error.occurrences} x {error.method} {error.name}: {error.error}" for error in stats.errors.values()
        ]
    return "\n".join(lines)


def format_iterations(iterations: dict[str, Iterations]) -> str:
    """Per scenario: iterations run, how many stopped at a failed step, and the requests that were never sent."""
    rows: list[tuple[str, ...]] = [("Scenario", "Iterations", "Incomplete", "Incomplete %", "Steps not sent")]
    for name, count in sorted(iterations.items()):
        rows.append(
            (
                name,
                str(count.total),
                str(count.incomplete),
                f"{count.incomplete_percent:.1f}",
                str(count.steps_not_sent),
            )
        )
    lines = _table(rows)
    stopped = {name: count.setups_failed for name, count in sorted(iterations.items()) if count.setups_failed}
    lines += [f"{name}: {users} virtual user(s) stopped because their setup failed" for name, users in stopped.items()]
    return "\n".join(lines)
