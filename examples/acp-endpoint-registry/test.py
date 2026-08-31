#!/usr/bin/env python3
"""Tests for the acp-endpoint-registry example (launcher + secret-scrub).

Run:  python3 examples/acp-endpoint-registry/test.py

Covers:
  - launcher happy path: key-by-reference, env merge, role-slot mapping,
    argument forwarding
  - wrapper-flag stripping (lease-id/value flags and --hide-claude-auth)
  - config validation: unknown adapter, missing model, missing/empty key
  - key permissions: loose mode warns but does not block
  - secret scanner --scan: per-prefix detection + clean-file pass
  - secret scanner --check-config: good config, inline secret, non-path
    apiKeyRef, and key-file permission enforcement
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "launcher.py"
SCRUB = HERE / "secret-scrub.py"
STUB = HERE / "test-stub-adapter.py"
README = HERE / "README.md"

PASS, FAIL = 0, 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"ok - {label}")
    else:
        FAIL += 1
        print(f"NOT OK - {label}")


def write_registry(root: Path, adapters: dict) -> Path:
    config = root / "endpoints.json"
    config.write_text(json.dumps({"adapters": adapters}, indent=2))
    return config


def run_launcher(config: Path, argv: list[str]) -> dict:
    """Run launcher.py against the stub adapter; parse its env dump."""
    env = dict(os.environ)
    env["ACP_REGISTRY_FILE"] = str(config)
    env["ACP_ADAPTER_EXECUTABLE"] = sys.executable
    env["ACP_ADAPTER_PATH"] = str(STUB)
    proc = subprocess.run(
        [sys.executable, str(LAUNCHER), *argv],
        capture_output=True, text=True, env=env,
    )
    stub_env: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if line.startswith("STUB-ENV "):
            key, _, value = line[len("STUB-ENV "):].partition("=")
            stub_env[key] = value
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "env": stub_env,
    }


def make_key(root: Path, name: str, material: str, mode: int = 0o600) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(material)
    os.chmod(path, mode)
    return path


# ---------------------------------------------------------------- happy path
def test_launcher_happy_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_key(root, "keys/claude.key", "test-key-material-not-a-real-secret-0001")
        config = write_registry(root, {
            "claude": {
                "endpoint": "http://endpoint.local:8080",
                "apiKeyRef": "keys/claude.key",
                "model": "default-model",
                "slots": {"haiku": "fast-model", "opus": "heavy-model"},
                "env": {"EXAMPLE_REGISTRY_POLICY": "on"},
            }
        })
        result = run_launcher(config, ["claude", "task", "--verbose"])
        check("launcher exits 0 on happy path", result["returncode"] == 0)
        env = result["env"]
        check("key resolved from file",
              env.get("ANTHROPIC_API_KEY") == "test-key-material-not-a-real-secret-0001")
        check("endpoint applied", env.get("ANTHROPIC_BASE_URL") == "http://endpoint.local:8080")
        check("model applied", env.get("ANTHROPIC_MODEL") == "default-model")
        check("role slot mapped",
              env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL") == "fast-model")
        check("env policy merged", env.get("EXAMPLE_REGISTRY_POLICY") == "on")
        check("args forwarded",
              "task" in result["stdout"] and "--verbose" in result["stdout"])


def test_launcher_strips_wrapper_flags() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_key(root, "keys/claude.key", "test-key-material-not-a-real-secret-0002")
        config = write_registry(root, {
            "claude": {
                "endpoint": "http://endpoint.local:8080",
                "apiKeyRef": "keys/claude.key",
                "model": "m",
            }
        })
        result = run_launcher(config, [
            "claude",
            "--hide-claude-auth",
            "--openclaw-acpx-lease-id", "lease-123",
            "--openclaw-gateway-instance-id", "inst-456",
            "do-work",
        ])
        check("wrapper flags stripped, work arg kept", "do-work" in result["stdout"])
        check("flag values stripped too",
              "lease-123" not in result["stdout"] and "inst-456" not in result["stdout"])
        check("--hide-claude-auth not forwarded",
              "--hide-claude-auth" not in result["stdout"])


# ------------------------------------------------------------ config errors
def test_launcher_config_errors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_key(root, "k.key", "test-key-material-not-a-real-secret-0003")

        missing_adapter = write_registry(root, {"other": {
            "endpoint": "http://e", "apiKeyRef": "k.key", "model": "m"}})
        r = run_launcher(missing_adapter, ["claude"])
        check("unknown adapter fails",
              r["returncode"] != 0 and "unknown adapter" in r["stderr"])

        no_model = write_registry(root, {"claude": {
            "endpoint": "http://e", "apiKeyRef": "k.key"}})
        r = run_launcher(no_model, ["claude"])
        check("missing model fails", r["returncode"] != 0)

        bad_key = write_registry(root, {"claude": {
            "endpoint": "http://e", "apiKeyRef": "missing.key", "model": "m"}})
        r = run_launcher(bad_key, ["claude"])
        check("missing key file fails", r["returncode"] != 0)

        make_key(root, "empty.key", "   \n")
        empty_entry = write_registry(root, {"claude": {
            "endpoint": "http://e", "apiKeyRef": "empty.key", "model": "m"}})
        r = run_launcher(empty_entry, ["claude"])
        check("empty key file fails", r["returncode"] != 0)

        make_key(root, "loose.key", "test-key-material-not-a-real-secret-0004", mode=0o644)
        loose_entry = write_registry(root, {"claude": {
            "endpoint": "http://e", "apiKeyRef": "loose.key", "model": "m"}})
        r = run_launcher(loose_entry, ["claude"])
        check("loose key warns but still execs",
              r["returncode"] == 0 and "group/other readable" in r["stderr"])


# ------------------------------------------------------------- secret scrub
def test_scrub_scan() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for prefix in ("sk-", "ah-", "ghp_", "xoxb-", "hf_", "npm_", "gsk_", "pplx-"):
            leak = Path(tmp) / f"leak-{prefix.strip('-_')}.txt"
            leak.write_text("token " + prefix + "A" * 40)
            r = subprocess.run(
                [sys.executable, str(SCRUB), "--scan", str(leak)],
                capture_output=True, text=True,
            )
            check(f"scan detects {prefix}literal", r.returncode != 0)

        assignment = Path(tmp) / "leak-assign.txt"
        assignment.write_text('api_key = "' + "x" * 40 + '"\n')
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--scan", str(assignment)],
            capture_output=True, text=True,
        )
        check("scan detects generic credential assignment", r.returncode != 0)

        clean = Path(tmp) / "clean.txt"
        clean.write_text("api_key_file = keys/claude.key\n")
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--scan", str(clean)],
            capture_output=True, text=True,
        )
        check("scan passes key reference", r.returncode == 0)


def test_scrub_clean_examples() -> None:
    for name in ("README.md", "endpoints.example.json", "launcher.py", "secret-scrub.py"):
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--scan", str(HERE / name)],
            capture_output=True, text=True,
        )
        check(f"{name} scans clean", r.returncode == 0)


def test_launcher_resolves_bare_executables() -> None:
    """execve() performs no PATH lookup; a bare EXECUTABLE name must resolve.

    The default EXECUTABLE is "node"; without resolution the launcher crashed
    at os.execve (FileNotFoundError) with a valid adapter and registry — the
    test suite missed it because every prior test set ACP_ADAPTER_EXECUTABLE
    to an absolute path.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_key(root, "keys/claude.key", "test-key-material-not-a-real-secret-0007")
        config = write_registry(root, {
            "claude": {
                "endpoint": "http://endpoint.local:8080",
                "apiKeyRef": "keys/claude.key",
                "model": "default-model",
            }
        })
        # A "node" shim that exits 42: proves execve received an absolute path
        # (a bare "node" would raise FileNotFoundError and exit with a traceback).
        bindir = root / "bin"
        bindir.mkdir()
        shim = bindir / "node"
        shim.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
        shim.chmod(0o755)
        env = dict(os.environ)
        env["ACP_REGISTRY_FILE"] = str(config)
        env["ACP_ADAPTER_PATH"] = str(STUB)
        env.pop("ACP_ADAPTER_EXECUTABLE", None)
        env["PATH"] = str(bindir)
        r = subprocess.run(
            [sys.executable, str(LAUNCHER), "claude"],
            capture_output=True, text=True, env=env,
        )
        check("bare executable name resolves via PATH (no execve crash)",
              r.returncode == 42 and "Traceback" not in r.stderr)


def test_scrub_scan_recurses_directories() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nested = root / "pkg" / "deep"
        nested.mkdir(parents=True)
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--scan", str(root / "no-such-dir")],
            capture_output=True, text=True,
        )
        check("nonexistent scan path fails loudly", r.returncode != 0)
        check("nonexistent path message says nothing was scanned",
              "nothing was scanned" in r.stderr)

        (nested / "secret.txt").write_text('api_key = "' + "A" * 40 + '"\n')
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--scan", str(root)],
            capture_output=True, text=True,
        )
        check("scan walks directories recursively", r.returncode != 0)
        check("recursive scan names the nested file", "secret.txt" in r.stderr)

        (nested / "secret.txt").write_text("just notes, nothing secret here\n")
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--scan", str(root)],
            capture_output=True, text=True,
        )
        check("recursive scan passes a clean directory", r.returncode == 0)
        check("recursive scan counts the files it checked", "1 text files scanned" in r.stdout)


def test_launcher_missing_adapter_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_key(root, "keys/claude.key", "test-key-material-not-a-real-secret-0006")
        config = write_registry(root, {
            "claude": {
                "endpoint": "http://endpoint.local:8080",
                "apiKeyRef": "keys/claude.key",
                "model": "default-model",
            }
        })
        env = dict(os.environ)
        env["ACP_REGISTRY_FILE"] = str(config)
        env["ACP_ADAPTER_PATH"] = str(root / "definitely-missing-adapter.js")
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), "claude"],
            capture_output=True, text=True, env=env,
        )
        check("missing adapter exits non-zero before exec", proc.returncode != 0)
        check("missing adapter names the gap", "missing adapter" in proc.stderr)
        check("missing adapter keeps the key out of stderr", "0006" not in proc.stderr)


def test_readme_wiring_matches_acpx_agent_shape() -> None:
    text = README.read_text()
    wiring = None
    for match in re.finditer(r"```json\n(\{.*?\n\})\n```", text, re.S):
        block = json.loads(match.group(1))
        entry = (
            block.get("plugins", {}).get("entries", {}).get("acpx")
        )
        if isinstance(entry, dict) and "agents" in (entry.get("config") or {}):
            wiring = entry["config"]["agents"]["claude"]
            break
    check("README contains the acpx wiring block", wiring is not None)
    if wiring is None:
        return
    check("README wiring uses a single command string",
          isinstance(wiring.get("command"), str) and wiring["command"].strip() != "")
    check("README wiring has no separate args field", "args" not in wiring)


def test_scrub_check_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_key(root, "keys/claude.key", "test-key-material-not-a-real-secret-0005")

        good = write_registry(root, {
            "claude": {
                "endpoint": "http://endpoint.local:8080",
                "apiKeyRef": "keys/claude.key",
                "model": "default-model",
            }
        })
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--check-config", str(good)],
            capture_output=True, text=True, cwd=str(root),
        )
        check("check-config accepts good registry", r.returncode == 0)

        inline = write_registry(root, {
            "claude": {
                "endpoint": "http://endpoint.local:8080",
                "apiKeyRef": "keys/claude.key",
                "model": "m",
                "apiKey": "***" + "B" * 40,
            }
        })
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--check-config", str(inline)],
            capture_output=True, text=True, cwd=str(root),
        )
        check("check-config rejects inline key", r.returncode != 0)

        literal = write_registry(root, {
            "claude": {
                "endpoint": "http://e",
                "apiKeyRef": "literal-secret-value-not-a-path",
                "model": "m",
            }
        })
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--check-config", str(literal)],
            capture_output=True, text=True, cwd=str(root),
        )
        check("check-config rejects non-path apiKeyRef", r.returncode != 0)

        os.chmod(root / "keys/claude.key", 0o644)
        r = subprocess.run(
            [sys.executable, str(SCRUB), "--check-config", str(good)],
            capture_output=True, text=True, cwd=str(root),
        )
        check("check-config rejects loose key file", r.returncode != 0)
        os.chmod(root / "keys/claude.key", 0o600)


if __name__ == "__main__":
    test_launcher_happy_path()
    test_launcher_strips_wrapper_flags()
    test_launcher_config_errors()
    test_launcher_missing_adapter_fails_closed()
    test_launcher_resolves_bare_executables()
    test_readme_wiring_matches_acpx_agent_shape()
    test_scrub_scan()
    test_scrub_scan_recurses_directories()
    test_scrub_clean_examples()
    test_scrub_check_config()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
