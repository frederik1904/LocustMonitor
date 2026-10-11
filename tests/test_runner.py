import json
from pathlib import Path

import pytest
from locust import HttpUser

from helpers import write
from perfmon.config.loader import load_project
from perfmon.runner import run_scenario, run_setup
from perfmon.template import TemplateError
from perfmon.users import build_user_classes


class FakeResponse:
    def __init__(self, status_code, body, verdicts):
        self.status_code = status_code
        self._body = body
        self._verdicts = verdicts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def json(self):
        if self._body is None:
            raise ValueError("not JSON")
        return self._body

    def success(self):
        self._verdicts.append("success")

    def failure(self, exc):
        self._verdicts.append(exc)


class RecordingClient:
    """Answers every request with status_code and the JSON body registered for its URL (default {})."""

    def __init__(self, status_code=200, bodies=None):
        self.calls = []
        self.verdicts = []
        self.status_code = status_code
        self.bodies = bodies or {}

    def request(self, method, url, *, name, params, headers, data, catch_response):
        assert catch_response
        self.calls.append(
            {"method": method, "url": url, "name": name, "params": params, "headers": headers, "data": data}
        )
        return FakeResponse(self.status_code, self.bodies.get(url, {}), self.verdicts)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    write(tmp_path, "endpoints/ping/meta.yaml", "path: /ping\n")
    write(
        tmp_path,
        "endpoints/create_order/meta.yaml",
        "method: post\npath: /customers/{{customer}}/orders\nheaders: {X-Tenant: '{{tenant}}'}\n"
        "vars: {customer: 7, tenant: acme, note: blåbær}\n",
    )
    write(tmp_path, "endpoints/create_order/request.json", '{"note": "{{note}}", "qty": {{qty}}}')
    write(
        tmp_path, "scenarios/flow.yaml", "weight: 4\nsteps:\n  - ping\n  - endpoint: create_order\n    vars: {qty: 2}\n"
    )
    write(tmp_path, "scenarios/ping.yaml", "steps: [ping]\n")
    write(tmp_path, "scenarios/order.yaml", "steps: [create_order]\n")
    return tmp_path


def test_sends_each_step_rendered_and_in_order(project: Path):
    client = RecordingClient()
    run_scenario(load_project(project).scenarios["flow"], client)
    assert client.calls == [
        {"method": "GET", "url": "/ping", "name": "flow/ping", "params": {}, "headers": {}, "data": None},
        {
            "method": "POST",
            "url": "/customers/7/orders",
            "name": "flow/create_order",
            "params": {},
            "headers": {"X-Tenant": "acme", "Content-Type": "application/json"},
            "data": '{"note": "blåbær", "qty": 2}'.encode(),
        },
    ]


def test_explicit_content_type_is_kept(project: Path):
    write(project, "endpoints/ping/meta.yaml", "path: /ping\nmethod: PUT\nheaders: {content-type: text/plain}\n")
    write(project, "endpoints/ping/request.json", "{}")
    client = RecordingClient()
    run_scenario(load_project(project).scenarios["ping"], client)
    assert client.calls[0]["headers"] == {"content-type": "text/plain"}


def test_missing_variable_names_the_endpoint_and_scenario(project: Path):
    with pytest.raises(TemplateError, match="step 'create_order' in scenario 'order': no value for: qty"):
        run_scenario(load_project(project).scenarios["order"], RecordingClient())


@pytest.mark.parametrize(
    ("meta", "status", "verdicts"),
    [
        ("path: /ping\n", 500, []),  # no validate block: left to the client's default rule
        ("path: /ping\n", 200, ["success"]),
        ("path: /ping\nvalidate: {status: 200}\n", 200, ["success"]),
        ("path: /ping\nvalidate: {status: 404}\n", 404, ["success"]),
        ("path: /ping\nvalidate: {status: 200}\n", 503, ["expected status 200, got 503"]),
        ("path: /ping\nvalidate: {status: 200}\n", 0, []),  # no response: the connection error is kept
    ],
)
def test_status_validation(project: Path, meta: str, status: int, verdicts: list[str]):
    write(project, "endpoints/ping/meta.yaml", meta)
    client = RecordingClient(status_code=status)
    run_scenario(load_project(project).scenarios["ping"], client)
    assert client.verdicts == verdicts


@pytest.mark.parametrize(
    ("mode", "expected", "variables", "actual", "verdict"),
    [
        (
            "subset",
            '{"id": {{id}}, "name": "{{name}}"}',
            "{id: 7, name: IPA}",
            {"id": 7, "name": "IPA", "x": 1},
            "success",
        ),
        ("subset", '{"id": {{id}}, "name": "{{name}}"}', "{id: 7, name: null}", {"id": 7, "name": "Stout"}, "success"),
        ("subset", '{"id": {{id}}}', "{id: 7}", {"id": 8}, "body: $.id expected 7, got 8"),
        ("exact", '{"id": {{id}}}', "{id: 7}", {"id": 7}, "success"),
        ("exact", '{"id": {{id}}}', "{id: 7}", {"id": 7, "x": 1}, "body: $.x is not expected"),
        ("none", '{"id": {{id}}}', "{id: 7}", {"id": 8}, "success"),
        ("subset", '{"id": {{id}}}', "{id: 7}", None, "body: the response is not JSON"),
        ("subset", '{"id": {{nope}}}', "{id: 7}", {"id": 7}, "response file of 'ping': no value for: nope"),
        ("subset", '{"id": ', "{id: 7}", {"id": 7}, "body: the response file of 'ping' is not valid JSON"),
    ],
)
def test_body_validation(project: Path, mode: str, expected: str, variables: str, actual, verdict: str):
    write(
        project,
        "endpoints/ping/meta.yaml",
        f"path: /ping\nvars: {variables}\nvalidate: {{status: 200, body: {mode}}}\n",
    )
    write(project, "endpoints/ping/response.json", expected)
    client = RecordingClient(bodies={"/ping": actual})
    run_scenario(load_project(project).scenarios["ping"], client)
    assert len(client.verdicts) == 1 and client.verdicts[0].startswith(verdict)


def test_bodies_can_be_left_unchecked_while_the_status_still_counts(project: Path):
    write(project, "endpoints/ping/meta.yaml", "path: /ping\nvalidate: {status: 200, body: exact}\n")
    write(project, "endpoints/ping/response.json", '{"id": 1}')
    scenario = load_project(project).scenarios["ping"]

    wrong_body = RecordingClient(bodies={"/ping": {"id": 2}})
    run_scenario(scenario, wrong_body, check_bodies=False)
    assert wrong_body.verdicts == ["success"]

    wrong_status = RecordingClient(status_code=500)
    run_scenario(scenario, wrong_status, check_bodies=False)
    assert wrong_status.verdicts == ["expected status 200, got 500"]


def test_status_is_checked_before_the_body(project: Path):
    write(project, "endpoints/ping/meta.yaml", "path: /ping\nvalidate: {status: 201, body: exact}\n")
    write(project, "endpoints/ping/response.json", "{}")
    client = RecordingClient(status_code=200)
    run_scenario(load_project(project).scenarios["ping"], client)
    assert client.verdicts == ["expected status 201, got 200"]


@pytest.fixture
def chain(tmp_path: Path) -> Path:
    write(
        tmp_path,
        "endpoints/login/meta.yaml",
        "method: POST\npath: /login\nextract: {token: $.auth.token, uid: '$.ids[0]'}\n",
    )
    write(tmp_path, "endpoints/login/request.json", '{"user": "{{user}}", "otp": {{otp}}}')
    write(
        tmp_path,
        "endpoints/orders/meta.yaml",
        "path: /users/{{uid}}/orders\nquery: {status: '{{status}}', limit: 5}\n"
        "headers: {Authorization: 'Bearer {{token}}', X-Trace: '{{trace}}'}\nvars: {status: open, trace: null, uid: 0}\n",
    )
    write(tmp_path, "scenarios/flow.yaml", "vars: {user: from-vars, otp: null}\nsteps: [login, orders]\n")
    return tmp_path


def test_values_flow_from_row_and_earlier_responses(chain: Path):
    client = RecordingClient(bodies={"/login": {"auth": {"token": "t0k"}, "ids": [42, 43]}})
    skipped = run_scenario(load_project(chain).scenarios["flow"], client, {"user": "from-row", "status": None})
    login, orders = client.calls
    assert skipped.skipped == () and skipped.passed and client.verdicts == ["success", "success"]
    assert json.loads(login["data"]) == {"user": "from-row"}  # the row beats vars; null otp is left out
    assert orders["url"] == "/users/42/orders"  # extracted uid beats the endpoint's own var
    assert orders["headers"] == {"Authorization": "Bearer t0k"}  # null X-Trace is not sent
    assert orders["params"] == {"limit": "5"}  # null status (from the row) is not sent


@pytest.mark.parametrize(
    ("status", "body", "verdict"),
    [
        (500, {}, None),
        (200, {"auth": {}}, "extract 'token': $.auth.token matched nothing in the response"),
        (200, None, "extract: the response is not JSON"),
    ],
)
def test_a_failed_step_stops_the_chain(chain: Path, status: int, body, verdict):
    client = RecordingClient(status_code=status, bodies={"/login": body})
    skipped = run_scenario(load_project(chain).scenarios["flow"], client, {})
    assert skipped.skipped == ("orders",) and not skipped.passed and len(client.calls) == 1
    assert client.verdicts == ([verdict] if verdict else [])


def test_setup_values_are_there_for_every_iteration(chain: Path):
    write(chain, "scenarios/flow.yaml", "vars: {user: from-vars, otp: null}\nsetup: [login]\nsteps: [orders]\n")
    scenario = load_project(chain).scenarios["flow"]
    client = RecordingClient(bodies={"/login": {"auth": {"token": "t0k"}, "ids": [42]}})

    setup = run_setup(scenario, client, {"user": "ada", "status": "new"})
    assert setup.passed and setup.values == {"user": "ada", "status": "new", "token": "t0k", "uid": 42}
    assert client.calls[0]["name"] == "flow/setup/login"

    for row in ({}, {"status": "paid"}):  # an iteration's own row beats the setup's
        run_scenario(scenario, client, row, setup.values)
    first, second = client.calls[1:]
    assert first["url"] == second["url"] == "/users/42/orders"
    assert (first["params"]["status"], second["params"]["status"]) == ("new", "paid")
    assert len(client.calls) == 3  # login was sent once


def test_a_failed_setup_reports_what_it_skipped(chain: Path):
    write(chain, "scenarios/flow.yaml", "vars: {user: u, otp: null}\nsetup: [login, login]\nsteps: [orders]\n")
    setup = run_setup(load_project(chain).scenarios["flow"], RecordingClient(status_code=500))
    assert not setup.passed and setup.skipped == ("setup/login#2",)


def test_invalid_jsonpath_is_a_failure(chain: Path):
    write(chain, "endpoints/login/meta.yaml", "method: POST\npath: /login\nextract: {token: '$.[['}\n")
    client = RecordingClient()
    run_scenario(load_project(chain).scenarios["flow"], client, {})
    assert client.verdicts[0].startswith("extract: invalid JSONPath '$.[['")


def test_one_user_class_per_scenario(project: Path):
    classes = build_user_classes(load_project(project))
    assert sorted(classes) == ["flow", "order", "ping"]
    assert all(issubclass(cls, HttpUser) and not cls.abstract for cls in classes.values())
    assert classes["flow"].weight == 4 and classes["flow"].__name__ == "flow"
