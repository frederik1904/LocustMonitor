import argparse
import sys
from pathlib import Path

from perfmon.config.models import ConfigError
from perfmon.project import open_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="perfmon")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="run every scenario once, without load, and report pass/fail")
    check.add_argument("scenarios", nargs="*", help="scenarios to run (default: all)")
    check.add_argument("--root", default=".", help="project folder holding endpoints/ and scenarios/ (default: .)")
    check.add_argument("--host", required=True, help="base URL of the API, e.g. https://api.example.com")

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
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    unknown = sorted(set(args.scenarios) - set(project.scenarios))
    if unknown:
        available = ", ".join(sorted(project.scenarios))
        print(f"Unknown scenario(s): {', '.join(unknown)} (available: {available})", file=sys.stderr)
        return 2

    # Imported late: Locust patches the standard library on import.
    from perfmon.modes.check import check_project, format_report

    try:
        outcomes = check_project(project, args.host, args.scenarios)
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    print(format_report(outcomes))
    return 0 if all(outcome.passed for outcome in outcomes) else 1
