from collections.abc import Callable
from pathlib import Path

from perfmon.reporting.base import Reporter
from perfmon.reporting.excel import ExcelReporter

# Reporters that write files, by the name given to --report. Each is built with the report folder.
REPORTERS: dict[str, Callable[[Path], Reporter]] = {
    "excel": ExcelReporter,
}
