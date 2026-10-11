import logging
from collections.abc import Callable
from typing import Any

from locust import HttpUser, constant_pacing
from locust.exception import StopUser

from perfmon.config.models import Project, Scenario
from perfmon.data.pool import DataPool
from perfmon.runner import RunResult, run_scenario, run_setup

logger = logging.getLogger(__name__)

# Told about every finished setup (is_setup=True) and iteration of a scenario.
Observer = Callable[[Scenario, RunResult, bool], None]


def build_user_classes(
    project: Project,
    *,
    host: str | None = None,
    only: list[str] | None = None,
    pacing: float = 0,
    users_per_scenario: int | None = None,
    check_bodies: bool = True,
    observe: Observer | None = None,
) -> dict[str, type[HttpUser]]:
    """One Locust user class per scenario, named after it.

    `pacing` is the seconds between the starts of a user's iterations (0: back to back).
    `users_per_scenario` pins every scenario to that many users instead of sharing them by weight.
    With check_bodies=False responses are judged on status alone.
    `observe` is called with the result of every setup and iteration.
    """
    pool = DataPool(project)
    attributes: dict[str, Any] = {}
    if host or project.settings.host:
        attributes["host"] = host or project.settings.host
    if pacing:
        attributes["wait_time"] = constant_pacing(pacing)
    if users_per_scenario:
        attributes["fixed_count"] = users_per_scenario
    return {
        name: _user_class(project.scenarios[name], pool, attributes, check_bodies, observe)
        for name in only or project.scenarios
    }


def _user_class(
    scenario: Scenario, pool: DataPool, attributes: dict[str, Any], check_bodies: bool, observe: Observer | None
) -> type[HttpUser]:
    def on_start(user: Any) -> None:
        if not scenario.setup:
            return
        setup = run_setup(scenario, user.client, pool.next_setup_row(scenario), check_bodies=check_bodies)
        if observe:
            observe(scenario, setup, True)
        if not setup.passed:
            logger.warning("scenario '%s': setup failed, so this virtual user stops", scenario.name)
            raise StopUser()
        user.setup_values = setup.values

    def run(user: Any) -> None:
        result = run_scenario(
            scenario, user.client, pool.next_row(scenario), user.setup_values, check_bodies=check_bodies
        )
        if observe:
            observe(scenario, result, False)

    members = {"weight": scenario.weight, "tasks": [run], "on_start": on_start, "setup_values": {}}
    return type(scenario.name, (HttpUser,), members | attributes)
