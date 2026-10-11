# PerformanceMonitor: plan, decisions and todo

A Locust-based tool for baseline response-time measurement, limit testing and
functional endpoint checks, driven by folders of YAML and request/response files.

## Goal

- Describe each endpoint in its own folder: metadata, a request template and an expected response.
- Substitute `{{placeholders}}` from static vars, CSV rows and earlier responses (request chaining).
- Optionally validate responses.
- Stay open for new API styles (REST now; SOAP and GraphQL later) and new report outputs
  (Excel now; LGTM or others later) through the strategy pattern.

## Working rules

- **Every feature ships with an example.** A step is not done until an example project uses the
  feature and it has been run (`perfmon check`, and a load run where relevant).
- **Several example folders are fine.** `Example/` targets sampleapis.com and must always pass;
  `ExampleFailing/` fails on purpose to show the reports; `ExampleSecrets/` needs an environment
  variable; add another folder when a
  feature needs a different kind of package (e.g. a SOAP or GraphQL API, or a local mock server for
  writes and failure cases). Each example folder has its own README.
- **Keep the editor support up to date.** Whenever the file formats change:
  - give every new key a `description` in `perfmon/config/schema.py` (it becomes the hover text),
  - regenerate with `uv run perfmon schema` (a test fails when `schemas/` is out of date),
  - add a mapping in `.idea/jsonSchemas.xml` for any new kind of YAML file (e.g. mode settings in step 6).
- **Before committing, all four must pass:** `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format --check .` and `uv run pyright`.

## Status

| # | Step | Status |
|---|------|--------|
| 1 | Models, loader, template renderer | Done |
| 2 | REST handler, runner, user factory | Done |
| 3 | `check` mode (functional endpoint testing) | Done |
| 4 | Chaining (`extract`) and CSV data source | Done |
| 5 | Response validation (`subset` / `exact`) | Done |
| 5a | Review fixes: correctness of results | Done |
| 5b | Review cleanup: code quality | Done |
| 6 | Project file, `perfmon run`, `baseline` and `limit` modes | Done |
| 7 | Reporter interface and Excel reporter | Done |
| 8 | Ergonomics and docs | Todo |
| 9 | Generate endpoint folders from OpenAPI | Todo |

## Todo

### 3. `check` mode (done)

- [x] Run every scenario once, without load, and report pass/fail per step.
- [x] Exit non-zero on any failure so it can run in CI (0 pass, 1 failures, 2 config or usage error).
- [x] Reuse `runner.run_scenario` through Locust's own `HttpSession`.
- [x] Entry point: `uv run perfmon check --root DIR --host URL [scenario ...]`.
- [x] `validate.status` is applied, in check mode and in load runs.

### 4. Chaining and CSV data (done)

- [x] `extract(endpoint, response) -> dict` on `ProtocolHandler`; JSONPath for REST via `jsonpath-ng`.
- [x] Per-iteration context in the runner: step vars < data row < extracted values.
- [x] `perfmon/data/`: `base.py` (`DataSource`), `csv.py` (`CsvSource`), `pool.py` (who shares a cursor).
- [x] One row per scenario iteration, shared by every step.
- [x] Data modes `shared` (default), `scenario` and `random` (shuffled once, optional `seed`).
- [x] `data:` accepts a path or `{file, mode, seed}`.
- [x] A failed step, or an extract that finds nothing, stops the chain; check mode reports the rest as SKIP.
- [x] Null means omit for JSON body keys and list items, headers and query parameters.
- [x] `query:` mapping in `meta.yaml`.
- [x] A null placeholder inside a longer value or in `path` is an error.
- [x] The body is only parsed and re-serialised when a null variable is present.
- [x] Example: chaining in `browse_beers` and `coffee_lifecycle`, CSV in `get_beer`, one scenario per data
      mode (`get_beer`, `get_stout`, `random_beer`), null omission in `coffee_break` and `coffee_lifecycle`.
- [x] Editor support: descriptions for `query` and the `data` forms; schemas regenerated.

### 5. Validation (done)

- [x] `check(endpoint, response, context) -> failure message | None` on `ProtocolHandler`.
- [x] Sent with `catch_response=True` so validation failures count as Locust failures.
- [x] `status`: compare the HTTP status, before the body.
- [x] `body: subset`: everything in `response.*` must be in the response; extra keys and extra trailing
      list items are allowed.
- [x] `body: exact`: full equality.
- [x] `response.*` is rendered through the template engine; a null variable leaves its key unchecked.
- [x] `body: subset` or `exact` without a response file is a load-time error.
- [x] Example: `get_beer` and `create_coffee` (subset), `delete_coffee` (exact) in `Example/`;
      failure reports in `ExampleFailing/`.
- [x] Editor support: `validate.body` description updated; schemas regenerated.
- [ ] Later, if needed: `body: schema` (JSON Schema), and a way to match list items in any order.

### 5a. Review fixes: correctness of results (done)

Found in the code review after step 5.

- [x] **Text values are JSON-escaped in JSON files** when the placeholder sits inside a string, in
      request and response files, so quotes and line breaks stay valid JSON.
- [x] **A project with no scenarios is an error.**
- [x] **`.yml` is accepted** like `.yaml` for scenario files and `meta`; having both spellings is an error.
- [x] **Distinct stats names for repeated endpoints:** optional `name:` on a step; without it a repeated
      endpoint is numbered `#2`, `#3`.
- [x] **Load-time placeholder check:** every `{{placeholder}}` in path, query, headers, request and
      response files must be supplied by vars, a CSV column or an earlier `extract`.
- [x] **Load-time check of JSONPath syntax** in `extract`.
- [x] Example: step names in `coffee_break`; a title with quotes in `coffee_lifecycle`.
- [x] Editor support: description for step `name`; `.yml` patterns in the IntelliJ mapping; schemas regenerated.

### 5b. Review cleanup: code quality (done)

Found in the same review. No behaviour change.

- [x] **One list of endpoint fields.** The resolved `Endpoint` wraps the parsed `EndpointFile` as
      `endpoint.meta`, so a new `meta.yaml` key is added in `schema.py` only.
- [x] **JSON rendering moved next to the REST handler** (`perfmon/protocols/json_template.py`);
      `template.py` keeps the format-neutral parts.
- [x] **`ruff` (lint and format) and `pyright` are set up** in `pyproject.toml` as dev dependencies; both
      pass. Long lines are allowed in tests, which hold YAML and JSON snippets as one-line strings.
- [x] **Shared test helper:** `write` lives in `tests/helpers.py`.

### 6. Project file, `perfmon run` and modes (done)

- [x] **`project.yaml`** (optional) with `host`, shared `vars` (lowest precedence) and `modes`.
- [x] **`perfmon run --mode baseline|limit [scenario ...]`**, with `--root` and `--host` (overrides the
      project file). `perfmon check` takes the host from the project file too.
- [x] **Secrets from the environment:** `{{$env.NAME}}`; an unset variable is reported before anything runs.
- [x] **Per-user setup:** `setup:` in a scenario (a list of steps, or `{data, steps}`), run once per
      virtual user. Its data row and extracted values are available in every iteration. A user whose
      setup fails stops.
- [x] `baseline`: a fixed number of users per scenario, constant pacing, fixed duration; a table with
      requests, failures, p50/p95/p99, average and requests per second for every step.
- [x] `limit`: users raised in steps across all scenarios (shared by weight); stops when a step's error
      rate or p95 crosses `stop_when`; reports the step where it broke and the last healthy one.
      Only status codes are checked, not bodies.
- [x] `locustfile.py` and `PERFMON_ROOT` removed; `perfmon run` is the only way to start a load run.
- [x] Pacing: seconds between the starts of a user's iterations, per mode.
- [x] Durations accept seconds or `30s` / `5m` / `1h`.
- [x] A run stops gracefully: users finish the iteration they are in, so clean-up steps still run.
- [x] Example: `project.yaml` in all example projects; `setup:` in `Example/scenarios/tasting.yaml`;
      `{{$env.NAME}}` in `ExampleSecrets/`.
- [x] Editor support: `schemas/project.schema.json` with its IntelliJ mapping; descriptions for `setup`.
- [x] **Iteration statistic:** per scenario, the iterations run, how many were incomplete (a step
      failed) and how many steps were therefore never sent; limit mode also prints it per step. Kept
      apart from the request failure rate, because a step that was not sent did not itself fail.
- [ ] Later, if needed: command-line overrides for mode settings (`--users`, `--duration`); a warm-up
      period excluded from a limit step; baseline thresholds that fail the run (a regression gate).

### 7. Reporting (done)

Readers: developers looking for a bottleneck, and people checking a contract (were the targets met?).

- [x] `perfmon/reporting/`: `base.py` (`Reporter` interface), `summary.py` (the run as plain data),
      `console.py` and `excel.py`.
- [x] The interface has two hooks: `on_request` (every request as it finishes; must not block) and
      `on_end(summary)`. The terminal output is a reporter too, fed from the same summary.
- [x] `perfmon run --report excel [--report-dir DIR]` writes `<project>-<mode>-<start time>.xlsx`.
- [x] **Our own measurements instead of Locust's cumulative statistics:** per step, per level of load
      and per time slice, kept as counts per rounded response time so memory does not grow with the run.
- [x] **Load steps in full:** requests/s, intended and achieved iterations/s, failed %, p50/p95/p99/max,
      iterations, incomplete, steps not sent, targets met, verdict.
- [x] **Every step at every level of load** (sheet "Steps by load"): which endpoint bends first.
- [x] **Failures by kind and status code**, with when and at how many users each was first seen.
- [x] **Iteration time per scenario:** p50, p95 and max of a complete iteration.
- [x] **Timeline:** users, requests/s, failed %, p50 and p95 over the run.
- [x] **Run settings** in the report (mode settings, thresholds, scenarios and weights).
- [x] **Targets:** `targets: {p95_ms, p99_ms, error_percent}` in `project.yaml` (default for every
      endpoint) and in `meta.yaml` (overrides per key). Reports say per step whether they were met; a
      limit run says up to which load they held; a baseline run exits 1 when one is missed.
- [x] **Dashboard sheet with charts:** for a limit run, response time by load, failed requests and
      incomplete iterations by load, intended and achieved iterations/s, p95 by load for the slowest
      steps; for a baseline, p95 per step beside its target; for both, response time, requests/s and
      failed % over the run. It prints one page wide.
- [x] Container: `/reports` is the report folder (`PERFMON_REPORT_DIR`), mounted from `./reports`.
- [x] Example: `Example/sample-limit-report.xlsx` and `sample-baseline-report.xlsx`; targets in
      `Example/project.yaml` and `list_beers`; a target that is missed in `ExampleFailing/`.
- [x] Editor support: descriptions for `targets`; schemas regenerated.
- [ ] Later: LGTM reporter; decide between Prometheus remote-write, OTLP and Loki at that point.
- [ ] Later, if needed: reports for `perfmon check`; choosing reporters in `project.yaml`; targets per
      step of a scenario; response size; load-generator CPU in the report.
- Decided against: comparing with earlier runs. Nothing is stored between runs.

### 8. Ergonomics and docs

- [ ] Check mode: option to run every data row instead of only the first.
- [ ] List the allowed keys in "unknown key" errors (lost when moving to pydantic).
- [ ] `validate.status` accepting several codes or a class (`[200, 204]`, `2xx`); today one code only.
- [ ] Type check for CSV values used as bare JSON (`"qty": {{qty}}` with `abc` is sent as invalid JSON).
- [ ] Warn about endpoint folders that no scenario uses.
- [ ] README with the file formats, the commands and the container usage.
- [x] Example project against sampleapis.com in `Example/`.
- [x] `.gitignore` for `__pycache__/`, `.venv/` and `.pytest_cache/`; `.idea/` is committed (it holds the schema mappings).
- [ ] Distributed runs: the shared CSV cursor is per process; unique rows across workers need partitioning.
- [ ] SOAP handler (XPath extraction) and GraphQL handler (a 200 with `errors` is a failure), each with its own example folder.

### 9. Generate endpoint folders from OpenAPI

Depends on `query:` (step 4) and body validation (step 5).

- [ ] `perfmon init --from openapi.yaml --root DIR`: one endpoint folder per operation (OpenAPI 3).
- [ ] Folder name from `operationId`, falling back to method + path.
- [ ] `meta.yaml`: `method`, `path` with `{id}` turned into `{{id}}`, `query`, `headers`, and
      `validate.status` from the first 2xx response.
- [ ] `request.json` / `response.json` from the spec's examples when present.
- [ ] Otherwise build `request.json` from the schema: `$ref` (use a library), `allOf`/`oneOf`/`anyOf`,
      enums, nested and recursive types.
- [ ] Parameters and body fields become `vars`; optional ones default to `null` so they are omitted
      until filled in.
- [ ] Never overwrite: only create folders that do not exist yet.
- [ ] Example: a small OpenAPI file and the folders generated from it, in their own example folder.
- Not generated: real values (which ids exist), chains between endpoints, obtaining auth tokens.
- Out of scope for now: reporting drift when the spec changes; Swagger 2.0.

## Known gaps and possible later additions

Not planned as steps; listed so they are not forgotten.

- **Re-login when a token expires.** `setup:` runs once per virtual user and is never repeated, so a
  token that expires during a long run turns that user's requests into 401s. Options: run setup again
  when a step answers 401, or after a configured time. Unlikely to matter for short runs.
- **Incomplete iterations do not stop a limit run.** They are reported but are not part of
  `stop_when`; a threshold such as `incomplete_percent` could be added.
- **Chains and limit tests:** a slow step throttles the steps after it, and a failed step hides the
  rest. To find one endpoint's limit, give it its own scenario and put its prerequisites in `setup:`.
- **One process, one CPU core.** Locust runs all virtual users on one core. More load needs
  distributed workers (which also need row partitioning for CSV data) or Locust's faster HTTP client.
- **Extracting from a large response is the one costly step** (about 0.26 ms of CPU for a 58 KB list),
  because the whole body is parsed. Everything else we add per step is a few microseconds.
- **Check mode uses only the first data row** of each scenario.

## Decisions and why

### Project layout on disk

- **Endpoints and scenarios are separate.** `endpoints/<name>/` holds `meta.yaml`, `request.*` and
  `response.*`; `scenarios/<name>.yaml` chains endpoints. *Why:* shared steps such as `login` are not
  copied into every chain, and the same endpoint can be fed different data per scenario.
- **Only scenarios run; endpoints are building blocks.** Testing one endpoint means a two-line scenario
  file. *Why:* one way to define a test is cleaner than two, and null-means-omit lets a scenario shape a
  request without needing an endpoint-level variant. `standalone` and endpoint-level `data:` were removed.
- **Data is bound in the scenario file only.** *Why:* the row is shared by all steps, so it belongs to
  the scenario, not to any one endpoint.
- **A variant is a scenario.** To run the same endpoint with other parameters or data, add a small
  scenario file that reuses it (see `Example/scenarios/get_stout.yaml`). *Why:* it runs side by side with
  the base, with its own weight, data and statistics, and needs no extra concept.
- **No profiles (removed).** Endpoint and scenario files briefly had `profiles:` blocks selected by
  `PERFMON_PROFILE`. *Why removed:* it was a run-wide switch, not the "several runners from one base" it
  was meant to be, and scenarios already cover that. If run-wide switching (dev/staging/prod) is needed
  later, prefer one root-level file over blocks scattered across every endpoint.
- **"Mode" means the load shape** (`check`, `baseline`, `limit`).
- **Variable precedence:** endpoint < scenario < step, then
  (at run time) CSV row, then extracted values. *Why:* the most specific and most recent value wins.
- **Request and response files may have any extension**, but only one of each per folder. *Why:* JSON,
  XML and GraphQL bodies all fit; two candidates would be ambiguous.
- **YAML for config.** *Why:* chosen over JSON for comments and readability, and over TOML for nested headers.

### Templating

- **Custom renderer instead of a Mustache library.** *Why:* Mustache HTML-escapes `{{x}}`, which corrupts
  JSON and XML bodies.
- **A missing variable is an error**, not an empty string. *Why:* silent blanks produce misleading test results.
- **Non-string values are written as JSON** (`true`, `null`, `500`). *Why:* `"qty": {{qty}}` must yield valid JSON.
- **Built-ins:** `{{$uuid}}`, `{{$timestamp}}`, `{{$isotime}}`.
- **In JSON files, a value inside a string is escaped; a bare value is inserted as-is.** *Why:*
  `"title": "{{title}}"` must survive quotes in the title, while `"qty": {{qty}}` must stay a number
  even when the value comes from a CSV as text.
- **Null means omit.** A null variable drops the JSON key, header or query parameter
  it fills, instead of sending `null`. *Why:* optional fields are common and no current endpoint needs an
  explicit null; an empty CSV cell can then mean "leave this out for this row". A literal `null` typed in
  the request file is still sent. Revisit for SOAP and GraphQL. *Why structural rather than Mustache
  sections:* `{{#x}}...{{/x}}` blocks leave trailing commas in JSON.

### Typing

- **File formats are pydantic models** with `extra="forbid"` (`perfmon/config/schema.py`). *Why:* the valid
  keys are the model's fields, so typos fail at load with the file and location; stronger than an enum of
  key names over an untyped dict.
- **Enums for fixed value sets:** `ApiProtocol`, `HttpMethod`, `BodyMatch`. An unimplemented protocol
  (e.g. `soap`) is rejected at load until its handler exists.
- **Editor help comes from generated JSON Schema.** `perfmon schema` exports the pydantic models to
  `schemas/`, and `.idea/jsonSchemas.xml` maps them onto `endpoints/*/meta.yaml` and `scenarios/*.yaml`.
  *Why:* completion, hover docs and validation in IntelliJ from the same source of truth as the loader.
- **Two layers: "as written" (`schema.py`) and "resolved" (`models.py`).** A resolved `Endpoint` is the
  parsed `meta.yaml` (`endpoint.meta`) plus its name and the request/response file contents; a resolved
  scenario has its endpoint names looked up, vars merged and data file located. *Why:* the file format
  is defined in one place, and nothing outside `config/` sees raw YAML.

### Architecture

- **Dependencies point one way and Locust stays at the edge.** `config`, `template`, `protocols` and
  `runner` do not import Locust; only `users.py` and `modes/` (and later reporting) do.
  *Why:* the core is unit-testable and reusable for `check` mode.
- **One strategy, one folder:** `base.py` holds the interface, one file per implementation, a registry in
  `__init__.py`. *Why:* adding SOAP is one file and one enum value.
- **Folders are created with their first file.** *Why:* no empty packages describing code that does not exist.
- **Protocol handlers own build, extract and validate; the transport is shared HTTP.** *Why:* REST, SOAP
  and GraphQL all travel over HTTP and differ only in how requests are shaped and responses interpreted.
- **Strategies:** `ProtocolHandler` (done for REST), `DataSource`, load mode, `Reporter`.

### Running

- **One Locust user class per scenario**, weighted by `weight`. *Why:* Locust's own weighting handles
  the mix of scenarios in a limit run.
- **Stats names are `scenario/step`.** A step is named after its endpoint unless it has a `name:`; repeats
  are numbered. *Why:* the same endpoint in two scenarios, or twice in one, is measured separately.
- **`perfmon run` drives Locust as a library**, not through `locustfile.py`. *Why:* the mode controls
  the user count step by step, reads each step's results and decides the exit code, none of which the
  Locust command line exposes. `locustfile.py` and `PERFMON_ROOT` were removed: the Locust web UI is
  not used, and one way to start a run is cleaner than two.
- **Modes are a strategy** (`LoadMode` in `perfmon/modes/load.py`): pacing, whether users are pinned
  per scenario, and a `drive` method that changes the load over time. They are plain loops over
  "set users, wait, look at the window" instead of Locust `LoadTestShape` classes. *Why:* a shape can
  only return a user count per tick; it cannot look at results or explain why it stopped.
- **Baseline users are per scenario; limit users are shared by weight.** *Why:* a baseline should measure
  every scenario the same way however many scenarios exist, while a limit test should apply a realistic mix.
- **A limit step is judged on its own requests only**, collected through a request listener. *Why:*
  Locust's statistics are cumulative, which would hide a late degradation behind early healthy steps.
- **Limit mode checks status codes only**, not response bodies (`validate.body` is ignored there;
  `extract` still runs because later steps need its values). *Why:* a limit test asks whether the API
  still answers, and comparing bodies costs load-generator CPU exactly when it is needed for load.
  Baseline and check mode compare bodies as configured.
- **Incomplete iterations are a statistic of their own**, separate from request failures. *Why:* when a
  step fails, the steps after it are not sent, so they appear nowhere in the request statistics and
  the failure rate understates how many user journeys broke; but they did not fail either, so
  counting them as errors would be wrong too.
- **The container image holds only perfmon; the project is mounted.** `perfmon` is the entrypoint, so
  the arguments are the same as on the command line, and exit codes pass through for CI. *Why:* one
  image serves every project, and editing a scenario needs no rebuild. It runs as a non-root user,
  and `host.docker.internal` reaches an API on the machine running Docker.
- **`verify_tls: false` in `project.yaml` skips the certificate check**, for test environments with a
  self-signed certificate. It is off unless set, the commands print a note when it is used, and the
  report's Settings sheet records it. *Why in the project file and not a command-line flag:* it is a
  property of the environment being tested, and it should be visible to whoever reads the project.
- **A trailing slash on `host` is ignored**, since every path starts with one.
- **Exit codes of `perfmon run`:** baseline exits 1 if a target was missed, or if a request failed in a
  step that sets no failure target of its own; limit exits 0 whether or not
  it found the limit, because failures are what it is looking for. 2 is a configuration error.
- **Setup values rank below the iteration's own row:** step vars < setup row and extracts < iteration
  row < iteration extracts. *Why:* the more recent and more specific value wins.
- **Content-Type is guessed from the request file extension** unless `meta.yaml` sets it.
- **Bodies are sent as UTF-8 bytes.** *Why:* `requests` would otherwise encode a `str` body as latin-1.
- **Check mode uses Locust's own HTTP session**, listening to its request event. *Why:* a check sends
  exactly what a load test sends and applies the same pass/fail rule, with one runner for both.
- **Without a `validate` block, Locust's default rule applies** (connection error or status >= 400 fails).
  With one, the block decides, so an expected 404 passes.
- **The project is an installable package** (hatchling) so `perfmon` exists as a command.
- **Commands open a project with `perfmon.project.open_project`**, which loads it and then verifies
  placeholders and JSONPath syntax, reporting every problem at once. `config.loader.load_project` only
  reads files. *Why:* the checks need the protocol handlers and CSV headers, which the config layer
  should not depend on; and a missing variable found before the run costs nothing, while one found
  during a load run raises on every iteration.
- **Config errors exit with one line**, `Configuration error: <file>: <problem>`, instead of a traceback.

### Data and reporting

- **One data row per scenario iteration**, drawn once and shared by all of its steps. *Why:* the steps
  of a chain must see the same user/order/etc.
- **Three data modes: `shared`, `scenario`, `random`.** *Why:* `shared` suits single-use rows (two
  scenarios never get the same row at the same time), `scenario` keeps each scenario's rows stable when
  others are added or removed, and `random` is `shared` over shuffled rows: it avoids cache-friendly, predictable ordering while
  still using every row once before any row repeats.
- **The mode decides which row is drawn, never how it is shared:** in every mode the row is drawn once
  per iteration and shared by all steps of a scenario.
- **Extracted values beat everything else in the context.** *Why:* a value from an earlier response is
  the most recent and most specific thing known about this iteration.
- **A failed step stops the chain.** *Why:* later steps would fail for the same reason and only add
  noise to the statistics.
- **Check mode uses the first data row of each scenario.**
- **Sequential modes wrap at the end of the file.** *Why:* the simplest way to keep runs consistent
  and repeatable.
- **Single-process first.** The cursor sits behind `DataSource` so distributed runs can be added later.
- **Reporters receive a `RunSummary`, not Locust's statistics.** *Why:* a reporter then needs to know
  nothing about Locust, can be tested with hand-made data, and the terminal output, the spreadsheet
  and a future LGTM exporter all describe the same numbers.
- **The console is always on; file reporters are opt-in with `--report`.**
- **Measurements are our own, gathered per step, per level of load and per time slice.** *Why:* Locust's
  statistics are cumulative for the whole run, which cannot show which endpoint slowed down at which
  load. Response times are counted per rounded value (two to three significant digits), so percentiles
  are slightly rounded and memory stays flat however long the run is.
- **Targets are separate from `stop_when`.** Targets say what is good enough (the contract);
  `stop_when` says when a limit run should give up. A limit run reports both: up to which load the
  targets held, and where the API gave way.
- **Charts never share two scales on one axis.** Measures in different units get a chart each, side by
  side, with the same x axis. Colours come from a fixed set checked for colour-blind separation; every
  chart's numbers are also in a table sheet.
- **A chart shows at most six lines** (the slowest steps); the rest are in the tables.
- **Excel first for reporting.** The LGTM transport question is deferred. *Why:* the strategy interface
  isolates it; only the two-hook shape has to be right now.
- **Subset lists are compared from the start.** The expected items must match the first items of the
  response in order; the response may have more after them. *Why:* it is the list equivalent of "may
  have extra keys" and lets a test pin down the first entries of a long list.
- **Differences name their place** (`$.rating.average expected 5, got 4.4`), the first three are listed.
  *Why:* a failure should say what to fix without opening the response.
- **Booleans never equal numbers** in comparisons, although `true == 1` in Python.
- **Validation is optional per endpoint** (omit `validate:`). In limit tests prefer status-only or `subset`.
  *Why:* deep comparison costs CPU on the load generator and can skew timings.

## File format reference

```yaml
# project.yaml (optional)
name: shop                             # in reports; default is the folder name
host: https://api.example.com
targets: { p95_ms: 800, error_percent: 1 }   # for every endpoint; also p99_ms
verify_tls: false                      # only for a test environment with a self-signed certificate
vars: { tenant: acme }                 # lowest precedence
modes:
  baseline: { users: 1, duration: 60s, pacing: 1 }
  limit:
    start_users: 5
    step_users: 5
    max_users: 100
    step_duration: 30s
    pacing: 1
    stop_when: { error_percent: 5, p95_ms: 1000 }
```

```yaml
# endpoints/create_order/meta.yaml
path: /customers/{{customer}}/orders   # required
method: POST                           # default GET
protocol: rest                         # default rest
query: { expand: "{{expand}}" }          # a null value is not sent
headers: { Authorization: "Bearer {{token}}", X-Api-Key: "{{$env.API_KEY}}" }
extract: { order_id: $.id }            # JSONPath into the response, for later steps
validate: { status: 201, body: subset } # body: none | subset | exact, compared with response.*
targets: { p95_ms: 300 }               # overrides the project's targets, key by key
vars: { quantity: 1 }
```

```yaml
# scenarios/order_flow.yaml
weight: 3
setup:                                 # once per virtual user; or a plain list of steps
  data: data/users.csv
  steps: [login]
data: data/orders.csv                  # or { file: ..., mode: shared | scenario | random, seed: 1 }
vars: { currency: DKK }
steps:
  - endpoint: create_order
    name: big_order                    # label in reports; default is the endpoint name
    vars: { quantity: 500 }
  - get_order
```

## Running

```fish
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run perfmon check --root Example
uv run perfmon run --root Example                 # baseline
uv run perfmon run --root Example --mode limit
uv run perfmon run --root Example --mode limit --report excel   # also writes reports/<name>.xlsx
```

In a container (the project folder is mounted read-only at `/project`; `PERFMON_PROJECT` picks it,
default `./Example`; an optional `.env` file supplies `{{$env.NAME}}` values):

```fish
docker compose build
docker compose run --rm perfmon check
docker compose run --rm perfmon run --mode limit --report excel   # written to ./reports
PERFMON_PROJECT=./ExampleFailing docker compose run --rm perfmon check
docker run --rm -v "$PWD/Example:/project:ro" perfmon check        # without compose
```
