# PerformanceMonitor (`perfmon`)

`perfmon` tests HTTP APIs from plain files. You describe each endpoint in a folder (some YAML,
a request template, an expected response) and combine endpoints into scenarios. The same files
then serve three purposes:

| Command | Question it answers |
|---------|---------------------|
| `perfmon check` | Does every scenario work? One pass, no load, pass or fail per step. |
| `perfmon run` | How fast is the API under normal use? A steady, light load (baseline). |
| `perfmon run --mode limit` | How much load can it take? Load raised in steps until it gives way. |

Load is generated with [Locust](https://locust.io/), but you never write Locust code.

**Contents**

- [Quick start](#quick-start)
- [Concepts](#concepts)
- [Project layout](#project-layout)
- [Endpoints](#endpoints)
- [Scenarios](#scenarios)
- [Placeholders](#placeholders)
- [Chaining requests](#chaining-requests)
- [Checking responses](#checking-responses)
- [Test data](#test-data)
- [Project settings](#project-settings)
- [Running](#running)
- [Reports](#reports)
- [Targets](#targets)
- [Running in a container](#running-in-a-container)
- [Editor support](#editor-support)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [For developers](#for-developers)

## Quick start

You need Python 3.14 or newer and [uv](https://docs.astral.sh/uv/). Docker is an alternative; see
[Running in a container](#running-in-a-container).

```sh
uv sync                                                    # install perfmon and its dependencies
uv run perfmon check --root Example                        # run every example scenario once
uv run perfmon run --root Example                          # baseline: 10 seconds of light load
uv run perfmon run --root Example --mode limit --report excel   # limit test, with a workbook in reports/
```

`Example/` is a complete project against the public <https://sampleapis.com/> API. Reading its
files next to this document is the fastest way to learn the formats. There are two more:
`ExampleFailing/` shows what every kind of failure looks like, and `ExampleSecrets/` shows how to
pass a secret from the environment.

## Concepts

| Term | Meaning |
|------|---------|
| **Project** | A folder with `endpoints/`, `scenarios/` and optionally `project.yaml` and data files. |
| **Endpoint** | One API operation: method, path, headers, an optional request body and expected response. A building block; it never runs on its own. |
| **Scenario** | A list of endpoints called in order. Scenarios are what you run. |
| **Step** | One endpoint inside a scenario, optionally with its own name and values. |
| **Iteration** | One pass through a scenario's steps. |
| **Virtual user** | A simulated client that repeats one scenario, one iteration after another. It has its own HTTP session (cookies, connections) and never has two requests in flight. |
| **Setup** | Steps a virtual user runs once before its first iteration, typically a login. |

## Project layout

```
my-project/
  project.yaml               # optional: host, shared values, targets, mode settings
  endpoints/
    login/
      meta.yaml              # required: what to call and what to expect
      request.json           # optional: the request body, with {{placeholders}}
      response.json          # optional: the expected response body
    create_order/
      meta.yaml
      request.json
  scenarios/
    order_flow.yaml          # runs login, then create_order
  data/
    users.csv                # optional: rows of values for placeholders
```

- Folder names under `endpoints/` are the endpoint names. File names under `scenarios/` (without
  the extension) are the scenario names.
- `.yaml` and `.yml` are both accepted.
- A request or response file may have any extension (`request.json`, `request.xml`, ...), but a
  folder may hold only one of each.

## Endpoints

`endpoints/<name>/meta.yaml`:

```yaml
path: /customers/{{customer_id}}/orders     # required
method: POST                                # default GET
query:
  expand: "{{expand}}"                      # ?expand=...; left out when the value is null
headers:
  Authorization: "Bearer {{token}}"
extract:
  order_id: $.id                            # take values from the response for later steps
validate:
  status: 201
  body: subset                              # none | subset | exact
targets:
  p95_ms: 300                               # see Targets
vars:
  expand: null                              # default values for this endpoint's placeholders
```

| Key | Default | Meaning |
|-----|---------|---------|
| `path` | required | URL path, appended to the host. |
| `method` | `GET` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD` or `OPTIONS`. |
| `protocol` | `rest` | The API style. Only `rest` exists today. |
| `query` | none | Query string parameters. A parameter whose value is null is not sent. |
| `headers` | none | Request headers. A header whose value is null is not sent. |
| `extract` | none | Variable name to [JSONPath](#chaining-requests) into the response. |
| `validate` | none | [Checks on the response](#checking-responses). |
| `targets` | project's | [What counts as good enough](#targets) for this endpoint. |
| `vars` | none | Default values for placeholders used by this endpoint. |

**Request body.** Put it in `request.<ext>` next to `meta.yaml`. The `Content-Type` header is
derived from the extension (`request.json` gives `application/json`) unless you set the header
yourself. Bodies are sent as UTF-8.

```json
{
  "customer": "{{customer_id}}",
  "quantity": {{quantity}},
  "note": "{{note}}"
}
```

## Scenarios

`scenarios/<name>.yaml`:

```yaml
weight: 3                        # how often this scenario is picked in a limit run; default 1
setup:                           # optional: once per virtual user
  data: data/users.csv
  steps: [login]
data: data/orders.csv            # optional: one row per iteration
vars:
  currency: DKK                  # values for every step of this scenario
steps:
  - endpoint: create_order
    name: big_order              # optional label in reports
    vars: { quantity: 500 }      # values for this step only
  - get_order                    # short form: just the endpoint name
```

| Key | Default | Meaning |
|-----|---------|---------|
| `steps` | required | Endpoints to call, in order, on every iteration. |
| `setup` | none | Steps run once per virtual user. Either a list of steps, or a mapping with `steps` and `data`. |
| `data` | none | A [data file](#test-data) giving one row per iteration, shared by all steps. |
| `vars` | none | Values for placeholders in every step. |
| `weight` | `1` | Share of virtual users this scenario gets in a limit run. |

**Steps.** A step is either an endpoint name or a mapping with `endpoint` and optionally `name`
and `vars`. Reports label every request `scenario/step`. A step is named after its endpoint unless
you give it a `name`; an endpoint used more than once without a name is numbered (`find`,
`find#2`, `find#3`). Setup steps are labelled `scenario/setup/step`.

**A failed step ends the iteration.** The remaining steps are not sent. `check` lists them as
`SKIP`; load runs count them as "steps not sent".

**Variants.** To run the same endpoint with other values or data, write another small scenario
that reuses it. `Example/scenarios/get_stout.yaml` is `get_beer` with a different style.

**Setup.** Use it for whatever a user does once, such as logging in. The setup's data row and the
values its steps extract are available in every iteration of that user. Without setup, a chain
that starts with `login` logs in on every iteration, and the load test hammers the login endpoint.
A user whose setup fails stops.

## Placeholders

`{{name}}` is replaced by a value in `path`, `query`, `headers`, the request file and the response
file. `{{user.id}}` reads a field of a value, and `{{items.0}}` an item of a list.

**Where values come from.** When the same name is defined in several places, the one further down
this list wins:

1. `vars` in `project.yaml`
2. `vars` in the endpoint's `meta.yaml`
3. `vars` in the scenario
4. `vars` on the step
5. the setup's data row, then the values the setup extracted
6. the iteration's data row
7. values extracted from earlier responses in the same iteration

**Built-in values**

| Placeholder | Value |
|-------------|-------|
| `{{$uuid}}` | A new random UUID each time. |
| `{{$timestamp}}` | The current time as whole seconds since 1970. |
| `{{$isotime}}` | The current time in ISO 8601, UTC. |
| `{{$env.NAME}}` | The environment variable `NAME`. Use it for secrets, so they are not written in files. |

**Rules**

- **A missing value is an error, never an empty string.** It is caught before anything is sent.
- **Null means "leave it out".** When a value is null (YAML `null`, or an empty CSV cell), the
  thing it fills is removed: the query parameter, the header, or the JSON key or list item. This
  is how one endpoint serves both "with" and "without" an optional field.
- **Null only works for a whole value.** In `path`, or inside a longer string such as
  `Bearer {{token}}`, a null value is an error.
- **In JSON files, text inside quotes is escaped.** `"note": "{{note}}"` stays valid JSON when the
  note contains quotes or line breaks.
- **Outside quotes, the value is inserted as it is.** `"quantity": {{quantity}}` gives a number,
  also when the value came from a CSV file as text. Lists and booleans are written as JSON.
- **To send an explicit JSON `null`,** write `null` in the request file itself.

## Chaining requests

`extract` reads values from a response so later steps can use them:

```yaml
# endpoints/login/meta.yaml
method: POST
path: /login
extract:
  token: $.access_token
  user_id: $.user.id
```

```yaml
# endpoints/get_orders/meta.yaml
path: /users/{{user_id}}/orders
headers:
  Authorization: "Bearer {{token}}"
```

The expressions are [JSONPath](https://github.com/h2non/jsonpath-ng#jsonpath-syntax): `$.id`,
`$.user.id`, `$[0].id`, `$.items[2].name`. The first match is used. An expression that matches
nothing fails the step, which ends the iteration.

## Checking responses

Without a `validate` block, a step fails on a connection error or an HTTP status of 400 or above.
With one, the block decides, so an endpoint that is expected to answer 404 can pass.

```yaml
validate:
  status: 201
  body: subset
```

| `body` | The response passes when |
|--------|--------------------------|
| `none` (default) | Always; only the status is checked. |
| `subset` | Everything in the response file is in the response. The response may have more keys, and lists may have more items after the expected ones. |
| `exact` | The response equals the response file. |

- The response file may use placeholders, with the same values the request was built from.
- A null value leaves its key out of the expectation.
- The status is checked first; the body only if the status is right.
- A failure names the place: `body: $.rating.average expected 5, got 4.4; $.name is missing`.
- **Limit runs ignore `body`** and judge on the status alone. Comparing bodies costs CPU on the
  load generator exactly when it is needed for load.

## Test data

A data file is a CSV with a header row. Each column name becomes a placeholder; each row is one
set of values. An empty cell is null.

```csv
username,password,note
ada,secret1,
bob,secret2,second account
```

```yaml
data: data/users.csv                              # short form, mode shared
data: { file: data/users.csv, mode: random, seed: 7 }
```

A scenario draws one row per iteration, and every step of that iteration sees the same row.

| `mode` | Which row comes next |
|--------|----------------------|
| `shared` (default) | The next row of the file. All scenarios using the file share one position, so two never get the same row at the same time until the file wraps. |
| `scenario` | The next row, counted separately for this scenario. |
| `random` | Like `shared`, with the rows shuffled once at the start. `seed` makes the order repeatable. |

All modes start over at the end of the file. `perfmon check` uses the first row only.

## Project settings

`project.yaml` is optional. Every key has a default.

```yaml
name: shop                       # in reports and report file names; default is the folder's name
host: https://api.example.com    # --host overrides it
verify_tls: true                 # false only for a test environment with a self-signed certificate
vars:
  tenant: acme                   # values for every scenario; anything more specific wins
targets:
  p95_ms: 800                    # see Targets
  error_percent: 1
modes:
  baseline:
    users: 1                     # virtual users per scenario
    duration: 60s                # seconds, or 30s / 5m / 1h
    pacing: 1                    # seconds from the start of one iteration to the start of the next
  limit:
    start_users: 5               # virtual users in the first step, across all scenarios
    step_users: 5                # added in each further step
    max_users: 100               # give up looking beyond this
    step_duration: 30s
    pacing: 1
    stop_when:
      error_percent: 5           # stop when more than this share of a step's requests fail
      p95_ms: 1000               # stop when a step's p95 exceeds this; not set by default
```

The values shown for `modes` are the defaults, except `stop_when.p95_ms`, which has none.

## Running

```sh
perfmon check [scenario ...] [--root DIR] [--host URL]
perfmon run   [scenario ...] [--root DIR] [--host URL] [--mode baseline|limit]
              [--report excel] [--report-dir DIR]
```

- `--root` is the project folder; the default is the current directory.
- Naming scenarios runs only those; the default is all of them.
- Prefix the commands with `uv run` unless the virtual environment is activated.

Before anything is sent, the whole project is verified: unknown keys, unknown endpoints, missing
data files, placeholders that nothing supplies, invalid JSONPath and unset environment variables
are all reported together, each with its file or scenario and step.

### `check`: does it work?

Runs each scenario once, with full response checks.

```
browse_beers
  PASS  GET https://api.sampleapis.com/beers/ale  [200, 632 ms]
  PASS  GET https://api.sampleapis.com/beers/ale/4  [200, 134 ms]
wrong_value
  FAIL  GET https://api.sampleapis.com/beers/ale/1  [200, 161 ms]
        body: $.name expected "Not The Real Name", got "Founders All Day IPA"
broken_chain
  FAIL  GET https://api.sampleapis.com/beers/ale  [200, 383 ms]
        extract 'brewery_id': $[0].brewery.id matched nothing in the response
  SKIP  get_beer  (an earlier step failed)
```

### `run`: baseline

A fixed number of virtual users per scenario, at a steady pace, for a fixed time. Use it to learn
normal response times and to check them against targets.

```
Baseline: 1 user(s) per scenario, 3 scenario(s), for 10 s
Every target was met (6 step(s) with targets).

Step                         Requests  Failed %  p50 ms  p95 ms  p99 ms  Max ms  Targets
GET browse_beers/get_beer          11       0.0     140     377     377     377  met
GET browse_beers/list_beers        11       0.0     260     680     680     685  met
...

Scenario      Iterations  Incomplete  Incomplete %  Steps not sent  Iteration p50 ms  p95 ms
browse_beers          11           0           0.0               0               400     820
```

### `run --mode limit`: how much can it take?

Virtual users are added in steps, shared between the scenarios by `weight`. Each step is judged on
the requests made during it. The run stops at the first step that crosses `stop_when`, or at
`max_users`.

```
Limit: from 50 to at most 1000 users in steps of 50, 20 s per step
     50 users: 50.0 req/s, 0.0% failed, p50 97 / p95 180 / p99 360 ms, 0 of 1000 iterations incomplete
    ...
    700 users: 491.3 req/s, 1.1% failed, p50 1100 / p95 2700 / p99 3300 ms, 110 of 9826 iterations incomplete
Limit reached at 700 users: p95 was 2700 ms (threshold 2000 ms); the last healthy step was 650 users.
```

### Reading the numbers

- **Users are not requests per second.** A user starts one iteration every `pacing` seconds, and
  waits for each response before sending the next request. Ten users at `pacing: 1` running a
  three-step scenario send about 30 requests per second while the API keeps up.
- **Load backs off when the API slows down.** Once an iteration takes longer than `pacing`, a user
  cannot keep its rate. Compare intended and achieved iterations per second in the report.
- **p50 / p95 / p99** are the response times that 50%, 95% and 99% of requests stayed within. They
  are rounded to two or three significant digits.
- **Incomplete iterations** stopped at a failed step. **Steps not sent** are the requests that were
  therefore never made. They are not failures and are not part of the failure rate, but they do
  mean that fewer user journeys completed than the failure rate alone suggests.
- **In a chain, the first endpoint to give way decides the result.** A slow step throttles the
  steps after it, and a failed step hides them. To find one endpoint's limit, give it its own
  scenario and put what it needs first in `setup`.
- **The load generator runs on one CPU core.** At several hundred requests per second it can
  become the bottleneck itself. If achieved load stops following intended load, check the CPU of
  the `perfmon` process before blaming the API.

### Exit codes

| Code | `check` | `run` baseline | `run --mode limit` |
|------|---------|----------------|--------------------|
| 0 | every step passed | targets met and no unexpected failures | always, when the run completed |
| 1 | a step failed or was skipped | a target was missed, or a request failed in a step with no `error_percent` target | never |
| 2 | the project has a problem | the project has a problem | the project has a problem |

A limit run exits 0 whether or not it found the limit, because failures are what it is looking for.

## Reports

`perfmon run` always prints its tables. `--report excel` also writes a workbook to
`reports/<project>-<mode>-<start time in UTC>.xlsx` (`--report-dir` or `PERFMON_REPORT_DIR` change
the folder). Two real ones are in `Example/`.

| Sheet | Contents |
|-------|----------|
| **Dashboard** | Key facts, the findings as sentences, and charts. Prints one page wide. |
| **Load steps** (limit) | Per level of load: requests/s, intended and achieved iterations/s, failed %, p50/p95/p99/max, iterations, incomplete, targets met, verdict. |
| **Steps by load** (limit) | Every step at every level of load. Shows which endpoint bends first. |
| **Steps** | Whole-run numbers per step, with its targets and whether they were met. |
| **Iterations** | Per scenario: iterations, incomplete, steps not sent, users stopped in setup, and how long a complete iteration took. |
| **Failures** | Kind, status code, count, message, and when and at how many users each was first seen. |
| **Timeline** | Users, requests/s, failed %, p50 and p95 over the run. |
| **Settings** | How the run was configured. |

Dashboard charts for a limit run: response time by load, failed requests and incomplete iterations
by load, intended against achieved iterations per second, and p95 by load for the slowest steps.
For a baseline: p95 per step beside its target. For both: response time, requests per second and
failed % over the run.

Failure kinds are `no response` (connection error or timeout), `unexpected status`,
`body mismatch` and `extract failed`.

## Targets

Targets say what is good enough. Set defaults for every endpoint in `project.yaml` and override
them, key by key, in an endpoint's `meta.yaml`:

```yaml
# project.yaml
targets:
  p95_ms: 800
  error_percent: 1
```

```yaml
# endpoints/export/meta.yaml: allowed to be slower; the failure target still applies
targets:
  p95_ms: 5000
```

| Key | The target is met when |
|-----|------------------------|
| `p95_ms` | 95% of the requests took no longer than this many milliseconds. |
| `p99_ms` | 99% of the requests took no longer than this many milliseconds. |
| `error_percent` | No more than this percentage of the requests failed. |

- Every report says per step whether its targets were met, and by how much they were missed.
- A baseline run exits 1 when a target is missed, so it can gate a pipeline.
- A limit run says up to which load the targets held ("Every target was met up to 300 users"),
  next to where the API gave way. Targets and `stop_when` are separate: targets are the contract,
  `stop_when` is when to stop looking.

## Running in a container

The image contains only `perfmon`; your project folder is mounted into it.

```sh
docker compose build
docker compose run --rm perfmon check
docker compose run --rm perfmon run --mode limit --report excel    # written to ./reports
PERFMON_PROJECT=./my-project docker compose run --rm perfmon check
```

- `PERFMON_PROJECT` chooses the project folder (default `./Example`). It is mounted read-only.
- Reports are written to `./reports` on your machine.
- Put values for `{{$env.NAME}}` in a `.env` file, one `NAME=value` per line. It is ignored by git.
- An API on your own machine is reachable as `http://host.docker.internal:<port>`.
- Exit codes pass through, so the commands work in a pipeline.

Without compose:

```sh
docker run --rm -v "$PWD/my-project:/project:ro" -v "$PWD/reports:/reports" perfmon run --report excel
```

## Editor support

`schemas/` holds JSON Schema files for `meta.yaml`, scenario files and `project.yaml`. With them an
editor completes keys and values, shows a description on hover, and underlines mistakes.

- **IntelliJ / PyCharm:** the mappings are in `.idea/jsonSchemas.xml`. If a file shows no schema in
  the status bar, add it under *Settings > Languages & Frameworks > Schemas and DTDs > JSON Schema
  Mappings*.
- **VS Code** (YAML extension): map the schemas in `settings.json`:

  ```json
  "yaml.schemas": {
    "schemas/endpoint.schema.json": "**/endpoints/*/meta.yaml",
    "schemas/scenario.schema.json": "**/scenarios/*.yaml",
    "schemas/project.schema.json": "**/project.yaml"
  }
  ```

Two things the editor flags although `perfmon` accepts them: a lower-case `method: post`, and a
numeric header value such as `X-Version: 2` (quote it).

## Troubleshooting

| Message | Cause and fix |
|---------|---------------|
| `endpoints: directory not found` | `--root` does not point at a project folder. Endpoints must be under `endpoints/<name>/meta.yaml`. |
| `no scenario files (*.yaml) found` | Only scenarios run. Add `scenarios/<name>.yaml` with a `steps:` list. |
| `<key>: unknown key` | A typo, or a key in the wrong file. The message gives the file and the place. |
| `unknown endpoint 'x' (available: ...)` | The step names a folder that does not exist under `endpoints/`. |
| `no vars, data column or earlier extract provides {{x}}` | Nothing gives `x` a value at that step. Add it to `vars`, a CSV column, or an earlier step's `extract`. |
| `the environment variable X is not set` | An endpoint uses `{{$env.X}}`. Export it, or put it in `.env` for the container. |
| `x is null, which can only leave out a whole ...` | A null value is used in `path` or inside a longer string. |
| `validate.body is 'subset' but the folder has no response file` | Add `response.json`, or remove `body:`. |
| `no host; set host in project.yaml or pass --host` | Neither is set. |
| `CERTIFICATE_VERIFY_FAILED` | The API has a certificate that is not trusted. For a test environment with a self-signed certificate, set `verify_tls: false` in `project.yaml`. |
| `extract 'x': ... matched nothing in the response` | The response does not have that field. Run `check` and compare with the actual response. |

## Limitations

- **REST with JSON only.** SOAP and GraphQL are planned; the code is prepared for them.
- **One process, one CPU core.** There are no distributed workers yet.
- **Setup runs once.** If a token expires during a long run, that user's requests fail from then on.
- **`validate.status` takes one code.**
- **Targets belong to an endpoint,** not to a step: every use of the endpoint is judged the same way.
- **`check` uses only the first data row** and has no file report.
- **CSV values are text.** A non-numeric value where JSON needs a number produces an invalid body.
- **Nothing is stored between runs,** so reports do not compare with earlier runs.

`TODO.md` has the full list of planned work, known gaps and the reasons behind the design.

## For developers

### Working on the code

```sh
uv sync                    # includes the dev tools
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run perfmon schema      # regenerate schemas/ after changing perfmon/config/schema.py
```

All four checks must pass before a commit. A test fails when `schemas/` is out of date.

### How the code is organised

```
perfmon/
  cli.py              the perfmon command
  project.py          open a project: load it, then verify it
  template.py         {{placeholder}} rendering, independent of any format
  runner.py           send the steps of a scenario through an HTTP client
  users.py            turn scenarios into Locust user classes
  config/
    schema.py         the file formats, as pydantic models (the single source of truth)
    models.py         what the rest of the code uses: Endpoint, Scenario, Project
    loader.py         folders and files into those models
    json_schema.py    export of the formats for editors
  protocols/          how an API style builds requests and reads responses
    base.py             the ProtocolHandler interface
    rest.py             REST with JSON
    json_template.py    JSON-aware rendering: escaping and leaving out nulls
    json_compare.py     subset and exact comparison
  data/               where rows of values come from
    base.py             the DataSource interface
    csv.py              CSV files
    pool.py             which scenarios share a position in a file
  modes/              ways of running
    check.py            one pass without load
    load.py             the load run, the LoadMode interface, measurement
    baseline.py, limit.py
  reporting/          where results go
    base.py             the Reporter interface
    summary.py          a run as plain data
    console.py, excel.py
```

Two rules hold the structure together:

- **Dependencies point one way, and Locust stays at the edge.** `config`, `template`, `protocols`,
  `data` and `runner` do not import Locust. Only `users.py` and `modes/` do. The core is therefore
  testable without a load test, and `check` and `run` share one runner.
- **Everything that varies is a strategy in its own folder:** an interface in `base.py`, one file per
  implementation, and a registry.

### Extending it

| To add | Do this |
|--------|---------|
| A key in a YAML file | Add a field with a `description` to the model in `config/schema.py`, use it, and run `perfmon schema`. |
| An API style (SOAP, GraphQL) | Add a value to `ApiProtocol`, implement `ProtocolHandler` (`lint`, `prepare`, `check`, `extract`) in `protocols/<name>.py`, and register it in `protocols/__init__.py`. |
| A data source | Implement `DataSource.next_row()` in `data/<name>.py` and choose it in `data/pool.py`. |
| A load mode | Implement `LoadMode` (settings, `drive`) in `modes/<name>.py` and offer it in `cli.py`. A mode is a loop over `begin_step`, `wait`, `end_step`. |
| A report format | Implement `Reporter` (`on_request`, `on_end`) in `reporting/<name>.py` and register it in `reporting/__init__.py` and `REPORT_NAMES` in `cli.py`. |

`Reporter.on_request` is called for every request while the run is going and must return at once.
`on_end` receives a `RunSummary`, which holds everything the built-in reports show and knows nothing
about Locust.

### Conventions

- Every feature ships with an example in one of the example projects, and the example is run.
- `Example/` must always pass. Deliberate failures belong in `ExampleFailing/`.
- Error messages name the file, or the scenario and step, and say what to do.
- Decisions and their reasons are recorded in `TODO.md`.
