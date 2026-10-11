from perfmon.config.schema import BaselineSettings
from perfmon.modes.load import LoadControl


class Baseline:
    """A steady, light load for a fixed time, to measure normal response times."""

    failures_fail_the_run = True
    check_bodies = True

    def __init__(self, settings: BaselineSettings) -> None:
        self._settings = settings
        self.pacing = settings.pacing
        self.users_per_scenario: int | None = settings.users

    def drive(self, load: LoadControl) -> list[str]:
        settings = self._settings
        load.say(
            f"Baseline: {settings.users} user(s) per scenario, {load.scenario_count} scenario(s), "
            f"for {settings.duration:g} s"
        )
        load.set_users(settings.users * load.scenario_count)
        load.wait(settings.duration)
        return []
