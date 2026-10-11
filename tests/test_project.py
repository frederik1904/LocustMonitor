from pathlib import Path

import pytest

from perfmon.cli import main
from perfmon.config.models import ConfigError
from perfmon.project import open_project


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    write(tmp_path, "data/users.csv", "user,region\nada,eu\n")
    write(tmp_path, "endpoints/login/meta.yaml", "method: POST\npath: /login\nextract: {token: $.token, me: $.user}\n")
    write(tmp_path, "endpoints/login/request.json", '{"user": "{{user}}", "at": "{{$isotime}}"}')
    write(
        tmp_path,
        "endpoints/orders/meta.yaml",
        "path: /{{region}}/users/{{me.id}}/orders\nquery: {status: '{{status}}'}\n"
        "headers: {Authorization: 'Bearer {{token}}'}\nvalidate: {body: subset}\n",
    )
    write(tmp_path, "endpoints/orders/response.json", '{"owner": "{{user}}"}')
    write(tmp_path, "scenarios/flow.yaml", "data: data/users.csv\nvars: {status: open}\nsteps: [login, orders]\n")
    return tmp_path


def test_values_from_vars_data_columns_and_earlier_extracts_satisfy_placeholders(project: Path):
    assert sorted(open_project(project).scenarios) == ["flow"]


def test_every_missing_value_is_reported_with_its_step(project: Path):
    write(project, "scenarios/flow.yaml", "steps: [orders, login]\n")
    with pytest.raises(ConfigError) as error:
        open_project(project)
    message = str(error.value)
    assert (
        "scenario 'flow', step 'orders': no vars, data column or earlier extract provides "
        "{{me.id}}, {{region}}, {{status}}, {{token}}, {{user}}" in message
    )
    assert "scenario 'flow', step 'login': no vars, data column or earlier extract provides {{user}}" in message


def test_an_extract_only_helps_later_steps(project: Path):
    write(project, "endpoints/login/meta.yaml", "method: POST\npath: /login/{{token}}\nextract: {token: $.token, me: $.user}\n")
    with pytest.raises(ConfigError, match="step 'login': .* provides {{token}}"):
        open_project(project)


def test_invalid_jsonpath_is_found_before_anything_runs(project: Path):
    write(project, "endpoints/login/meta.yaml", "method: POST\npath: /login\nextract: {token: '$.[[', me: $.user}\n")
    with pytest.raises(ConfigError, match=r"endpoint 'login': extract: invalid JSONPath '\$\.\[\['"):
        open_project(project)


def test_the_command_line_refuses_a_project_with_problems(project: Path, capsys: pytest.CaptureFixture[str]):
    write(project, "scenarios/flow.yaml", "steps: [login]\n")
    assert main(["check", "--root", str(project), "--host", "http://127.0.0.1:9"]) == 2
    assert "provides {{user}}" in capsys.readouterr().err
