"""What a load run produced, in plain data, so reporters need to know nothing about Locust.

Response times are kept as counts per rounded value, never as a list of samples, so the
memory a run needs does not grow with the number of requests.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from perfmon.config.schema import Targets
from perfmon.runner import RunResult


def _rounded(milliseconds: float) -> int:
    """Two to three significant digits: exact below 100 ms, to 10 ms below 1 s, to 100 ms below 10 s."""
    digits = 0 if milliseconds < 100 else -1 if milliseconds < 1000 else -2 if milliseconds < 10000 else -3
    return int(round(milliseconds, digits))


class ResponseTimes:
    """A set of durations in milliseconds that can report its percentiles."""

    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.minimum = 0.0
        self.maximum = 0.0
        self._counts: dict[int, int] = {}

    def add(self, milliseconds: float) -> None:
        self.minimum = milliseconds if self.count == 0 else min(self.minimum, milliseconds)
        self.maximum = max(self.maximum, milliseconds)
        self.count += 1
        self.total += milliseconds
        bucket = _rounded(milliseconds)
        self._counts[bucket] = self._counts.get(bucket, 0) + 1

    def merge(self, other: ResponseTimes) -> None:
        if other.count == 0:
            return
        self.minimum = other.minimum if self.count == 0 else min(self.minimum, other.minimum)
        self.maximum = max(self.maximum, other.maximum)
        self.count += other.count
        self.total += other.total
        for bucket, count in other._counts.items():
            self._counts[bucket] = self._counts.get(bucket, 0) + count

    @property
    def average(self) -> float:
        return self.total / self.count if self.count else 0.0

    def percentile(self, fraction: float) -> float:
        """The value that this fraction of the durations do not exceed, e.g. 0.95 for p95."""
        wanted = fraction * self.count
        seen = 0
        for bucket in sorted(self._counts):
            seen += self._counts[bucket]
            if seen >= wanted:
                return min(float(bucket), self.maximum)
        return 0.0


@dataclass
class Measure:
    """The requests of one step, or of everything, during one stretch of the run."""

    times: ResponseTimes = field(default_factory=ResponseTimes)
    failures: int = 0

    def record(self, milliseconds: float, failed: bool) -> None:
        self.times.add(milliseconds)
        self.failures += failed

    def merge(self, other: Measure) -> None:
        self.times.merge(other.times)
        self.failures += other.failures

    @property
    def requests(self) -> int:
        return self.times.count

    @property
    def failure_percent(self) -> float:
        return 100 * self.failures / self.requests if self.requests else 0.0

    @property
    def p50(self) -> float:
        return self.times.percentile(0.50)

    @property
    def p95(self) -> float:
        return self.times.percentile(0.95)

    @property
    def p99(self) -> float:
        return self.times.percentile(0.99)


@dataclass(frozen=True, order=True)
class StepKey:
    """One step of one scenario: what a line of the statistics is about."""

    scenario: str
    step: str
    method: str

    @property
    def label(self) -> str:
        return f"{self.method} {self.scenario}/{self.step}"


@dataclass
class FailureGroup:
    """Failures of one step that share a status code and message."""

    key: StepKey
    kind: str  # no response | unexpected status | body mismatch | extract failed
    status: int | None
    message: str
    occurrences: int
    first_seen_seconds: float  # into the run
    first_seen_users: int


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
    durations: ResponseTimes = field(default_factory=ResponseTimes)  # of the complete iterations, in ms

    def add(self, result: RunResult, is_setup: bool, seconds: float) -> None:
        if is_setup:
            self.setups_failed += not result.passed
            return
        self.total += 1
        self.incomplete += not result.passed
        self.steps_not_sent += len(result.skipped)
        if result.passed:
            self.durations.add(seconds * 1000)

    @property
    def incomplete_percent(self) -> float:
        return 100 * self.incomplete / self.total if self.total else 0.0


@dataclass
class Phase:
    """A stretch of the run held at one level of load. A baseline is a single phase; a limit run has one per step."""

    users: int
    started_seconds: float  # into the run
    intended_iterations_per_second: float | None  # what users and pacing ask for; None when unpaced
    duration_seconds: float = 0.0
    total: Measure = field(default_factory=Measure)
    steps: dict[StepKey, Measure] = field(default_factory=dict)
    iterations: Iterations = field(default_factory=Iterations)
    verdict: str = ""  # "healthy", or why this level counts as over the limit

    @property
    def requests_per_second(self) -> float:
        return self.total.requests / self.duration_seconds if self.duration_seconds else 0.0

    @property
    def iterations_per_second(self) -> float:
        return self.iterations.total / self.duration_seconds if self.duration_seconds else 0.0


@dataclass
class TimeSlice:
    """Everything that finished within a few seconds of the run, for charts over time."""

    start_seconds: float
    length_seconds: float
    users: int
    measure: Measure = field(default_factory=Measure)

    @property
    def requests_per_second(self) -> float:
        return self.measure.requests / self.length_seconds


def target_misses(measure: Measure, targets: Targets) -> list[str]:
    """Which of the targets these requests did not meet, each as a short phrase."""
    if measure.requests == 0:
        return []
    misses = []
    if targets.p95_ms is not None and measure.p95 > targets.p95_ms:
        misses.append(f"p95 {measure.p95:.0f} ms > {targets.p95_ms:g} ms")
    if targets.p99_ms is not None and measure.p99 > targets.p99_ms:
        misses.append(f"p99 {measure.p99:.0f} ms > {targets.p99_ms:g} ms")
    if targets.error_percent is not None and measure.failure_percent > targets.error_percent:
        misses.append(f"{measure.failure_percent:.1f}% failed > {targets.error_percent:g}%")
    return misses


@dataclass
class RunSummary:
    project: str
    mode: str
    host: str
    started: datetime
    duration_seconds: float
    settings: dict[str, Any]  # how the run was configured, label to value
    findings: list[str]  # what the run showed, as sentences
    steps: dict[StepKey, Measure]  # over the whole run
    targets: dict[StepKey, Targets]
    failures: list[FailureGroup]
    iterations: dict[str, Iterations]  # per scenario, over the whole run
    phases: list[Phase]
    timeline: list[TimeSlice]

    @property
    def requests(self) -> int:
        return sum(measure.requests for measure in self.steps.values())

    @property
    def failed_requests(self) -> int:
        return sum(measure.failures for measure in self.steps.values())

    @property
    def has_targets(self) -> bool:
        return any(targets != Targets() for targets in self.targets.values())

    def misses(self, key: StepKey, measure: Measure) -> list[str]:
        return target_misses(measure, self.targets.get(key, Targets()))

    def steps_missing_targets(self, steps: dict[StepKey, Measure] | None = None) -> dict[StepKey, list[str]]:
        """The steps that missed a target, over the whole run or within the given stretch of it."""
        chosen = self.steps if steps is None else steps
        found = {key: self.misses(key, measure) for key, measure in sorted(chosen.items())}
        return {key: misses for key, misses in found.items() if misses}

    def target_verdict(self, key: StepKey, measure: Measure) -> str:
        """ "met", "missed: ..." or "" when the step has no targets."""
        if self.targets.get(key, Targets()) == Targets():
            return ""
        misses = self.misses(key, measure)
        return f"missed: {'; '.join(misses)}" if misses else "met"
