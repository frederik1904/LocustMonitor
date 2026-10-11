from pathlib import Path


def write(root: Path, relative: str, text: str = "") -> None:
    """Write a file under a project folder, creating its directories."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
