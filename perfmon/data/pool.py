from typing import Any

from perfmon.config.models import ConfigError, DataBinding, Project, Scenario
from perfmon.config.schema import DataMode
from perfmon.data.base import DataSource
from perfmon.data.csv import CsvSource


class DataPool:
    """The data source of every scenario in a project, shared between scenarios where the mode says so."""

    def __init__(self, project: Project) -> None:
        shared: dict[tuple[Any, ...], DataSource] = {}
        self._sources: dict[str, DataSource] = {}
        for scenario in project.scenarios.values():
            data = scenario.data
            if data is None:
                continue
            if data.mode is DataMode.SCENARIO:
                self._sources[scenario.name] = _open(data)
            else:
                key = (data.file, data.mode, data.seed)
                if key not in shared:
                    shared[key] = _open(data)
                self._sources[scenario.name] = shared[key]

    def next_row(self, scenario: Scenario) -> dict[str, Any]:
        """The row for one iteration of the scenario; empty when it has no data."""
        source = self._sources.get(scenario.name)
        return source.next_row() if source else {}


def _open(data: DataBinding) -> DataSource:
    if data.file.suffix.lower() != ".csv":
        raise ConfigError(f"{data.file}: unsupported data file type (supported: .csv)")
    return CsvSource(data.file, shuffle=data.mode is DataMode.RANDOM, seed=data.seed)
