from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from perfmon.config.models import Endpoint


@dataclass(frozen=True)
class PreparedRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes | None


class HttpResponse(Protocol):
    """The part of an HTTP response the handlers read."""

    status_code: int


class ProtocolHandler(Protocol):
    """How one API style (REST, SOAP, GraphQL) builds requests and judges responses."""

    def prepare(self, endpoint: Endpoint, context: Mapping[str, Any]) -> PreparedRequest: ...

    def check(self, endpoint: Endpoint, response: HttpResponse) -> str | None:
        """Return why the response fails the endpoint's `validate` block, or None if it passes."""
        ...
