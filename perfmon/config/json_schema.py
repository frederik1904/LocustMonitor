"""JSON Schema for the YAML files, so editors can offer completion, hover docs and validation."""

import json
from pathlib import Path
from typing import Any

from perfmon.config.schema import EndpointFile, ProjectFile, ScenarioFile

ENDPOINT_SCHEMA = "endpoint.schema.json"
SCENARIO_SCHEMA = "scenario.schema.json"
PROJECT_SCHEMA = "project.schema.json"

_ENDPOINT_NAME = {"type": "string", "description": "Name of a folder under endpoints/."}
_CSV_PATH = {"type": "string", "description": "Path to a CSV file."}


def json_schemas() -> dict[str, dict[str, Any]]:
    scenario = ScenarioFile.model_json_schema()
    # The models only describe the long forms; the shorthands the loader also accepts are added here.
    setup = scenario["$defs"]["SetupFile"]["properties"]
    for owner in (scenario["properties"], setup):
        owner["steps"]["items"] = {"anyOf": [_ENDPOINT_NAME, owner["steps"]["items"]]}
        owner["data"]["anyOf"].insert(0, _CSV_PATH)
    scenario["properties"]["setup"]["anyOf"].insert(0, {"type": "array", "items": setup["steps"]["items"]})
    return {
        ENDPOINT_SCHEMA: EndpointFile.model_json_schema(),
        SCENARIO_SCHEMA: scenario,
        PROJECT_SCHEMA: ProjectFile.model_json_schema(),
    }


def write_json_schemas(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, schema in json_schemas().items():
        target = folder / name
        target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        written.append(target)
    return written
