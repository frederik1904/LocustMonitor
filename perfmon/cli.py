import argparse
import os
import sys
from pathlib import Path

from perfmon.config.models import ConfigError, Project
from perfmon.project import open_project

# Kept here as plain names so that --help does not have to import Locust and the report libraries.
REPORT_NAMES = ["excel"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="perfmon")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="run every scenario once, without load, and report pass/fail")
    run = commands.add_parser("run", help="run scenarios under load and report response times")
    run.add_argument(
        "--mode",
        choices=["baseline", "limit"],
        default="baseline",
        help="baseline: steady light load; limit: raise the load until the API gives way (default: baseline)",
    )
    run.add_argument(
        "--report",
        action="append",
        default=[],
        choices=REPORT_NAMES,
        help="also write the results in this format; may be given more than once",
    )
    run.add_argument(
        "--report-dir",
        default=os.environ.get("PERFMON_REPORT_DIR", "reports"),
        help="folder for report files (default: reports, or $PERFMON_REPORT_DIR)",
    )
    for command in (check, run):
        command.add_argument("scenarios", nargs="*", help="scenarios to run (default: all)")
        command.add_argument("--root", default=".", help="project folder with endpoints/ and scenarios/ (default: .)")
        command.add_argument("--host", help="base URL of the API; overrides host in project.yaml")

    schema = commands.add_parser("schema", help="write JSON Schema files for the YAML formats (editor support)")
    schema.add_argument("--out", default="schemas", help="folder to write to (default: schemas)")

    args = parser.parse_args(argv)
    if args.command == "schema":
        from perfmon.config.json_schema import write_json_schemas

        for path in write_json_schemas(Path(args.out)):
            print(f"wrote {path}")
        return 0

    try:
        project = open_project(args.root)
        host = _host(project, args.host, args.root)
        _known(project, args.scenarios)
        if not project.settings.verify_tls:
            print("Note: verify_tls is false, so the API's TLS certificate is not checked.", file=sys.stderr)
        # Imported late: Locust patches the standard library on import.
        if args.command == "check":
            from perfmon.modes.check import check_project, format_report

            outcomes = check_project(project, host, args.scenarios)
            print(format_report(outcomes))
            return 0 if all(outcome.passed for outcome in outcomes) else 1

        from perfmon.modes.baseline import Baseline
        from perfmon.modes.limit import Limit
        from perfmon.modes.load import run_failed, run_load
        from perfmon.reporting import REPORTERS
        from perfmon.reporting.console import ConsoleReporter

        modes = project.settings.modes
        mode = Baseline(modes.baseline) if args.mode == "baseline" else Limit(modes.limit)
        reporters = [ConsoleReporter(), *(REPORTERS[name](Path(args.report_dir)) for name in args.report)]
        summary = run_load(project, host, mode, args.scenarios, reporters)
        for reporter in reporters:
            written = reporter.on_end(summary)
            if written:
                print(f"\n{written}")
        return 1 if run_failed(mode, summary) else 0
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2


def _host(project: Project, given: str | None, root: str) -> str:
    host = given or project.settings.host
    if not host:
        raise ConfigError(f"{root}: no host; set host in project.yaml or pass --host")
    return host.rstrip("/")  # paths start with a slash, so one at the end of the host would double it


def _known(project: Project, names: list[str]) -> None:
    unknown = sorted(set(names) - set(project.scenarios))
    if unknown:
        available = ", ".join(sorted(project.scenarios))
        raise ConfigError(f"unknown scenario(s): {', '.join(unknown)} (available: {available})")
