import mimetypes
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from perfmon.config.models import ConfigError, Endpoint, Project, Scenario, Step
from perfmon.config.schema import EndpointFile, ScenarioFile


def load_project(root: str | Path) -> Project:
    """Read endpoints/ and scenarios/ under root.

    Endpoints marked standalone (the default) also become a one-step scenario of
    the same name.
    """
    root = Path(root)
    endpoint_dir = root / "endpoints"
    if not endpoint_dir.is_dir():
        raise ConfigError(f"{endpoint_dir}: directory not found")

    endpoints = {
        folder.name: _load_endpoint(folder, root)
        for folder in sorted(endpoint_dir.iterdir())
        if folder.is_dir()
    }

    scenarios: dict[str, Scenario] = {}
    for file in sorted((root / "scenarios").glob("*.yaml")):
        scenarios[file.stem] = _load_scenario(file, root, endpoints)

    for endpoint in endpoints.values():
        if not endpoint.standalone:
            continue
        if endpoint.name in scenarios:
            raise ConfigError(
                f"{root / 'scenarios' / (endpoint.name + '.yaml')}: has the same name as a "
                f"standalone endpoint; rename it or set 'standalone: false' on the endpoint"
            )
        scenarios[endpoint.name] = Scenario(
            name=endpoint.name,
            steps=(Step(endpoint, endpoint.vars),),
            data=endpoint.data,
        )

    return Project(endpoints, scenarios)


def _load_endpoint(folder: Path, root: Path) -> Endpoint:
    meta_path = folder / "meta.yaml"
    if not meta_path.is_file():
        raise ConfigError(f"{meta_path}: file not found")
    meta = _parse(EndpointFile, meta_path)
    request_file = _find_sibling(folder, "request")
    response_file = _find_sibling(folder, "response")
    return Endpoint(
        name=folder.name,
        path=meta.path,
        protocol=meta.protocol,
        method=meta.method,
        headers=meta.headers,
        extract=meta.extract,
        validation=meta.validation,
        standalone=meta.standalone,
        request=_read(request_file),
        request_content_type=mimetypes.guess_type(request_file.name)[0] if request_file else None,
        response=_read(response_file),
        data=_data_file(meta.data, meta_path, root),
        vars=meta.vars,
    )


def _load_scenario(file: Path, root: Path, endpoints: dict[str, Endpoint]) -> Scenario:
    spec = _parse(ScenarioFile, file)

    steps = []
    for step in spec.steps:
        if step.endpoint not in endpoints:
            known = ", ".join(sorted(endpoints))
            raise ConfigError(f"{file}: unknown endpoint '{step.endpoint}' (available: {known})")
        endpoint = endpoints[step.endpoint]
        # Most specific wins: endpoint < scenario < step.
        steps.append(Step(endpoint, endpoint.vars | spec.vars | step.vars))

    return Scenario(
        name=file.stem,
        steps=tuple(steps),
        data=_data_file(spec.data, file, root),
        weight=spec.weight,
    )


def _data_file(data: Path | None, source: Path, root: Path) -> Path | None:
    if data is None:
        return None
    data_path = root / data
    if not data_path.is_file():
        raise ConfigError(f"{source}: data file '{data}' not found (looked in {root})")
    return data_path


def _find_sibling(folder: Path, stem: str) -> Path | None:
    """Find request.* / response.* whatever the extension (json, xml, graphql, ...)."""
    matches = sorted(p for p in folder.glob(f"{stem}.*") if p.is_file())
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise ConfigError(f"{folder}: expected one {stem} file, found {names}")
    return matches[0] if matches else None


def _read(file: Path | None) -> str | None:
    return file.read_text(encoding="utf-8") if file else None


def _parse[T: BaseModel](model: type[T], path: Path) -> T:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: invalid YAML: {error}") from error
    try:
        return model.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(f"{path}: {_describe(error)}") from error


def _describe(error: ValidationError) -> str:
    problems = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"])
        what = "unknown key" if item["type"] == "extra_forbidden" else item["msg"]
        problems.append(f"{where}: {what}" if where else what)
    return "; ".join(problems)
