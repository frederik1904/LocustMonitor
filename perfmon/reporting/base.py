from dataclasses import dataclass
from typing import Protocol

from perfmon.reporting.summary import RunSummary


@dataclass(frozen=True)
class RequestSample:
    """One finished request, as it happens."""

    scenario: str
    step: str
    method: str
    response_time_ms: float
    failure: str | None


class Reporter(Protocol):
    """Somewhere the results of a load run go: the terminal, a spreadsheet, a metrics store."""

    def on_request(self, sample: RequestSample) -> None:
        """Called for every request while the run is going. It runs in the request path, so it
        must return at once: buffer and send elsewhere, never wait here."""
        ...

    def on_end(self, summary: RunSummary) -> str | None:
        """Called once with the whole run. Return a line to tell the person where the report went, if any."""
        ...
