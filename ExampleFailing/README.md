# Example project: what failures look like

Every scenario here fails on purpose, to show how each kind of failure is reported.
It only sends GET requests to <https://sampleapis.com/>.

```fish
uv run perfmon check --root ExampleFailing
```

The command exits with code 1 and prints:

```
broken_chain
  FAIL  GET https://api.sampleapis.com/beers/ale  [200, 383 ms]
        extract 'brewery_id': $[0].brewery.id matched nothing in the response
  SKIP  get_beer  (an earlier step failed)
too_strict
  FAIL  GET https://api.sampleapis.com/beers/ale/1  [200, 156 ms]
        body: $.image is not expected; $.name is not expected; $.price is not expected (and 1 more)
wrong_status
  FAIL  GET https://api.sampleapis.com/beers/ale/0  [404, 158 ms]
        expected status 200, got 404
wrong_value
  FAIL  GET https://api.sampleapis.com/beers/ale/1  [200, 161 ms]
        body: $.name expected "Not The Real Name", got "Founders All Day IPA"; $.rating.stars is missing

0 passed, 4 failed, 1 skipped
```

| Scenario | Shows |
|----------|-------|
| `wrong_value` | `body: subset` with a wrong value and a missing key; each difference names its place |
| `too_strict` | `body: exact` reporting keys the response has but the file does not; only the first three are listed |
| `wrong_status` | a status mismatch, checked before the body |
| `broken_chain` | an `extract` that finds nothing fails the step, and the rest of the chain is skipped |

## A missed target

`project.yaml` here sets a p95 target of 1 ms, which nothing can meet. A baseline run reports every
step as having missed it and exits with code 1:

```fish
uv run perfmon run --root ExampleFailing wrong_status too_strict
```
