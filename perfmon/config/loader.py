import mimetypes
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from perfmon.config.models import ConfigError, DataBinding, Endpoint, Project, Scenario, Step
from perfmon.config.schema import BodyMatch, DataSpec, EndpointFile, ScenarioFile

_YAML_SUFFIXES = (".yaml", ".yml")


def load_project(root: str | Path) -> Project:
    """Read endpoints/ and scenarios/ under root. Endpoints only run as steps of a scenario."""
    root = Path(root)
    endpoint_dir = root / "endpoints"
    if not endpoint_dir.is_dir():
        raise ConfigError(f"{endpoint_dir}: directory not found")

    endpoints = {
        folder.name: _load_endpoint(folder)
        for folder in sorted(endpoint_dir.iterdir())
        if folder.is_dir()
    }

    scenario_dir = root / "scenarios"
    scenarios: dict[str, Scenario] = {}
    for file in sorted(p for p in scenario_dir.glob("*") if p.suffix in _YAML_SUFFIXES and p.is_file()):
        if file.stem in scenarios:
            raise ConfigError(f"{file}: there is more than one scenario file named '{file.stem}'")
        scenarios[file.stem] = _load_scenario(file, root, endpoints)
    if not scenarios:
        raise ConfigError(f"{scenario_dir}: no scenario files (*.yaml) found, so there is nothing to run")

    return Project(endpoints, scenarios)


def _load_endpoint(folder: Path) -> Endpoint:
    candidates = [folder / f"meta{suffix}" for suffix in _YAML_SUFFIXES if (folder / f"meta{suffix}").is_file()]
    if len(candidates) != 1:
        problem = "file not found" if not candidates else "there is also a meta.yml; keep one of them"
        raise ConfigError(f"{folder / 'meta.yaml'}: {problem}")
    meta_path = candidates[0]
    meta = _parse(EndpointFile, meta_path)
    request_file = _find_sibling(folder, "request")
    response_file = _find_sibling(folder, "response")
    if meta.validation and meta.validation.body is not BodyMatch.NONE and response_file is None:
        raise ConfigError(
            f"{meta_path}: validate.body is '{meta.validation.body}' but the folder has no response file to compare with"
        )
    return Endpoint(
        name=folder.name,
        path=meta.path,
        protocol=meta.protocol,
        method=meta.method,
        query=meta.query,
        headers=meta.headers,
        extract=meta.extract,
        validation=meta.validation,
        request=_read(request_file),
        request_content_type=mimetypes.guess_type(request_file.name)[0] if request_file else None,
        response=_read(response_file),
        vars=meta.vars,
    )


def _load_scenario(file: Path, root: Path, endpoints: dict[str, Endpoint]) -> Scenario:
    spec = _parse(ScenarioFile, file)

    steps: list[Step] = []
    for step in spec.steps:
        if step.endpoint not in endpoints:
            known = ", ".join(sorted(endpoints))
            raise ConfigError(f"{file}: unknown endpoint '{step.endpoint}' (available: {known})")
        endpoint = endpoints[step.endpoint]
        name = _step_name(step.name, endpoint.name, {earlier.name for earlier in steps}, file)
        # Most specific wins: endpoint < scenario < step.
        steps.append(Step(name, endpoint, endpoint.vars | spec.vars | step.vars))

    return Scenario(
        name=file.stem,
        steps=tuple(steps),
        data=_data_file(spec.data, file, root),
        weight=spec.weight,
    )


def _step_name(given: str | None, endpoint: str, taken: set[str], source: Path) -> str:
    """The step's label in reports: as given, else the endpoint name, numbered when it repeats."""
    if given is not None:
        if given in taken:
            raise ConfigError(f"{source}: two steps are named '{given}'")
        return given
    name, count = endpoint, 1
    while name in taken:
        count += 1
        name = f"{endpoint}#{count}"
    return name


def _data_file(data: DataSpec | None, source: Path, root: Path) -> DataBinding | None:
    if data is None:
        return None
    data_path = root / data.file
    if not data_path.is_file():
        raise ConfigError(f"{source}: data file '{data.file}' not found (looked in {root})")
    return DataBinding(data_path, data.mode, data.seed)


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
