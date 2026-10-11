# Example project: sampleapis.com

A small project against <https://sampleapis.com/> that touches each feature.

| Name | Kind | Shows |
|------|------|-------|
| `list_beers` | endpoint | path variable, `extract`, status validation |
| `get_beer` | endpoint | CSV data, templated expected response, `body: subset` |
| `find_coffee` | endpoint | query string, `standalone: false` |
| `create_coffee` | endpoint | a JSON request body with placeholders, a built-in (`{{$isotime}}`), a list variable |
| `delete_coffee` | endpoint | `DELETE` with a path variable |
| `browse_beers` | scenario | chaining: `list_beers` feeds `beer_id` to `get_beer` |
| `coffee_break` | scenario | per-step `vars` overrides |
| `coffee_lifecycle` | scenario | a request with a body; scenario `vars` shared by both steps; cleans up after itself |
| `get_stout` | scenario | a variant: the `get_beer` endpoint reused with a different style |

Run it from the repository root. First a functional check (each scenario once), then a small load run:

```fish
uv run perfmon check --root Example --host https://api.sampleapis.com
PERFMON_ROOT=Example uv run locust --headless -u 2 -t 10s --host https://api.sampleapis.com
```

Name scenarios after `locust` to run only those, e.g. `uv run locust browse_beers get_stout ...`.

sampleapis.com is a free public service: keep the user count and duration low. Its data
is shared by everyone, so the only scenario that writes (`coffee_lifecycle`) deletes what it creates;
follow the same pattern if you add another.

`validate.status` is applied. `extract`, `data` and `validate.body` are read from the files but not
applied yet (steps 4 and 5 in `TODO.md`), so for now `get_beer` always fetches `beer_id: 1`.

A load run that stops between the two steps of `coffee_lifecycle` leaves one entry behind.
Remove it by repeating this until it answers 404:

```fish
curl -X DELETE https://api.sampleapis.com/coffee/hot/990001
```
