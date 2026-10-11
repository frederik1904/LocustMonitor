import argparse
import sys
from pathlib import Path

from perfmon.config.models import ConfigError, Project
from perfmon.project import open_project


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
        # Imported late: Locust patches the standard library on import.
        if args.command == "check":
            from perfmon.modes.check import check_project, format_report

            outcomes = check_project(project, host, args.scenarios)
            print(format_report(outcomes))
            return 0 if all(outcome.passed for outcome in outcomes) else 1

        from perfmon.modes.baseline import Baseline
        from perfmon.modes.limit import Limit
        from perfmon.modes.load import run_load

        modes = project.settings.modes
        mode = Baseline(modes.baseline) if args.mode == "baseline" else Limit(modes.limit)
        report = run_load(project, host, mode, args.scenarios)
        print(report.text)
        return 1 if mode.failures_fail_the_run and report.failures else 0
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2


def _host(project: Project, given: str | None, root: str) -> str:
    host = given or project.settings.host
    if not host:
        raise ConfigError(f"{root}: no host; set host in project.yaml or pass --host")
    return host


def _known(project: Project, names: list[str]) -> None:
    unknown = sorted(set(names) - set(project.scenarios))
    if unknown:
        available = ", ".join(sorted(project.scenarios))
        raise ConfigError(f"unknown scenario(s): {', '.join(unknown)} (available: {available})")
