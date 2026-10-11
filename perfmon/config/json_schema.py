"""JSON Schema for the YAML files, so editors can offer completion, hover docs and validation."""

import json
from pathlib import Path
from typing import Any

from perfmon.config.schema import EndpointFile, ScenarioFile

ENDPOINT_SCHEMA = "endpoint.schema.json"
SCENARIO_SCHEMA = "scenario.schema.json"


def json_schemas() -> dict[str, dict[str, Any]]:
    endpoint = EndpointFile.model_json_schema()
    scenario = ScenarioFile.model_json_schema()
    # The models only see the long forms; the shorthands accepted by the loader are added here.
    steps = scenario["properties"]["steps"]
    steps["items"] = {
        "anyOf": [{"type": "string", "description": "Name of a folder under endpoints/."}, steps["items"]]
    }
    scenario["properties"]["data"]["anyOf"].insert(0, {"type": "string", "description": "Path to a CSV file."})
    return {ENDPOINT_SCHEMA: endpoint, SCENARIO_SCHEMA: scenario}


def write_json_schemas(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, schema in json_schemas().items():
        target = folder / name
        target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        written.append(target)
    return written
