from pathlib import Path

import pytest

from helpers import write
from perfmon.config.loader import load_project
from perfmon.config.models import ConfigError, DataBinding
from perfmon.config.schema import (
    ApiProtocol,
    BodyMatch,
    DataMode,
    HttpMethod,
    ProjectFile,
    Targets,
    ValidationSpec,
)


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
    assert (login.meta.method, login.meta.path, login.meta.protocol) == (HttpMethod.POST, "/login", ApiProtocol.REST)
    assert login.request == '{"user": "{{username}}"}' and login.response is None
    assert login.meta.extract == {"token": "$.token"} and login.meta.validation is None
    assert order.meta.validation == ValidationSpec(status=201, body=BodyMatch.SUBSET)
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
        (
            "endpoints/bad/meta.yaml",
            "path: /x\nvalidate: {body: fuzzy}\n",
            "validate.body: Input should be 'none', 'subset' or 'exact'",
        ),
        ("scenarios/bad.yaml", "steps: [logn]\n", "unknown endpoint 'logn'"),
        (
            "scenarios/bad.yaml",
            "steps: [login]\ndata: {file: data/users.csv, mode: sorted}\n",
            "data.mode: Input should be 'shared', 'scenario' or 'random'",
        ),
        (
            "scenarios/bad.yaml",
            "steps: [login]\ndata: {file: data/users.csv, seed: 1}\n",
            "seed only applies to mode: random",
        ),
        ("scenarios/bad.yaml", "weight: 2\n", "steps: Field required"),
        (
            "endpoints/bad/meta.yaml",
            "path: /x\nvalidate: {body: exact}\n",
            "validate.body is 'exact' but the folder has no response file",
        ),
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
    assert loaded.endpoints["search"].meta.query == {"q": "{{term}}", "page": 2, "debug": None}


def test_steps_are_named_after_their_endpoint_and_numbered_when_repeated(project: Path):
    write(
        project,
        "scenarios/order_flow.yaml",
        "steps:\n  - login\n  - login\n  - {endpoint: login, name: again}\n  - login\n  - create_order\n",
    )
    steps = load_project(project).scenarios["order_flow"].steps
    assert [step.name for step in steps] == ["login", "login#2", "again", "login#3", "create_order"]


def test_two_steps_with_the_same_given_name(project: Path):
    write(
        project, "scenarios/order_flow.yaml", "steps:\n  - {endpoint: login, name: a}\n  - {endpoint: login, name: a}\n"
    )
    with pytest.raises(ConfigError, match="two steps are named 'a'"):
        load_project(project)


def test_yml_is_read_like_yaml(tmp_path: Path):
    write(tmp_path, "endpoints/ping/meta.yml", "path: /ping\n")
    write(tmp_path, "scenarios/flow.yml", "steps: [ping]\n")
    assert sorted(load_project(tmp_path).scenarios) == ["flow"]

    write(tmp_path, "scenarios/flow.yaml", "steps: [ping]\n")
    with pytest.raises(ConfigError, match="more than one scenario file named 'flow'"):
        load_project(tmp_path)


def test_meta_in_both_spellings(tmp_path: Path):
    write(tmp_path, "endpoints/ping/meta.yml", "path: /ping\n")
    write(tmp_path, "endpoints/ping/meta.yaml", "path: /ping\n")
    with pytest.raises(ConfigError, match="there is also a meta.yml"):
        load_project(tmp_path)


def test_a_project_without_scenarios_is_an_error(tmp_path: Path):
    write(tmp_path, "endpoints/ping/meta.yaml", "path: /ping\n")
    write(tmp_path, "scenarios/notes.txt", "not a scenario")
    with pytest.raises(ConfigError, match="no scenario files"):
        load_project(tmp_path)


def test_project_file_gives_host_modes_and_the_lowest_precedence_vars(project: Path):
    write(
        project,
        "project.yaml",
        "host: https://api.example.com\nvars: {tenant: acme, quantity: 99}\n"
        "modes:\n  baseline: {users: 2, duration: 5m, pacing: 0}\n  limit: {step_duration: 10s, stop_when: {p95_ms: 800}}\n",
    )
    loaded = load_project(project)
    assert loaded.settings.host == "https://api.example.com"
    assert (loaded.settings.modes.baseline.duration, loaded.settings.modes.baseline.users) == (300, 2)
    assert (loaded.settings.modes.limit.step_duration, loaded.settings.modes.limit.stop_when.p95_ms) == (10, 800)
    # project < endpoint < scenario < step
    assert loaded.scenarios["order_flow"].steps[1].vars == {"tenant": "acme", "quantity": 2, "currency": "DKK"}


def test_project_file_is_optional_and_checked(project: Path):
    loaded = load_project(project)
    assert loaded.settings == ProjectFile() and loaded.name == project.name
    write(project, "project.yaml", "name: shop\n")
    assert load_project(project).name == "shop"
    write(project, "project.yaml", "modes: {baseline: {duration: soon}}\n")
    with pytest.raises(ConfigError, match="project.yaml: modes.baseline.duration: .*such as 30s, 5m or 1h"):
        load_project(project)


def test_setup_as_a_list_or_with_its_own_data(project: Path):
    write(project, "scenarios/order_flow.yaml", "setup: [login, login]\nsteps: [login, create_order]\n")
    flow = load_project(project).scenarios["order_flow"]
    assert [step.name for step in flow.setup] == ["setup/login", "setup/login#2"]
    assert [step.name for step in flow.steps] == ["login", "create_order"] and flow.setup_data is None

    write(
        project, "scenarios/order_flow.yaml", "setup: {data: data/users.csv, steps: [login]}\nsteps: [create_order]\n"
    )
    flow = load_project(project).scenarios["order_flow"]
    assert flow.setup_data == DataBinding(project / "data/users.csv", DataMode.SHARED, None) and flow.data is None


def test_endpoint_targets_are_completed_by_the_project_targets(project: Path):
    write(project, "project.yaml", "targets: {p95_ms: 800, error_percent: 1}\n")
    write(project, "endpoints/login/meta.yaml", "method: post\npath: /login\ntargets: {p95_ms: 300, p99_ms: 900}\n")
    endpoints = load_project(project).endpoints
    assert endpoints["login"].targets == Targets(p95_ms=300, p99_ms=900, error_percent=1)
    assert endpoints["create_order"].targets == Targets(p95_ms=800, error_percent=1)
