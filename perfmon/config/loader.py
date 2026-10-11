import mimetypes
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from perfmon.config.models import ConfigError, DataBinding, Endpoint, Project, Scenario, Step
from perfmon.config.schema import BodyMatch, DataSpec, EndpointFile, ProjectFile, ScenarioFile, StepFile

_YAML_SUFFIXES = (".yaml", ".yml")


def load_project(root: str | Path) -> Project:
    """Read project.yaml, endpoints/ and scenarios/ under root. Endpoints only run as steps of a scenario."""
    root = Path(root)
    settings_file = _one_of(root, "project")
    settings = _parse(ProjectFile, settings_file) if settings_file else ProjectFile()
    endpoint_dir = root / "endpoints"
    if not endpoint_dir.is_dir():
        raise ConfigError(f"{endpoint_dir}: directory not found")

    endpoints = {folder.name: _load_endpoint(folder) for folder in sorted(endpoint_dir.iterdir()) if folder.is_dir()}

    scenario_dir = root / "scenarios"
    scenarios: dict[str, Scenario] = {}
    for file in sorted(p for p in scenario_dir.glob("*") if p.suffix in _YAML_SUFFIXES and p.is_file()):
        if file.stem in scenarios:
            raise ConfigError(f"{file}: there is more than one scenario file named '{file.stem}'")
        scenarios[file.stem] = _load_scenario(file, root, endpoints, settings.vars)
    if not scenarios:
        raise ConfigError(f"{scenario_dir}: no scenario files (*.yaml) found, so there is nothing to run")

    return Project(endpoints, scenarios, settings)


def _load_endpoint(folder: Path) -> Endpoint:
    meta_path = _one_of(folder, "meta")
    if meta_path is None:
        raise ConfigError(f"{folder / 'meta.yaml'}: file not found")
    meta = _parse(EndpointFile, meta_path)
    request_file = _find_sibling(folder, "request")
    response_file = _find_sibling(folder, "response")
    if meta.validation and meta.validation.body is not BodyMatch.NONE and response_file is None:
        raise ConfigError(
            f"{meta_path}: validate.body is '{meta.validation.body}' "
            "but the folder has no response file to compare with"
        )
    return Endpoint(
        name=folder.name,
        meta=meta,
        request=_read(request_file),
        request_content_type=mimetypes.guess_type(request_file.name)[0] if request_file else None,
        response=_read(response_file),
    )


def _load_scenario(file: Path, root: Path, endpoints: dict[str, Endpoint], project_vars: dict[str, Any]) -> Scenario:
    spec = _parse(ScenarioFile, file)

    def resolve(step_files: list[StepFile], prefix: str) -> tuple[Step, ...]:
        steps: list[Step] = []
        for step in step_files:
            if step.endpoint not in endpoints:
                known = ", ".join(sorted(endpoints))
                raise ConfigError(f"{file}: unknown endpoint '{step.endpoint}' (available: {known})")
            endpoint = endpoints[step.endpoint]
            name = prefix + _step_name(
                step.name, endpoint.name, {earlier.name.removeprefix(prefix) for earlier in steps}, file
            )
            # Most specific wins: project < endpoint < scenario < step.
            steps.append(Step(name, endpoint, project_vars | endpoint.meta.vars | spec.vars | step.vars))
        return tuple(steps)

    return Scenario(
        name=file.stem,
        steps=resolve(spec.steps, ""),
        data=_data_file(spec.data, file, root),
        weight=spec.weight,
        setup=resolve(spec.setup.steps, "setup/") if spec.setup else (),
        setup_data=_data_file(spec.setup.data, file, root) if spec.setup else None,
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


def _one_of(folder: Path, stem: str) -> Path | None:
    """The folder's <stem>.yaml or <stem>.yml; having both is an error."""
    found = [folder / f"{stem}{suffix}" for suffix in _YAML_SUFFIXES if (folder / f"{stem}{suffix}").is_file()]
    if len(found) > 1:
        raise ConfigError(f"{found[0]}: there is also a {found[1].name}; keep one of them")
    return found[0] if found else None


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
