from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from perfmon.config.models import Endpoint, Scenario, Step
from perfmon.protocols import HANDLERS
from perfmon.protocols.base import ExtractError, ProtocolHandler
from perfmon.template import TemplateError


class CaughtResponse(Protocol):
    """Locust's response when `catch_response=True`: the caller decides pass or fail."""

    status_code: int

    def json(self) -> Any: ...

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
        params: dict[str, str],
        headers: dict[str, str],
        data: bytes | None,
        catch_response: bool,
    ) -> AbstractContextManager[CaughtResponse]: ...


@dataclass(frozen=True)
class RunResult:
    passed: bool
    values: dict[str, Any]  # what the steps extracted
    skipped: tuple[str, ...]  # steps not sent because an earlier one failed


def run_setup(
    scenario: Scenario, client: HttpClient, row: Mapping[str, Any] | None = None, *, check_bodies: bool = True
) -> RunResult:
    """Run the scenario's setup steps once, for one virtual user.

    `row` is that user's setup data row. The result's values (the row plus what the steps
    extracted) are what the user brings to each of its iterations.
    """
    result = _run_steps(scenario, scenario.setup, client, dict(row or {}), check_bodies)
    return RunResult(result.passed, dict(row or {}) | result.values, result.skipped)


def run_scenario(
    scenario: Scenario,
    client: HttpClient,
    row: Mapping[str, Any] | None = None,
    user_values: Mapping[str, Any] | None = None,
    *,
    check_bodies: bool = True,
) -> RunResult:
    """Send the steps of the scenario once, in order, stopping at the first one that fails.

    `row` is this iteration's data row, shared by every step; `user_values` is what the
    virtual user's setup produced. With check_bodies=False responses are judged on status alone.
    """
    return _run_steps(scenario, scenario.steps, client, dict(user_values or {}) | dict(row or {}), check_bodies)


def _run_steps(
    scenario: Scenario, steps: tuple[Step, ...], client: HttpClient, given: dict[str, Any], check_bodies: bool
) -> RunResult:
    extracted: dict[str, Any] = {}
    for index, step in enumerate(steps):
        endpoint = step.endpoint
        handler = HANDLERS[endpoint.meta.protocol]
        # Later sources win: the step's vars, then setup values and the data row, then earlier responses.
        context = step.vars | given | extracted
        try:
            request = handler.prepare(endpoint, context)
        except TemplateError as error:
            raise TemplateError(f"step '{step.name}' in scenario '{scenario.name}': {error}") from error
        with client.request(
            request.method,
            request.path,
            name=_stats_name(scenario, step),
            params=request.query,
            headers=request.headers,
            data=request.body,
            catch_response=True,
        ) as response:
            passed = _settle(handler, endpoint, response, context, extracted, check_bodies)
        if not passed:
            return RunResult(False, extracted, tuple(later.name for later in steps[index + 1 :]))
    return RunResult(True, extracted, ())


def _settle(
    handler: ProtocolHandler,
    endpoint: Endpoint,
    response: CaughtResponse,
    context: Mapping[str, Any],
    extracted: dict[str, Any],
    check_bodies: bool,
) -> bool:
    """Mark the response passed or failed and collect its extracted values; True if it passed."""
    if response.status_code == 0:
        return False  # no response arrived; the client reports the connection error itself
    if endpoint.meta.validation is None:
        if response.status_code >= 400:
            return False  # the client's default rule reports it
        failure = None
    else:
        try:
            failure = handler.check(endpoint, response, context, check_body=check_bodies)
        except TemplateError as error:
            failure = f"response file of '{endpoint.name}': {error}"
    if failure is None and endpoint.meta.extract:
        try:
            extracted.update(handler.extract(endpoint, response))
        except ExtractError as error:
            failure = str(error)
    if failure is not None:
        response.failure(failure)
        return False
    response.success()
    return True


def _stats_name(scenario: Scenario, step: Step) -> str:
    # Prefixed with the scenario so the same endpoint in two scenarios is measured separately.
    return f"{scenario.name}/{step.name}"
