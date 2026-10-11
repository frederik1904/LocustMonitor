import csv
import random
from pathlib import Path
from typing import Any

from perfmon.config.models import ConfigError


class CsvSource:
    """Rows of a CSV file in order, starting over at the end. An empty cell becomes None."""

    def __init__(self, file: Path, *, shuffle: bool = False, seed: int | None = None) -> None:
        # utf-8-sig: Excel writes a byte order mark that would otherwise end up in the first column name.
        with file.open(newline="", encoding="utf-8-sig") as handle:
            self._rows = [
                {name: (cell or None) for name, cell in row.items() if name is not None}
                for row in csv.DictReader(handle)
            ]
        if not self._rows:
            raise ConfigError(f"{file}: no data rows")
        if shuffle:
            random.Random(seed).shuffle(self._rows)
        self._next = 0

    def next_row(self) -> dict[str, Any]:
        row = self._rows[self._next % len(self._rows)]
        self._next += 1
        return row
