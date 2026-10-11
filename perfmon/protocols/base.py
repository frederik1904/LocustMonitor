from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from perfmon.config.models import Endpoint


@dataclass(frozen=True)
class PreparedRequest:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: bytes | None


class ExtractError(Exception):
    """A value named in an endpoint's `extract` block could not be read from the response."""


class HttpResponse(Protocol):
    """The part of an HTTP response the handlers read."""

    status_code: int

    def json(self) -> Any: ...


class ProtocolHandler(Protocol):
    """How one API style (REST, SOAP, GraphQL) builds requests and reads responses."""

    def lint(self, endpoint: Endpoint) -> list[str]:
        """Problems in the endpoint's definition that can be seen without sending anything."""
        ...

    def prepare(self, endpoint: Endpoint, context: Mapping[str, Any]) -> PreparedRequest: ...

    def check(
        self, endpoint: Endpoint, response: HttpResponse, context: Mapping[str, Any], *, check_body: bool
    ) -> str | None:
        """Return why the response fails the endpoint's `validate` block, or None if it passes.

        `context` is the one the request was built from, for placeholders in the expected response.
        With check_body=False only the status is judged.
        """
        ...

    def extract(self, endpoint: Endpoint, response: HttpResponse) -> dict[str, Any]:
        """Read the endpoint's `extract` values from the response; raise ExtractError if one is absent."""
        ...
