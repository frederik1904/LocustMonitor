# Example project: secrets from the environment

`{{$env.NAME}}` reads the environment variable `NAME`, so tokens and keys stay out of the
YAML and CSV files. The one endpoint here sends an `X-Api-Key` header taken from
`SAMPLE_API_KEY` (sampleapis.com ignores the header; it is only there to show the mechanism).

Without the variable, nothing is sent and the command exits with code 2:

```fish
uv run perfmon check --root ExampleSecrets
```

```
Configuration error: ExampleSecrets: endpoint 'get_beer': the environment variable SAMPLE_API_KEY is not set
```

With it, the check passes:

```fish
env SAMPLE_API_KEY=demo-key uv run perfmon check --root ExampleSecrets
```
