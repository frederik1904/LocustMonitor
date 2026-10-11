from contextlib import AbstractContextManager
from typing import Protocol

from perfmon.config.models import Scenario, Step
from perfmon.protocols import HANDLERS
from perfmon.template import TemplateError


class CaughtResponse(Protocol):
    """Locust's response when `catch_response=True`: the caller decides pass or fail."""

    status_code: int

    def success(self) -> None: ...

    def failure(self, exc: str) -> None: ...


class HttpClient(Protocol):
    """The part of Locust's HTTP session the runner needs; `name` is the label in the statistics."""

    def request(
        self,
        method: str,
        url: str,
        *,
        name: str,
        headers: dict[str, str],
        data: bytes | None,
        catch_response: bool,
    ) -> AbstractContextManager[CaughtResponse]: ...


def run_scenario(scenario: Scenario, client: HttpClient) -> None:
    """Send every step of the scenario once, in order."""
    for step in scenario.steps:
        endpoint = step.endpoint
        handler = HANDLERS[endpoint.protocol]
        try:
            request = handler.prepare(endpoint, step.vars)
        except TemplateError as error:
            raise TemplateError(f"endpoint '{endpoint.name}' in scenario '{scenario.name}': {error}") from error
        with client.request(
            request.method,
            request.path,
            name=_stats_name(scenario, step),
            headers=request.headers,
            data=request.body,
            catch_response=True,
        ) as response:
            # Without a `validate` block, or when no response arrived (status 0), the client's
            # own rule applies: connection errors and HTTP status >= 400 are failures.
            if endpoint.validation is not None and response.status_code != 0:
                failure = handler.check(endpoint, response)
                if failure:
                    response.failure(failure)
                else:
                    response.success()


def _stats_name(scenario: Scenario, step: Step) -> str:
    # A standalone endpoint reports under its own name; inside a chain it is
    # "scenario/endpoint" so the same endpoint in two scenarios is measured separately.
    if scenario.name == step.endpoint.name:
        return step.endpoint.name
    return f"{scenario.name}/{step.endpoint.name}"
