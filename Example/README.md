# Example project: sampleapis.com

A small project against <https://sampleapis.com/> that touches each feature.

| Name | Kind | Shows |
|------|------|-------|
| `list_beers` | endpoint | path variable, `extract` with JSONPath, status validation |
| `get_beer` | endpoint | two path variables, templated expected response, `body: subset` |
| `find_coffee` | endpoint | `query` parameters |
| `create_coffee` | endpoint | a JSON request body with placeholders, a built-in (`{{$isotime}}`), a list variable, `extract` |
| `delete_coffee` | endpoint | `DELETE` using an extracted value, `body: exact` |
| `get_beer` | scenario | the simplest case: one endpoint with CSV data (`shared` mode) |
| `browse_beers` | scenario | chaining: `list_beers` extracts `beer_id`, `get_beer` uses it |
| `coffee_break` | scenario | per-step `vars`; a null variable leaves a query parameter out |
| `coffee_lifecycle` | scenario | a request with a body; a null variable leaves a body key out; deletes the id the create returned |
| `get_stout` | scenario | a variant of `get_beer`; data in `scenario` mode (its own cursor) |
| `random_beer` | scenario | data in `random` mode with a seed |

Run it from the repository root. First a functional check (each scenario once), then a small load run:

```fish
uv run perfmon check --root Example --host https://api.sampleapis.com
PERFMON_ROOT=Example uv run locust --headless -u 2 -t 10s --host https://api.sampleapis.com
```

Name scenarios after `locust` to run only those, e.g. `uv run locust browse_beers get_stout ...`.

sampleapis.com is a free public service: keep the user count and duration low. Its data
is shared by everyone, so the only scenario that writes (`coffee_lifecycle`) deletes what it creates;
follow the same pattern if you add another.

Every scenario here is meant to pass. `ExampleFailing/` next to this folder shows what failures look like.

A load run that stops between the two steps of `coffee_lifecycle` leaves one entry behind.
Remove it by repeating this until it answers 404:

```fish
curl -X DELETE https://api.sampleapis.com/coffee/hot/990001
```
