from typing import Any, Protocol


class DataSource(Protocol):
    """Hands out one row of placeholder values per scenario iteration."""

    def next_row(self) -> dict[str, Any]: ...
