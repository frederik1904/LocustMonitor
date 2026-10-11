from typing import Any

from perfmon.config.schema import LimitSettings, StopWhen
from perfmon.modes.load import LoadControl
from perfmon.reporting.summary import Measure


class Limit:
    """Load raised in steps until the API fails or slows down beyond the configured thresholds."""

    name = "limit"
    failures_fail_the_run = False  # failures are what this mode is looking for
    check_bodies = False  # only whether the API still answers matters here, and comparing costs CPU
    users_per_scenario: int | None = None

    def __init__(self, settings: LimitSettings) -> None:
        self._settings = settings
        self.pacing = settings.pacing

    def settings(self) -> dict[str, Any]:
        settings = self._settings
        stop_when = settings.stop_when
        return {
            "Users in the first step": settings.start_users,
            "Users added per step": settings.step_users,
            "Most users tried": settings.max_users,
            "Step duration (s)": settings.step_duration,
            "Pacing (s between iteration starts)": settings.pacing,
            "Stop when failed requests exceed (%)": stop_when.error_percent,
            "Stop when p95 exceeds (ms)": stop_when.p95_ms if stop_when.p95_ms is not None else "not set",
        }

    def drive(self, load: LoadControl) -> list[str]:
        settings = self._settings
        load.say(
            f"Limit: from {settings.start_users} to at most {settings.max_users} users in steps of "
            f"{settings.step_users}, {settings.step_duration:g} s per step"
        )
        healthy = 0
        users = settings.start_users
        while users <= settings.max_users:
            load.begin_step(users)
            load.wait(settings.step_duration)
            step = load.end_step()
            reason = _breach(step.total, settings.stop_when)
            step.verdict = reason or "healthy"
            load.say(
                f"  {users:>5} users: {step.requests_per_second:.1f} req/s, {step.total.failure_percent:.1f}% failed, "
                f"p50 {step.total.p50:.0f} / p95 {step.total.p95:.0f} / p99 {step.total.p99:.0f} ms, "
                f"{step.iterations.incomplete} of {step.iterations.total} iterations incomplete"
            )
            if reason:
                last = f"the last healthy step was {healthy} users" if healthy else "no step was healthy"
                return [f"Limit reached at {users} users: {reason}; {last}."]
            healthy = users
            users += settings.step_users
        return [f"No limit found: still healthy at {healthy} users, the highest step within max_users."]


def _breach(step: Measure, stop_when: StopWhen) -> str | None:
    """Why this step counts as over the limit, or None if it was healthy."""
    if step.requests == 0:
        return "no request completed during the step"
    if step.failure_percent > stop_when.error_percent:
        return f"{step.failure_percent:.1f}% of requests failed (threshold {stop_when.error_percent:g}%)"
    if stop_when.p95_ms is not None and step.p95 > stop_when.p95_ms:
        return f"p95 was {step.p95:.0f} ms (threshold {stop_when.p95_ms:g} ms)"
    return None
