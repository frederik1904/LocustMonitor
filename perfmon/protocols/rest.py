from collections.abc import Mapping
from typing import Any

from perfmon.config.models import Endpoint
from perfmon.protocols.base import HttpResponse, PreparedRequest
from perfmon.template import render, render_any


class RestHandler:
    def prepare(self, endpoint: Endpoint, context: Mapping[str, Any]) -> PreparedRequest:
        headers = render_any(endpoint.headers, context)
        body = None
        if endpoint.request is not None:
            # Encoded here because requests would otherwise send a str body as latin-1.
            body = render(endpoint.request, context).encode("utf-8")
            declared = {name.lower() for name in headers}
            if endpoint.request_content_type and "content-type" not in declared:
                headers["Content-Type"] = endpoint.request_content_type
        return PreparedRequest(
            method=endpoint.method.value,
            path=render(endpoint.path, context),
            headers=headers,
            body=body,
        )

    def check(self, endpoint: Endpoint, response: HttpResponse) -> str | None:
        expected = endpoint.validation.status if endpoint.validation else None
        if expected is not None and response.status_code != expected:
            return f"expected status {expected}, got {response.status_code}"
        return None
