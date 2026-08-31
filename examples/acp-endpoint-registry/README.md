# Example: ACP endpoint registry with key-by-reference

A small, self-contained example for pointing OpenClaw's ACP runtime (acpx)
harnesses at self-hosted, Anthropic-compatible endpoints without ever
putting API keys in shell rc files, environment exports, or repo files.

The pattern has three pieces:

| File                     | Purpose                                                                                                         |
| ------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `endpoints.example.json` | Declarative registry: endpoint, key **file reference**, default model, role-slot map, extra env                 |
| `launcher.py`            | Reads the registry, resolves the key from a mode-0600 file, execs the adapter with a clean environment          |
| `secret-scrub.py`        | Fail-closed hygiene gate: scan tracked files for key-shaped literals, or validate a registry (`--check-config`) |

This is an example, not product code: `launcher.py` is harness-agnostic and
has no dependency on OpenClaw internals, so you can adapt it to any adapter
command, not just the `claude` one shown below.

## Why key-by-reference

Self-hosted Anthropic-compatible endpoints make it tempting to export
`ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` in a shell profile. That leaks the
key to every process in the session and every command dump in issue reports.
This example keeps the literal key in exactly one place — a `0600` file — and
references it by path from the registry:

```json
{
  "adapters": {
    "claude": {
      "endpoint": "http://your-anthropic-compatible-endpoint.example:8080",
      "apiKeyRef": "keys/claude.key",
      "model": "your-default-model",
      "slots": { "haiku": "your-fast-model", "sonnet": "your-default-model" },
      "env": { "DISABLE_AUTOUPDATER": "1" }
    }
  }
}
```

`secret-scrub.py --check-config` enforces the invariant fail-closed: no
inline key material in the registry, `apiKeyRef` must be a path, the key file
must exist, must be mode `0600`, and must be either outside the repo or
gitignored.

## Quick start

```sh
mkdir -p ~/.openclaw/acp/keys
cp launcher.py ~/.openclaw/acp/launcher.py
cp endpoints.example.json ~/.openclaw/acp/endpoints.json
printf '%s' 'your-endpoint-key' > ~/.openclaw/acp/keys/claude.key
chmod 600 ~/.openclaw/acp/keys/claude.key
$EDITOR ~/.openclaw/acp/endpoints.json   # point endpoint/model at your setup
python3 secret-scrub.py --check-config ~/.openclaw/acp/endpoints.json
```

Run the example test suite (no network, no real adapter — it stubs the
adapter and asserts the environment the launcher hands over):

```sh
python3 test.py
```

Directory layout used by the defaults (all overridable via env vars):
`~/.openclaw/acp/endpoints.json` for the registry, `keys/` next to it for
key files. `ACP_REGISTRY_FILE` points at a different registry, and
`ACP_ADAPTER_PATH` overrides the adapter command that gets exec'd.

## Wiring it into OpenClaw (acpx)

Set your acpx config's custom agent command for the harness to invoke the
launcher (see [ACP agents — setup](https://docs.openclaw.ai/tools/acp-agents-setup)
for the config surface):

```json
{
  "plugins": {
    "entries": {
      "acpx": {
        "enabled": true,
        "config": {
          "agents": {
            "claude": {
              "command": "python3",
              "args": ["/home/you/.openclaw/acp/launcher.py", "claude"]
            }
          }
        }
      }
    }
  }
}
```

The launcher strips OpenClaw wrapper-only flags before handing arguments to
the adapter, maps role slots to the adapter's environment, and never prints
key material — including on failure paths.

## Hygiene gate

```sh
# scan explicit paths (or all tracked git files when run from a repo)
python3 secret-scrub.py --scan examples/

# validate the live registry + key permissions
python3 secret-scrub.py --check-config ~/.openclaw/acp/endpoints.json
```

Both modes exit non-zero on any finding, which makes them usable as
pre-commit hooks or CI lint steps. The pattern list (OpenAI- and Anthropic-
style keys, GitHub/Slack/Groq/Google/Perplexity/HuggingFace/npm tokens,
private-key blocks, generic `"api_key": "***"` assignments) is a plain list of
`(compiled regex, label)` pairs — extend it for your own token formats.
