from pathlib import Path

import pytest

from perfmon.config.loader import load_project
from perfmon.config.models import ConfigError, DataBinding
from perfmon.config.schema import ApiProtocol, BodyMatch, DataMode, HttpMethod, ValidationSpec


def write(root: Path, relative: str, text: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    write(tmp_path, "data/users.csv", "username\nada\n")
    write(
        tmp_path,
        "endpoints/login/meta.yaml",
        "method: post\npath: /login\nextract: {token: $.token}\n",
    )
    write(tmp_path, "endpoints/login/request.json", '{"user": "{{username}}"}')
    write(
        tmp_path,
        "endpoints/create_order/meta.yaml",
        """
path: /orders
method: POST
vars: {quantity: 1, currency: EUR}
validate: {status: 201, body: subset}
""",
    )
    write(tmp_path, "endpoints/create_order/response.json", '{"id": 1}')
    write(
        tmp_path,
        "scenarios/order_flow.yaml",
        """
weight: 3
data: data/users.csv
vars: {currency: DKK}
steps:
  - login
  - endpoint: create_order
    vars: {quantity: 2}
""",
    )
    return tmp_path


def test_loads_endpoint_files(project: Path):
    endpoints = load_project(project).endpoints
    login, order = endpoints["login"], endpoints["create_order"]
    assert (login.method, login.path, login.protocol) == (HttpMethod.POST, "/login", ApiProtocol.REST)
    assert login.request == '{"user": "{{username}}"}' and login.response is None
    assert login.extract == {"token": "$.token"} and login.validation is None
    assert order.validation == ValidationSpec(status=201, body=BodyMatch.SUBSET)
    assert order.response == '{"id": 1}'


def test_only_scenario_files_produce_scenarios(project: Path):
    loaded = load_project(project)
    assert sorted(loaded.endpoints) == ["create_order", "login"]
    assert sorted(loaded.scenarios) == ["order_flow"]
    assert loaded.scenarios["order_flow"].data == DataBinding(project / "data/users.csv", DataMode.SHARED, None)


def test_step_vars_override_scenario_vars_override_endpoint_vars(project: Path):
    flow = load_project(project).scenarios["order_flow"]
    assert flow.weight == 3
    assert [step.endpoint.name for step in flow.steps] == ["login", "create_order"]
    assert flow.steps[1].vars == {"quantity": 2, "currency": "DKK"}


@pytest.mark.parametrize(
    ("relative", "text", "message"),
    [
        ("endpoints/bad/meta.yaml", "path: /x\nmethdo: GET\n", "methdo: unknown key"),
        ("endpoints/bad/meta.yaml", "method: GET\n", "path: Field required"),
        ("scenarios/bad.yaml", "steps: [login]\ndata: data/nope.csv\n", "data file 'data/nope.csv' not found"),
        ("endpoints/bad/meta.yaml", "path: /x\nvalidate: {body: fuzzy}\n", "validate.body: Input should be 'none', 'subset' or 'exact'"),
        ("scenarios/bad.yaml", "steps: [logn]\n", "unknown endpoint 'logn'"),
        ("scenarios/bad.yaml", "steps: [login]\ndata: {file: data/users.csv, mode: sorted}\n", "data.mode: Input should be 'shared', 'scenario' or 'random'"),
        ("scenarios/bad.yaml", "steps: [login]\ndata: {file: data/users.csv, seed: 1}\n", "seed only applies to mode: random"),
        ("scenarios/bad.yaml", "weight: 2\n", "steps: Field required"),
        ("scenarios/bad.yaml", "steps: []\n", "steps: List should have at least 1 item"),
        ("endpoints/bad/meta.yaml", "path: /x\nmethod: FETCH\n", "method: Input should be 'GET'"),
        ("endpoints/bad/meta.yaml", "path: /x\nprotocol: soap\n", "protocol: Input should be 'rest'"),
        ("endpoints/bad/meta.yaml", "path: /x\nvalidate: {staus: 200}\n", "validate.staus: unknown key"),
        ("endpoints/bad/meta.yaml", "path: /x\nstandalone: false\n", "standalone: unknown key"),
        ("endpoints/bad/meta.yaml", "path: /x\ndata: data/users.csv\n", "data: unknown key"),
    ],
)
def test_config_errors_name_the_file(project: Path, relative: str, text: str, message: str):
    write(project, relative, text)
    with pytest.raises(ConfigError, match=message) as error:
        load_project(project)
    assert str(project) in str(error.value)


def test_two_request_files_is_an_error(project: Path):
    write(project, "endpoints/login/request.xml", "<a/>")
    with pytest.raises(ConfigError, match="expected one request file"):
        load_project(project)


def test_data_long_form_and_query(project: Path):
    write(project, "scenarios/order_flow.yaml", "steps: [login]\ndata: {file: data/users.csv, mode: random, seed: 3}\n")
    write(project, "endpoints/search/meta.yaml", "path: /search\nquery: {q: '{{term}}', page: 2, debug: null}\n")
    loaded = load_project(project)
    assert loaded.scenarios["order_flow"].data == DataBinding(project / "data/users.csv", DataMode.RANDOM, 3)
    assert loaded.endpoints["search"].query == {"q": "{{term}}", "page": 2, "debug": None}
