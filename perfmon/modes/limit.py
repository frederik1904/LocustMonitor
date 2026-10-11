from perfmon.config.schema import LimitSettings, StopWhen
from perfmon.modes.load import LoadControl, Window


class Limit:
    """Load raised in steps until the API fails or slows down beyond the configured thresholds."""

    failures_fail_the_run = False  # failures are what this mode is looking for
    check_bodies = False  # only whether the API still answers matters here, and comparing costs CPU
    users_per_scenario: int | None = None

    def __init__(self, settings: LimitSettings) -> None:
        self._settings = settings
        self.pacing = settings.pacing

    def drive(self, load: LoadControl) -> list[str]:
        settings = self._settings
        load.say(
            f"Limit: from {settings.start_users} to at most {settings.max_users} users in steps of "
            f"{settings.step_users}, {settings.step_duration:g} s per step"
        )
        healthy = 0
        users = settings.start_users
        while users <= settings.max_users:
            load.set_users(users)
            load.wait(settings.step_duration)
            window = load.take_window()
            iterations = window.iterations
            load.say(
                f"  {users:>5} users: {window.requests} requests, {window.error_percent:.1f}% failed, "
                f"p95 {window.percentile(0.95):.0f} ms, {iterations.incomplete} of {iterations.total} iterations "
                f"incomplete ({iterations.steps_not_sent} steps not sent)"
            )
            reason = _breach(window, settings.stop_when)
            if reason:
                last = f"the last healthy step was {healthy} users" if healthy else "no step was healthy"
                return [f"Limit reached at {users} users: {reason}; {last}."]
            healthy = users
            users += settings.step_users
        return [f"No limit found: still healthy at {healthy} users, the highest step within max_users."]


def _breach(window: Window, stop_when: StopWhen) -> str | None:
    """Why this step counts as over the limit, or None if it was healthy."""
    if window.requests == 0:
        return "no request completed during the step"
    if window.error_percent > stop_when.error_percent:
        return f"{window.error_percent:.1f}% of requests failed (threshold {stop_when.error_percent:g}%)"
    p95 = window.percentile(0.95)
    if stop_when.p95_ms is not None and p95 > stop_when.p95_ms:
        return f"p95 was {p95:.0f} ms (threshold {stop_when.p95_ms:g} ms)"
    return None
