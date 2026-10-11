from locust import HttpUser

from perfmon.config.models import Project, Scenario
from perfmon.runner import run_scenario


def build_user_classes(project: Project) -> dict[str, type[HttpUser]]:
    """One Locust user class per scenario, named after it so `locust <scenario>` selects it."""
    return {name: _user_class(scenario) for name, scenario in project.scenarios.items()}


def _user_class(scenario: Scenario) -> type[HttpUser]:
    def run(user: HttpUser) -> None:
        run_scenario(scenario, user.client)

    return type(scenario.name, (HttpUser,), {"weight": scenario.weight, "tasks": [run]})
