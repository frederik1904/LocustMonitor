from collections.abc import Mapping
from contextlib import AbstractContextManager
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


def run_scenario(scenario: Scenario, client: HttpClient, row: Mapping[str, Any] | None = None) -> tuple[str, ...]:
    """Send the steps of the scenario once, in order, stopping at the first one that fails.

    `row` is this iteration's data row, shared by every step. Returns the names of the
    steps that were skipped because an earlier step failed.
    """
    extracted: dict[str, Any] = {}
    for index, step in enumerate(scenario.steps):
        endpoint = step.endpoint
        handler = HANDLERS[endpoint.meta.protocol]
        # Later sources win: the step's vars, then the data row, then values from earlier responses.
        context = step.vars | dict(row or {}) | extracted
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
            passed = _settle(handler, endpoint, response, context, extracted)
        if not passed:
            return tuple(later.name for later in scenario.steps[index + 1 :])
    return ()


def _settle(
    handler: ProtocolHandler,
    endpoint: Endpoint,
    response: CaughtResponse,
    context: Mapping[str, Any],
    extracted: dict[str, Any],
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
            failure = handler.check(endpoint, response, context)
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
