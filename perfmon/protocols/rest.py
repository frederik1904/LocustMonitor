import json
from collections.abc import Mapping
from functools import cache
from typing import Any

from jsonpath_ng import JSONPath
from jsonpath_ng.parser import parse

from perfmon.config.models import Endpoint
from perfmon.config.schema import BodyMatch
from perfmon.protocols.base import ExtractError, HttpResponse, PreparedRequest
from perfmon.protocols.json_compare import describe_differences
from perfmon.protocols.json_template import render_json
from perfmon.template import render, render_mapping

_JSON = "application/json"


class RestHandler:
    def lint(self, endpoint: Endpoint) -> list[str]:
        problems = []
        for expression in endpoint.meta.extract.values():
            try:
                _compile(expression)
            except ExtractError as error:
                problems.append(str(error))
        return problems

    def prepare(self, endpoint: Endpoint, context: Mapping[str, Any]) -> PreparedRequest:
        headers = render_mapping(endpoint.meta.headers, context)
        body = None
        if endpoint.request is not None:
            is_json = endpoint.request_content_type == _JSON
            text = render_json(endpoint.request, context) if is_json else render(endpoint.request, context)
            # Encoded here because requests would otherwise send a str body as latin-1.
            body = text.encode("utf-8")
            declared = {name.lower() for name in headers}
            if endpoint.request_content_type and "content-type" not in declared:
                headers["Content-Type"] = endpoint.request_content_type
        return PreparedRequest(
            method=endpoint.meta.method.value,
            path=render(endpoint.meta.path, context),
            query=render_mapping(endpoint.meta.query, context),
            headers=headers,
            body=body,
        )

    def check(self, endpoint: Endpoint, response: HttpResponse, context: Mapping[str, Any]) -> str | None:
        validation = endpoint.meta.validation
        if validation is None:
            return None
        if validation.status is not None and response.status_code != validation.status:
            return f"expected status {validation.status}, got {response.status_code}"
        if validation.body is BodyMatch.NONE or endpoint.response is None:
            return None
        try:
            # A null variable leaves its key out of the expectation, as it does in a request.
            expected = json.loads(render_json(endpoint.response, context))
        except ValueError as error:
            return f"body: the response file of '{endpoint.name}' is not valid JSON ({error})"
        try:
            actual = response.json()
        except ValueError:
            return "body: the response is not JSON"
        difference = describe_differences(expected, actual, exact=validation.body is BodyMatch.EXACT)
        return f"body: {difference}" if difference else None

    def extract(self, endpoint: Endpoint, response: HttpResponse) -> dict[str, Any]:
        try:
            document = response.json()
        except ValueError as error:
            raise ExtractError("extract: the response is not JSON") from error
        values = {}
        for name, expression in endpoint.meta.extract.items():
            matches = _compile(expression).find(document)
            if not matches:
                raise ExtractError(f"extract '{name}': {expression} matched nothing in the response")
            values[name] = matches[0].value
        return values


@cache
def _compile(expression: str) -> JSONPath:
    try:
        return parse(expression)
    except Exception as error:  # jsonpath-ng raises several unrelated types for bad syntax
        raise ExtractError(f"extract: invalid JSONPath '{expression}': {error}") from error
