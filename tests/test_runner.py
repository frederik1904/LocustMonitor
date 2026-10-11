from pathlib import Path

import pytest
from locust import HttpUser

from perfmon.config.loader import load_project
from perfmon.runner import run_scenario
from perfmon.template import TemplateError
from perfmon.users import build_user_classes


class FakeResponse:
    def __init__(self, status_code, verdicts):
        self.status_code = status_code
        self._verdicts = verdicts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def success(self):
        self._verdicts.append("success")

    def failure(self, exc):
        self._verdicts.append(exc)


class RecordingClient:
    def __init__(self, status_code=200):
        self.calls = []
        self.verdicts = []
        self.status_code = status_code

    def request(self, method, url, *, name, headers, data, catch_response):
        assert catch_response
        self.calls.append({"method": method, "url": url, "name": name, "headers": headers, "data": data})
        return FakeResponse(self.status_code, self.verdicts)


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
    write(tmp_path, "scenarios/flow.yaml", "weight: 4\nsteps:\n  - ping\n  - endpoint: create_order\n    vars: {qty: 2}\n")
    return tmp_path


def test_sends_each_step_rendered_and_in_order(project: Path):
    client = RecordingClient()
    run_scenario(load_project(project).scenarios["flow"], client)
    assert client.calls == [
        {"method": "GET", "url": "/ping", "name": "flow/ping", "headers": {}, "data": None},
        {
            "method": "POST",
            "url": "/customers/7/orders",
            "name": "flow/create_order",
            "headers": {"X-Tenant": "acme", "Content-Type": "application/json"},
            "data": '{"note": "blåbær", "qty": 2}'.encode(),
        },
    ]


def test_standalone_endpoint_reports_under_its_own_name(project: Path):
    client = RecordingClient()
    run_scenario(load_project(project).scenarios["ping"], client)
    assert client.calls[0]["name"] == "ping"


def test_explicit_content_type_is_kept(project: Path):
    write(project, "endpoints/ping/meta.yaml", "path: /ping\nmethod: PUT\nheaders: {content-type: text/plain}\n")
    write(project, "endpoints/ping/request.json", "{}")
    client = RecordingClient()
    run_scenario(load_project(project).scenarios["ping"], client)
    assert client.calls[0]["headers"] == {"content-type": "text/plain"}


def test_missing_variable_names_the_endpoint_and_scenario(project: Path):
    with pytest.raises(TemplateError, match="endpoint 'create_order' in scenario 'create_order': no value for: qty"):
        run_scenario(load_project(project).scenarios["create_order"], RecordingClient())


@pytest.mark.parametrize(
    ("meta", "status", "verdicts"),
    [
        ("path: /ping\n", 500, []),  # no validate block: left to the client's default rule
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


def test_one_user_class_per_scenario(project: Path):
    classes = build_user_classes(load_project(project))
    assert sorted(classes) == ["create_order", "flow", "ping"]
    assert all(issubclass(cls, HttpUser) and not cls.abstract for cls in classes.values())
    assert classes["flow"].weight == 4 and classes["flow"].__name__ == "flow"
