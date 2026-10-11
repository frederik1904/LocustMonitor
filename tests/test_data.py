from pathlib import Path

import pytest

from perfmon.config.loader import load_project
from perfmon.config.models import ConfigError
from perfmon.data.csv import CsvSource
from perfmon.data.pool import DataPool


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def take(source, count: int) -> list[str]:
    return [source.next_row()["id"] for _ in range(count)]


def test_csv_rows_in_order_wrapping_with_empty_cells_as_none(tmp_path: Path):
    (tmp_path / "rows.csv").write_bytes("﻿id,note\n1,a\n2,\n".encode())  # with Excel's byte order mark
    source = CsvSource(tmp_path / "rows.csv")
    assert [source.next_row() for _ in range(3)] == [
        {"id": "1", "note": "a"},
        {"id": "2", "note": None},
        {"id": "1", "note": "a"},
    ]


def test_shuffle_uses_every_row_once_per_pass_and_is_repeatable_with_a_seed(tmp_path: Path):
    write(tmp_path, "rows.csv", "id\n" + "\n".join(map(str, range(20))) + "\n")
    first = take(CsvSource(tmp_path / "rows.csv", shuffle=True, seed=7), 40)
    again = take(CsvSource(tmp_path / "rows.csv", shuffle=True, seed=7), 40)
    assert first == again and first[:20] == first[20:]
    assert sorted(first[:20], key=int) == [str(n) for n in range(20)] and first[:20] != sorted(first[:20], key=int)


def test_csv_without_rows_is_a_config_error(tmp_path: Path):
    write(tmp_path, "rows.csv", "id\n")
    with pytest.raises(ConfigError, match="no data rows"):
        CsvSource(tmp_path / "rows.csv")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    write(tmp_path, "data/ids.csv", "id\n1\n2\n3\n4\n")
    write(tmp_path, "endpoints/get/meta.yaml", "path: /x/{{id}}\n")
    for name, data in {
        "shared_a": "data/ids.csv",
        "shared_b": "{file: data/ids.csv, mode: shared}",
        "own": "{file: data/ids.csv, mode: scenario}",
        "random_a": "{file: data/ids.csv, mode: random, seed: 1}",
        "random_b": "{file: data/ids.csv, mode: random, seed: 1}",
    }.items():
        write(tmp_path, f"scenarios/{name}.yaml", f"steps: [get]\ndata: {data}\n")
    write(tmp_path, "scenarios/no_data.yaml", "steps: [get]\n")
    return tmp_path


def test_modes_decide_who_shares_a_cursor(project: Path):
    loaded = load_project(project)
    pool = DataPool(loaded)

    def draw(name: str) -> str | None:
        return pool.next_row(loaded.scenarios[name]).get("id")

    # shared: the two scenarios take turns on one cursor.
    assert [draw("shared_a"), draw("shared_b"), draw("shared_a")] == ["1", "2", "3"]
    # scenario: its own cursor, untouched by the others.
    assert [draw("own"), draw("own")] == ["1", "2"]
    # random: one shuffled cursor shared by both, so four draws use each row once.
    assert sorted(draw(name) for name in ["random_a", "random_b", "random_a", "random_b"]) == ["1", "2", "3", "4"]
    assert draw("no_data") is None


def test_unsupported_data_file_type(project: Path):
    write(project, "data/ids.json", "[]")
    write(project, "scenarios/own.yaml", "steps: [get]\ndata: data/ids.json\n")
    with pytest.raises(ConfigError, match="unsupported data file type"):
        DataPool(load_project(project))
