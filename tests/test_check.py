import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from helpers import write
from perfmon.cli import main
from perfmon.config.loader import load_project
from perfmon.modes.check import check_project


class _Api(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"{}"
        self.send_response(200 if self.path.startswith("/ok") else 404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def host():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Api)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    write(tmp_path, "endpoints/ok/meta.yaml", "path: /ok/{{id}}\nvars: {id: 5}\nvalidate: {status: 200}\n")
    write(tmp_path, "endpoints/gone/meta.yaml", "path: /gone\nvalidate: {status: 404}\n")
    write(tmp_path, "scenarios/flow.yaml", "steps: [ok, gone]\n")
    write(tmp_path, "scenarios/ok.yaml", "steps: [ok]\n")
    return tmp_path


def test_reports_one_outcome_per_step(project: Path, host: str):
    outcomes = check_project(load_project(project), host)
    assert [(o.scenario, o.request, o.status, o.failure) for o in outcomes] == [
        ("flow", f"GET {host}/ok/5", 200, None),
        ("flow", f"GET {host}/gone", 404, None),
        ("ok", f"GET {host}/ok/5", 200, None),
    ]
    assert all(o.elapsed_ms is not None for o in outcomes)


def test_failures_explain_themselves(project: Path, host: str):
    write(project, "endpoints/gone/meta.yaml", "path: /gone\nvalidate: {status: 200}\n")
    write(project, "endpoints/unchecked/meta.yaml", "path: /missing\n")
    write(project, "endpoints/broken/meta.yaml", "path: /ok/{{nope}}\n")
    write(project, "scenarios/unchecked.yaml", "steps: [unchecked]\n")
    write(project, "scenarios/broken.yaml", "steps: [broken]\n")
    failures = {o.scenario: o.failure for o in check_project(load_project(project), host) if not o.passed}
    assert failures["flow"] == "expected status 200, got 404"
    assert "404" in failures["unchecked"]
    assert failures["broken"] == "step 'broken' in scenario 'broken': no value for: nope"


def test_unreachable_host_is_a_failure_not_a_crash(project: Path):
    outcomes = check_project(load_project(project), "http://127.0.0.1:9", only=["ok"])
    assert len(outcomes) == 1 and not outcomes[0].passed and outcomes[0].status is None


def test_cli_exit_codes(project: Path, host: str, capsys: pytest.CaptureFixture[str]):
    root = ["--root", str(project), "--host", host]
    assert main(["check", *root]) == 0
    assert "3 passed, 0 failed, 0 skipped" in capsys.readouterr().out

    assert main(["check", "nope", *root]) == 2
    assert "unknown scenario(s): nope (available: flow, ok)" in capsys.readouterr().err

    write(project, "endpoints/ok/meta.yaml", "path: /ok\nvalidate: {status: 201}\n")
    assert main(["check", "ok", *root]) == 1
    assert "FAIL  GET" in capsys.readouterr().out

    write(project, "endpoints/ok/meta.yaml", "pth: /ok\n")
    assert main(["check", *root]) == 2
    assert "Configuration error" in capsys.readouterr().err


def test_steps_after_a_failure_are_reported_as_skipped(project: Path, host: str, capsys: pytest.CaptureFixture[str]):
    write(project, "scenarios/flow.yaml", "steps: [gone, ok]\n")
    write(project, "endpoints/gone/meta.yaml", "path: /gone\n")
    assert main(["check", "flow", "--root", str(project), "--host", host]) == 1
    out = capsys.readouterr().out
    assert "SKIP  ok  (an earlier step failed)" in out and "0 passed, 1 failed, 1 skipped" in out


def test_check_uses_the_first_data_row(project: Path, host: str):
    write(project, "data/ids.csv", "id,unused\n8,\n9,x\n")
    write(project, "endpoints/ok/meta.yaml", "path: /ok/{{id}}\n")
    write(project, "scenarios/ok.yaml", "steps: [ok]\ndata: data/ids.csv\n")
    outcomes = check_project(load_project(project), host, only=["ok"])
    assert outcomes[0].request == f"GET {host}/ok/8"


def test_a_failed_setup_skips_every_step(project: Path, host: str, capsys: pytest.CaptureFixture[str]):
    write(project, "endpoints/gone/meta.yaml", "path: /gone\n")
    write(project, "scenarios/flow.yaml", "setup: [gone]\nsteps: [ok, ok]\n")
    assert main(["check", "flow", "--root", str(project), "--host", host]) == 1
    out = capsys.readouterr().out
    assert "SKIP  ok  " in out and "SKIP  ok#2  " in out and "0 passed, 1 failed, 2 skipped" in out


def test_host_comes_from_the_project_file_unless_given(project: Path, host: str, capsys: pytest.CaptureFixture[str]):
    assert main(["check", "ok", "--root", str(project)]) == 2
    assert "no host; set host in project.yaml or pass --host" in capsys.readouterr().err
    write(project, "project.yaml", f"host: {host}\n")
    assert main(["check", "ok", "--root", str(project)]) == 0
