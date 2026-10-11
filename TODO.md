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
- **Several example folders are fine.** `Example/` targets sampleapis.com; add another folder when a
  feature needs a different kind of package (e.g. a SOAP or GraphQL API, or a local mock server for
  writes and failure cases). Each example folder has its own README.
- **Keep the editor support up to date.** Whenever the file formats change:
  - give every new key a `description` in `perfmon/config/schema.py` (it becomes the hover text),
  - regenerate with `uv run perfmon schema` (a test fails when `schemas/` is out of date),
  - add a mapping in `.idea/jsonSchemas.xml` for any new kind of YAML file (e.g. mode settings in step 6).

## Status

| # | Step | Status |
|---|------|--------|
| 1 | Models, loader, template renderer | Done |
| 2 | REST handler, runner, user factory, locustfile | Done |
| 3 | `check` mode (functional endpoint testing) | Done |
| 4 | Chaining (`extract`) and CSV data source | Todo |
| 5 | Response validation (`subset` / `exact`) | Todo |
| 6 | `baseline` and `limit` modes | Todo |
| 7 | Reporter interface and Excel reporter | Todo |
| 8 | Ergonomics and docs | Todo |
| 9 | Generate endpoint folders from OpenAPI | Todo |

## Todo

### 3. `check` mode (done)

- [x] Run every scenario once, without load, and report pass/fail per step.
- [x] Exit non-zero on any failure so it can run in CI (0 pass, 1 failures, 2 config or usage error).
- [x] Reuse `runner.run_scenario` through Locust's own `HttpSession`.
- [x] Entry point: `uv run perfmon check --root DIR --host URL [scenario ...]`.
- [x] `validate.status` is applied, in check mode and in load runs.

### 4. Chaining and CSV data

- [ ] Add `extract(endpoint, response) -> dict` to `ProtocolHandler`; JSONPath for REST
      (pick a library, e.g. `jsonpath-ng`).
- [ ] Build the per-iteration context in the runner: step vars < data row < extracted values.
- [ ] Create `perfmon/data/` with `base.py` (`DataSource` interface) and `csv.py`.
- [ ] CSV rows: one row per scenario iteration, handed out sequentially, wrapping at the end.
- [ ] A standalone endpoint draws its own row each time it runs.
- [ ] In a scenario, one row is drawn at the start of the iteration and shared by every step in it.
- [ ] Three data modes, as a `DataMode` enum in `schema.py`:
  - `shared` (default): one sequential cursor per CSV file, shared by every scenario that uses the file.
  - `scenario`: each scenario has its own sequential cursor, even on the same file.
  - `random`: like `shared`, but the rows are shuffled once when the file is loaded.
- [ ] `data:` accepts a path (shorthand for `shared`) or `{file: ..., mode: ...}`.
- [ ] Optional seed for the `random` shuffle so a run can be repeated.
- [ ] Fail a chain early (skip remaining steps) when a step fails or an extract finds nothing.
- [ ] Null means omit: a variable that is null (YAML `null`, or an empty CSV cell) removes whatever has
      that placeholder as its whole value:
  - a JSON body key (`"note": {{note}}` or `"note": "{{note}}"`),
  - a header,
  - a query parameter.
- [ ] Add a `query:` mapping to `meta.yaml` so query parameters can be omitted (in `path` they are plain text).
- [ ] A null placeholder inside a longer string or in `path` is an error (nothing sensible to omit).
- [ ] Only parse and re-serialise the body when a null variable is actually present.
- [ ] Example: `browse_beers` passes the extracted `beer_id` on; `coffee_lifecycle` deletes the id returned by the create; `get_beer` reads `data/beer_ids.csv`; one scenario per data mode.
- [ ] Editor support: descriptions for `query` and the `data` mode form; regenerate the schemas.

### 5. Validation

- [x] `check(endpoint, response) -> failure message | None` on `ProtocolHandler` (status only so far).
- [x] Send with `catch_response=True` so validation failures count as Locust failures.
- [ ] Pass the context to `check` so the expected response can be rendered.
- [x] `status`: compare the HTTP status (done in step 3).
- [ ] `body: subset`: every key in `response.*` must be present and equal in the actual response.
- [ ] `body: exact`: full equality.
- [ ] Render `response.*` through the template engine so expected values can use variables.
- [ ] Decide whether to add `body: schema` (JSON Schema) later.
- [ ] Example: `get_beer` and `create_coffee` already declare `body: subset`; add one `body: exact` case and one deliberately failing case to show the report.

### 6. Modes (load shapes)

- [ ] Create `perfmon/modes/` with one `LoadTestShape` per mode.
- [ ] `baseline`: fixed low user count, constant pacing, fixed duration; report p50/p95/p99 per endpoint.
- [ ] `limit`: stepped ramp; stop when error rate or p95 crosses a threshold; report the step where it broke.
- [ ] Decide where mode settings live (users, duration, step size, thresholds), e.g. a `modes.yaml` in the project root.
- [ ] Add user pacing (`wait_time`); today users fire requests back to back.
- [ ] Example: mode settings for `baseline` and `limit` in the example project, with the commands in its README.
- [ ] Editor support: schema and IntelliJ mapping for the mode settings file.

### 7. Reporting

- [ ] Create `perfmon/reporting/` with `base.py` (`Reporter` interface) and `excel.py`.
- [ ] Interface has two hooks: `on_request` (streaming, must not block) and `on_test_end(stats)` (summary).
- [ ] Excel reporter (`openpyxl`): one summary sheet with per-endpoint counts, failures and percentiles.
- [ ] Later: LGTM reporter; decide between Prometheus remote-write, OTLP and Loki at that point.
- [ ] Example: a sample Excel report produced from an example run, with the command in the README.

### 8. Ergonomics and docs

- [ ] Load-time check that every `{{placeholder}}` is supplied by vars, a CSV header or an earlier
      `extract` (today a missing variable only fails at run time).
- [ ] List the allowed keys in "unknown key" errors (lost when moving to pydantic).
- [ ] A single CLI wrapping Locust so `--root` and `--mode` replace the environment variable.
- [ ] README with the file formats.
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
- [ ] Generated endpoints are `standalone: false`: they are building blocks for hand-written scenarios,
      not tests to run on their own.
- [ ] `request.json` / `response.json` from the spec's examples when present.
- [ ] Otherwise build `request.json` from the schema: `$ref` (use a library), `allOf`/`oneOf`/`anyOf`,
      enums, nested and recursive types.
- [ ] Parameters and body fields become `vars`; optional ones default to `null` so they are omitted
      until filled in.
- [ ] Never overwrite: only create folders that do not exist yet.
- [ ] Example: a small OpenAPI file and the folders generated from it, in their own example folder.
- Not generated: real values (which ids exist), chains between endpoints, obtaining auth tokens.
- Out of scope for now: reporting drift when the spec changes; Swagger 2.0.

## Decisions and why

### Project layout on disk

- **Endpoints and scenarios are separate.** `endpoints/<name>/` holds `meta.yaml`, `request.*` and
  `response.*`; `scenarios/<name>.yaml` chains endpoints. *Why:* shared steps such as `login` are not
  copied into every chain, and the same endpoint can be fed different data per scenario.
- **Endpoints are `standalone: true` by default.** A standalone endpoint is also a one-step scenario of
  the same name. *Why:* testing one endpoint should not need a scenario file. Building blocks that only
  work inside a chain set `standalone: false`.
- **Data is bound at the scenario level.** An endpoint may declare a default `data:` for standalone use;
  an explicit scenario uses only its own `data:`. *Why:* inheriting from steps would be ambiguous when
  several steps have defaults.
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
- **Null means omit (planned, step 4).** A null variable drops the JSON key, header or query parameter
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
- **Two layers: "as written" (`schema.py`) and "resolved" (`models.py`).** *Why:* nothing outside `config/`
  sees raw YAML.

### Architecture

- **Dependencies point one way and Locust stays at the edge.** `config`, `template`, `protocols` and
  `runner` do not import Locust; only `users.py`, `locustfile.py` and (later) modes/reporting do.
  *Why:* the core is unit-testable and reusable for `check` mode.
- **One strategy, one folder:** `base.py` holds the interface, one file per implementation, a registry in
  `__init__.py`. *Why:* adding SOAP is one file and one enum value.
- **Folders are created with their first file.** *Why:* no empty packages describing code that does not exist.
- **Protocol handlers own build, extract and validate; the transport is shared HTTP.** *Why:* REST, SOAP
  and GraphQL all travel over HTTP and differ only in how requests are shaped and responses interpreted.
- **Strategies:** `ProtocolHandler` (done for REST), `DataSource`, load mode, `Reporter`.

### Running

- **One Locust user class per scenario**, named after it and weighted by `weight`. *Why:* `locust flow ping`
  selects scenarios, and Locust's own weighting handles the mix.
- **Stats names:** a standalone endpoint reports as `name`; inside a chain as `scenario/name`. *Why:* the
  same endpoint in two scenarios is measured separately.
- **`PERFMON_ROOT` is an environment variable.** *Why:* Locust imports the locustfile
  before parsing its own arguments, and user classes must exist at import.
- **Content-Type is guessed from the request file extension** unless `meta.yaml` sets it.
- **Bodies are sent as UTF-8 bytes.** *Why:* `requests` would otherwise encode a `str` body as latin-1.
- **Check mode uses Locust's own HTTP session**, listening to its request event. *Why:* a check sends
  exactly what a load test sends and applies the same pass/fail rule, with one runner for both.
- **Without a `validate` block, Locust's default rule applies** (connection error or status >= 400 fails).
  With one, the block decides, so an expected 404 passes.
- **The project is an installable package** (hatchling) so `perfmon` exists as a command.
- **Config errors exit with one line**, `Configuration error: <file>: <problem>`, instead of a traceback.

### Data and reporting

- **One data row per scenario iteration.** A standalone endpoint requests its own row each run; in a
  scenario the row is drawn once and shared by all of its steps. *Why:* the steps of a chain must see the
  same user/order/etc., while independent endpoints must not be tied to each other's data.
- **Three data modes: `shared`, `scenario`, `random`.** *Why:* `shared` suits single-use rows (two
  scenarios never get the same row at the same time), `scenario` keeps each scenario's rows stable when
  others are added or removed, and `random` is `shared` over shuffled rows: it avoids cache-friendly, predictable ordering while
  still using every row once before any row repeats.
- **The mode decides which row is drawn, never how it is shared:** in every mode the row is drawn once
  per iteration and shared by all steps of a scenario.
- **Sequential modes wrap at the end of the file.** *Why:* the simplest way to keep runs consistent
  and repeatable.
- **Single-process first.** The cursor sits behind `DataSource` so distributed runs can be added later.
- **Excel first for reporting.** The LGTM transport question is deferred. *Why:* the strategy interface
  isolates it; only the two-hook shape has to be right now.
- **Validation is optional per endpoint** (omit `validate:`). In limit tests prefer status-only or `subset`.
  *Why:* deep comparison costs CPU on the load generator and can skew timings.

## File format reference

```yaml
# endpoints/create_order/meta.yaml
path: /customers/{{customer}}/orders   # required
method: POST                           # default GET
protocol: rest                         # default rest
headers: { Authorization: "Bearer {{token}}" }
extract: { order_id: $.id }            # not applied yet (step 4)
validate: { status: 201, body: subset } # status applied; body not yet (step 5)
standalone: true                       # default true
data: data/users.csv                   # not used yet (step 4)
vars: { quantity: 1 }
```

```yaml
# scenarios/order_flow.yaml
weight: 3
data: data/users.csv
vars: { currency: DKK }
steps:
  - login
  - endpoint: create_order
    vars: { quantity: 2 }
```

## Running

```fish
uv run pytest
uv run perfmon check --root Example --host https://api.sampleapis.com
PERFMON_ROOT=path/to/project uv run locust --headless -u 10 -t 30s --host http://your-api
```
