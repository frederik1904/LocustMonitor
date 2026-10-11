from typing import Any

from perfmon.config.models import ConfigError, DataBinding, Project, Scenario
from perfmon.config.schema import DataMode
from perfmon.data.base import DataSource
from perfmon.data.csv import CsvSource


class DataPool:
    """The data sources of every scenario in a project, shared between scenarios where the mode says so."""

    def __init__(self, project: Project) -> None:
        shared: dict[tuple[Any, ...], DataSource] = {}

        def source_for(data: DataBinding | None) -> DataSource | None:
            if data is None:
                return None
            if data.mode is DataMode.SCENARIO:
                return _open(data)
            key = (data.file, data.mode, data.seed)
            if key not in shared:
                shared[key] = _open(data)
            return shared[key]

        self._iteration = {scenario.name: source_for(scenario.data) for scenario in project.scenarios.values()}
        self._setup = {scenario.name: source_for(scenario.setup_data) for scenario in project.scenarios.values()}

    def next_row(self, scenario: Scenario) -> dict[str, Any]:
        """The row for one iteration of the scenario; empty when it has no data."""
        source = self._iteration.get(scenario.name)
        return source.next_row() if source else {}

    def next_setup_row(self, scenario: Scenario) -> dict[str, Any]:
        """The row for one virtual user's setup; empty when the setup has no data."""
        source = self._setup.get(scenario.name)
        return source.next_row() if source else {}


def _open(data: DataBinding) -> DataSource:
    if data.file.suffix.lower() != ".csv":
        raise ConfigError(f"{data.file}: unsupported data file type (supported: .csv)")
    return CsvSource(data.file, shuffle=data.mode is DataMode.RANDOM, seed=data.seed)
