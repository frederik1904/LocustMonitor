import json
from pathlib import Path

import pytest
import yaml

from perfmon.config.json_schema import ENDPOINT_SCHEMA, SCENARIO_SCHEMA, json_schemas

REPO = Path(__file__).parent.parent


@pytest.mark.parametrize("name", [ENDPOINT_SCHEMA, SCENARIO_SCHEMA])
def test_committed_schema_files_are_up_to_date(name: str):
    committed = json.loads((REPO / "schemas" / name).read_text())
    assert committed == json_schemas()[name], "run `uv run perfmon schema` to regenerate"


def test_schemas_describe_the_file_formats():
    endpoint, scenario = json_schemas()[ENDPOINT_SCHEMA], json_schemas()[SCENARIO_SCHEMA]
    assert endpoint["additionalProperties"] is False and endpoint["required"] == ["path"]
    assert "validate" in endpoint["properties"] and "validation" not in endpoint["properties"]
    assert {"type": "string"}.items() <= scenario["properties"]["steps"]["items"]["anyOf"][0].items()


def test_example_files_only_use_keys_the_schemas_know():
    schemas = json_schemas()
    for file in (REPO / "Example" / "endpoints").glob("*/meta.yaml"):
        assert set(yaml.safe_load(file.read_text())) <= set(schemas[ENDPOINT_SCHEMA]["properties"]), file
    for file in (REPO / "Example" / "scenarios").glob("*.yaml"):
        assert set(yaml.safe_load(file.read_text())) <= set(schemas[SCENARIO_SCHEMA]["properties"]), file
