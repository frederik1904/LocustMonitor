"""Run scenarios under load with Locust, driven by a mode that decides how many users run and for how long."""

import math
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

import gevent
from locust.env import Environment
from locust.runners import Runner

from perfmon.config.models import Project, Scenario
from perfmon.config.schema import Targets
from perfmon.reporting.base import Reporter, RequestSample
from perfmon.reporting.summary import FailureGroup, Iterations, Measure, Phase, RunSummary, StepKey, TimeSlice
from perfmon.runner import RunResult
from perfmon.users import build_user_classes

_STOP_TIMEOUT = 10  # seconds a stopping user gets to finish its iteration
_SLICE_SECONDS = 5  # resolution of the timeline while the run is going
_TIMELINE_POINTS = 120  # the timeline is thinned to at most this many points for the reports
_FAILURE_GROUPS = 200  # distinct failures kept apart; further ones are counted together


class LoadControl:
    """What a mode can do to the running test, and the place where its measurements are gathered."""

    def __init__(self, runner: Runner, scenario_count: int, pacing: float, say: Callable[[str], None]) -> None:
        self._runner = runner
        self._pacing = pacing
        self._clock = time.monotonic()
        self._phase: Phase | None = None
        self._slices: dict[int, TimeSlice] = {}
        self._failures: dict[tuple[Any, ...], FailureGroup] = {}
        self.steps: dict[StepKey, Measure] = {}
        self.iterations: dict[str, Iterations] = {}
        self.phases: list[Phase] = []
        self.scenario_count = scenario_count
        self.say = say

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._clock

    @property
    def failures(self) -> list[FailureGroup]:
        return sorted(self._failures.values(), key=lambda group: (group.key, -group.occurrences))

    # --- what a mode calls ---

    def begin_step(self, users: int) -> None:
        """Bring the number of virtual users to `users` (new ones start within about a second) and
        start measuring this level of load."""
        self._runner.start(users, spawn_rate=max(1, users - self._runner.user_count))
        intended = users / self._pacing if self._pacing else None
        self._phase = Phase(users=users, started_seconds=self.elapsed, intended_iterations_per_second=intended)

    def wait(self, seconds: float) -> None:
        gevent.sleep(seconds)

    def end_step(self, verdict: str = "") -> Phase:
        """Stop measuring this level of load and return what happened during it."""
        phase = self._phase
        if phase is None:
            raise RuntimeError("end_step() without begin_step()")
        phase.duration_seconds = self.elapsed - phase.started_seconds
        phase.verdict = verdict
        self.phases.append(phase)
        self._phase = None
        return phase

    # --- what the running test reports ---

    def record(
        self, request_type: str, name: str, response_time: float, response: Any, exception: Any, **_: Any
    ) -> None:
        key = StepKey(*_split(name), request_type)
        failed = exception is not None
        self.steps.setdefault(key, Measure()).record(response_time, failed)
        if self._phase:
            self._phase.total.record(response_time, failed)
            self._phase.steps.setdefault(key, Measure()).record(response_time, failed)
        index = int(self.elapsed // _SLICE_SECONDS)
        if index not in self._slices:
            self._slices[index] = TimeSlice(index * _SLICE_SECONDS, _SLICE_SECONDS, self._runner.user_count)
        self._slices[index].measure.record(response_time, failed)
        if failed:
            self._note_failure(key, getattr(response, "status_code", 0) or None, str(exception))

    def observe(self, scenario: Scenario, result: RunResult, is_setup: bool, seconds: float) -> None:
        self.iterations.setdefault(scenario.name, Iterations()).add(result, is_setup, seconds)
        if self._phase:
            self._phase.iterations.add(result, is_setup, seconds)

    def _note_failure(self, key: StepKey, status: int | None, message: str) -> None:
        group = (key, status, message)
        if group not in self._failures and len(self._failures) >= _FAILURE_GROUPS:
            group, status, message = (key, None, "other"), None, "(further distinct failures of this step)"
        if group in self._failures:
            self._failures[group].occurrences += 1
            return
        users = self._phase.users if self._phase else self._runner.user_count
        self._failures[group] = FailureGroup(key, _kind(status, message), status, message, 1, self.elapsed, users)

    def timeline(self) -> list[TimeSlice]:
        """The run in time order, thinned by merging neighbours so long runs stay chartable."""
        slices = [self._slices[index] for index in sorted(self._slices)]
        stride = math.ceil(len(slices) / _TIMELINE_POINTS)
        if stride <= 1:
            return slices
        merged = []
        for start in range(0, len(slices), stride):
            group = slices[start : start + stride]
            combined = TimeSlice(group[0].start_seconds, stride * _SLICE_SECONDS, max(piece.users for piece in group))
            for piece in group:
                combined.measure.merge(piece.measure)
            merged.append(combined)
        return merged


def _kind(status: int | None, message: str) -> str:
    """Sort a failure into a kind, from the status and the messages the runner writes."""
    if status is None:
        return "no response"
    if message.startswith("body:") or message.startswith("response file"):
        return "body mismatch"
    if message.startswith("extract"):
        return "extract failed"
    return "unexpected status"


class LoadMode(Protocol):
    """A way of applying load: how users are paced and how their number changes over the run."""

    name: str
    pacing: float  # seconds between the starts of a user's iterations
    users_per_scenario: int | None  # pin every scenario to this many users instead of sharing them by weight
    failures_fail_the_run: bool
    check_bodies: bool  # compare response bodies as the endpoints' validate blocks ask, or judge on status alone

    def settings(self) -> dict[str, Any]:
        """How the mode is configured, as label and value, for the reports."""
        ...

    def drive(self, load: LoadControl) -> list[str]:
        """Apply the load from start to finish; return what the mode concluded, as sentences."""
        ...


def run_load(
    project: Project,
    host: str,
    mode: LoadMode,
    only: list[str] | None = None,
    reporters: Sequence[Reporter] = (),
    say: Callable[[str], None] = print,
) -> RunSummary:
    """Run the named scenarios (default: all) against host the way the mode prescribes.

    Reporters see every request as it finishes; handing them the returned summary is up to the caller.
    """
    # The user classes report to the control, which needs the runner, which needs the user classes.
    control: list[LoadControl] = []
    user_classes = build_user_classes(
        project,
        host=host,
        only=only,
        pacing=mode.pacing,
        users_per_scenario=mode.users_per_scenario,
        check_bodies=mode.check_bodies,
        observe=lambda scenario, result, is_setup, seconds: control[0].observe(scenario, result, is_setup, seconds),
    )
    # stop_timeout lets a user finish the iteration it is in, so a chain's clean-up steps still run.
    environment = Environment(user_classes=list(user_classes.values()), host=host, stop_timeout=_STOP_TIMEOUT)
    runner = environment.create_local_runner()
    load = LoadControl(runner, len(user_classes), mode.pacing, say)
    control.append(load)
    environment.events.request.add_listener(load.record)
    if reporters:
        environment.events.request.add_listener(_streamer(reporters))

    started = datetime.now(UTC)
    try:
        findings = mode.drive(load)
    finally:
        runner.quit()

    scenarios = [project.scenarios[name] for name in user_classes]
    summary = RunSummary(
        project=project.name,
        mode=mode.name,
        host=host,
        started=started,
        duration_seconds=load.elapsed,
        settings=mode.settings()
        | {
            "Response bodies checked": "yes" if mode.check_bodies else "no, status codes only",
            "TLS certificates verified": "yes" if project.settings.verify_tls else "no (verify_tls: false)",
            "Scenarios": ", ".join(f"{scenario.name} (weight {scenario.weight})" for scenario in scenarios),
        },
        findings=findings,
        steps=dict(sorted(load.steps.items())),
        targets=_targets(scenarios),
        failures=load.failures,
        iterations=load.iterations,
        phases=load.phases,
        timeline=load.timeline(),
    )
    summary.findings.extend(_target_findings(summary))
    return summary


def run_failed(mode: LoadMode, summary: RunSummary) -> bool:
    """Whether the run should count as failed, for the command's exit code.

    Only for modes where failures are not the point: a missed target fails the run, and so does
    a failed request in a step that sets no failure target of its own to judge it by.
    """
    if not mode.failures_fail_the_run:
        return False
    if summary.steps_missing_targets():
        return True
    return any(
        measure.failures and summary.targets.get(key, Targets()).error_percent is None
        for key, measure in summary.steps.items()
    )


def _targets(scenarios: list[Scenario]) -> dict[StepKey, Targets]:
    return {
        StepKey(scenario.name, step.name, step.endpoint.meta.method.value): step.endpoint.targets
        for scenario in scenarios
        for step in scenario.setup + scenario.steps
    }


def _target_findings(summary: RunSummary) -> list[str]:
    """What the run says about the targets: over the whole run, and for a stepped run up to which load."""
    if not summary.has_targets:
        return []
    if len(summary.phases) > 1:
        met = 0
        for phase in summary.phases:
            if summary.steps_missing_targets(phase.steps):
                break
            met = phase.users
        highest = summary.phases[-1].users
        if met == highest:
            return [f"Every target was met at every level of load, up to {highest} users."]
        return [f"Every target was met up to {met} users." if met else "The targets were not met at any level of load."]
    missed = summary.steps_missing_targets()
    measured = sum(1 for key in summary.steps if summary.target_verdict(key, summary.steps[key]))
    if not missed:
        return [f"Every target was met ({measured} step(s) with targets)."]
    return [f"{len(missed)} of {measured} step(s) with targets missed them: " + ", ".join(key.label for key in missed)]


def _streamer(reporters: Sequence[Reporter]) -> Callable[..., None]:
    def on_request(request_type: str, name: str, response_time: float, exception: Any, **_: Any) -> None:
        scenario, step = _split(name)
        sample = RequestSample(scenario, step, request_type, response_time, str(exception) if exception else None)
        for reporter in reporters:
            reporter.on_request(sample)

    return on_request


def _split(stats_name: str) -> tuple[str, str]:
    """The runner labels requests "scenario/step"; a step's own name may contain further slashes."""
    scenario, _, step = stats_name.partition("/")
    return scenario, step
