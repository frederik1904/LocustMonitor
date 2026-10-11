from perfmon.reporting.base import RequestSample
from perfmon.reporting.summary import RunSummary


class ConsoleReporter:
    """Prints the run as text tables."""

    def on_request(self, sample: RequestSample) -> None:
        pass

    def on_end(self, summary: RunSummary) -> str | None:
        print(format_summary(summary))
        return None


def format_summary(summary: RunSummary) -> str:
    parts = ["\n".join(summary.findings), _steps(summary), _failures(summary), _iterations(summary)]
    return "\n\n".join(part for part in parts if part)


def _table(rows: list[tuple[str, ...]]) -> str:
    """Rows as aligned text: numbers right-aligned; the first column and the Targets column, being text, left."""
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    text_columns = {0} | {column for column, title in enumerate(rows[0]) if title == "Targets"}
    return "\n".join(
        "  ".join(
            cell.ljust(width) if column in text_columns else cell.rjust(width)
            for column, (cell, width) in enumerate(zip(row, widths, strict=True))
        ).rstrip()
        for row in rows
    )


def _steps(summary: RunSummary) -> str:
    header = ("Step", "Requests", "Failed %", "p50 ms", "p95 ms", "p99 ms", "Max ms")
    rows: list[tuple[str, ...]] = [(*header, "Targets") if summary.has_targets else header]
    for key, measure in summary.steps.items():
        row = (
            key.label,
            str(measure.requests),
            f"{measure.failure_percent:.1f}",
            f"{measure.p50:.0f}",
            f"{measure.p95:.0f}",
            f"{measure.p99:.0f}",
            f"{measure.times.maximum:.0f}",
        )
        rows.append((*row, summary.target_verdict(key, measure) or "-") if summary.has_targets else row)
    return _table(rows)


def _failures(summary: RunSummary) -> str:
    if not summary.failures:
        return ""
    lines = []
    for failure in summary.failures:
        status = f" {failure.status}" if failure.status else ""
        lines.append(
            f"  {failure.occurrences} x {failure.key.label}: {failure.message} [{failure.kind}{status}; "
            f"first after {failure.first_seen_seconds:.0f} s at {failure.first_seen_users} users]"
        )
    return "\n".join(["Failures:", *lines])


def _iterations(summary: RunSummary) -> str:
    """Per scenario: iterations run, how many stopped at a failed step, the requests never sent, and how
    long a complete iteration took."""
    rows: list[tuple[str, ...]] = [
        ("Scenario", "Iterations", "Incomplete", "Incomplete %", "Steps not sent", "Iteration p50 ms", "p95 ms")
    ]
    for name, count in sorted(summary.iterations.items()):
        rows.append(
            (
                name,
                str(count.total),
                str(count.incomplete),
                f"{count.incomplete_percent:.1f}",
                str(count.steps_not_sent),
                f"{count.durations.percentile(0.50):.0f}",
                f"{count.durations.percentile(0.95):.0f}",
            )
        )
    stopped = [
        f"{name}: {count.setups_failed} virtual user(s) stopped because their setup failed"
        for name, count in sorted(summary.iterations.items())
        if count.setups_failed
    ]
    return "\n".join([_table(rows), *stopped])
