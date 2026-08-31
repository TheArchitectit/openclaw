#!/usr/bin/env python3
"""Example ACP launcher: endpoint registry + key-by-reference for any harness.

Reads a declarative registry (~/.openclaw/acp/endpoints.json) describing
self-hosted endpoints for ACP harnesses, resolves each endpoint's API key
from a mode-0600 file (never inline, never a shell env var), and execs the
harness adapter with the registry's environment applied.

This file is an example, not product code. It has no hard dependency on
OpenClaw internals: point acpx's custom agent command at it (see
docs/tools/acp-agents-setup.md) or run it directly for testing.
"""

import json
import os
import stat
import sys
from pathlib import Path

ACP_DIR = Path.home() / ".openclaw/acp"
CONFIG_FILE = Path(os.environ.get("ACP_REGISTRY_FILE") or (ACP_DIR / "endpoints.json"))

# CLI exec path used to run the adapter. Override for testing or for adapters
# installed outside the repository checkout.
ADAPTER_OVERRIDE_ENV = "ACP_ADAPTER_PATH"
ADAPTER_DEFAULT = str(Path.home() / ".openclaw/acp/adapters/adapter.js")
EXECUTABLE = os.environ.get("ACP_ADAPTER_EXECUTABLE") or "node"

# Harness-independent wrapper flags that must not reach the adapter CLI.
WRAPPER_VALUE_FLAGS = {
    "--openclaw-acpx-lease-id",
    "--openclaw-gateway-instance-id",
}


def fail(message: str) -> None:
    # On failure nothing about the endpoint (including the key) is printed.
    raise SystemExit(f"acp-launcher: {message}")


def load_registry(config_path: Path) -> dict:
    if not config_path.is_file():
        fail(f"missing registry: {config_path}")
    try:
        return json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {config_path}: {exc}")


def resolve_key_path(ref: str, config_path: Path) -> Path:
    expanded = Path(os.path.expanduser(str(ref)))
    return expanded if expanded.is_absolute() else (config_path.parent / expanded)


def read_key(ref: str, config_path: Path) -> str:
    key_path = resolve_key_path(ref, config_path)
    if not key_path.is_file():
        fail("key file missing")
    value = key_path.read_text().strip()
    if not value:
        fail("key file is empty")
    if stat.S_IMODE(key_path.stat().st_mode) & 0o077:
        print(
            f"acp-launcher: WARNING key file is group/other readable; run "
            f"`chmod 600 {key_path}`",
            file=sys.stderr,
        )
    return value


def load_adapter(config: dict, adapter_id: str, config_path: Path) -> tuple[str, str]:
    adapters = config.get("adapters") if isinstance(config, dict) else None
    if not isinstance(adapters, dict) or adapter_id not in adapters:
        known = ", ".join(sorted(adapters)) if isinstance(adapters, dict) else "none"
        fail(f"unknown adapter '{adapter_id}' (known: {known})")
    entry = adapters[adapter_id]
    if not isinstance(entry, dict) or not all(
        isinstance(entry.get(field), str) and entry.get(field, "").strip()
        for field in ("endpoint", "model", "apiKeyRef")
    ):
        fail(f"adapters.{adapter_id} must set endpoint, model, and apiKeyRef")
    return entry["endpoint"].strip(), entry["model"].strip()


def strip_wrapper_flags(argv: list[str]) -> list[str]:
    forwarded: list[str] = []
    args = iter(argv)
    for arg in args:
        if arg in WRAPPER_VALUE_FLAGS:
            next(args, None)  # drop the flag's value too
        elif arg != "--hide-claude-auth":
            forwarded.append(arg)
    return forwarded


def build_env(entry: dict, key_value: str, endpoint: str, model: str) -> dict:
    """Merge registry env policy, then inject the resolved credentials."""
    env = os.environ.copy()
    for name, value in (entry.get("env") or {}).items():
        if isinstance(name, str) and isinstance(value, str):
            env[name] = value
    env.update(
        {
            "ANTHROPIC_API_KEY": key_value,
            "ANTHROPIC_BASE_URL": endpoint,
            "ANTHROPIC_MODEL": model,
            "CLAUDE_NO_ANALYTICS": "1",
            "CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT": "1",
        }
    )
    # Role-slot mapping: registry keys become the adapter's env controls.
    slots = entry.get("slots")
    if isinstance(slots, dict):
        for slot, slot_model in slots.items():
            if isinstance(slot, str) and isinstance(slot_model, str) and slot_model.strip():
                env[f"ANTHROPIC_DEFAULT_{slot.upper()}_MODEL"] = slot_model.strip()
    return env


def main() -> None:
    # Raw argv parsing, not argparse: adapter arguments routinely carry
    # --flags that argparse would reject as unknown options before they
    # reach the adapter. Format: launcher.py <adapter-id> [adapter args...]
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        raise SystemExit(
            "usage: launcher.py <adapter-id> [adapter args...]\n"
            "example: launcher.py claude --verbose task"
        )
    adapter_id, adapter_argv = argv[0], argv[1:]

    config = load_registry(CONFIG_FILE)
    endpoint, model = load_adapter(config, adapter_id, CONFIG_FILE)
    entry = config["adapters"][adapter_id]
    key_value = read_key(entry["apiKeyRef"], CONFIG_FILE)

    os.execve(
        EXECUTABLE,
        [
            EXECUTABLE,
            os.environ.get(ADAPTER_OVERRIDE_ENV) or ADAPTER_DEFAULT,
            *strip_wrapper_flags(adapter_argv),
        ],
        build_env(entry, key_value, endpoint, model),
    )


if __name__ == "__main__":
    main()
