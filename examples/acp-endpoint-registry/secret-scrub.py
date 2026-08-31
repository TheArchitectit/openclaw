#!/usr/bin/env python3
"""Example secret scanner for launcher/registry checkout hygiene.

Fail-closed pre-commit / pre-PR gate for self-hosted endpoint registries and
the files around them. Accepts either mode:
  --scan [PATHS...]     scan given paths (or tracked git files when omitted)
  --check-config FILE   validate a registry:
                          - no inline key material anywhere in the file
                          - every apiKeyRef is a path reference, not a literal
                          - the key file exists and is mode 0600
                          - an in-repo key file is ignored by git

Exits non-zero on any finding. Intended for pre-commit hooks, CI lint jobs,
and manual pre-PR checks; it is an example, not product code.
"""

import argparse
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

# Token-shaped literals that must never appear in tracked files.
# Entry point for local extensions: append (compiled_regex, label) pairs.
PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "OpenAI-style key"),
    (re.compile(r"\bah-[A-Za-z0-9]{24,}\b"), "self-hosted gateway key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"\bgsk_[A-Za-z0-9_-]{10,}\b"), "Groq key"),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"), "Google key"),
    (re.compile(r"\bpplx-[A-Za-z0-9_-]{10,}\b"), "Perplexity key"),
    (re.compile(r"\bhf_[A-Za-z0-9]{10,}\b"), "HuggingFace token"),
    (re.compile(r"\bnpm_[A-Za-z0-9]{10,}\b"), "npm token"),
    (
        re.compile(
            r"(?i)\b(?:api[_-]?key|auth[_-]?token|access[_-]?token|"
            r"client[_-]?secret|token|secret|password|passwd|credential)"
            r"[\"']?\s*[:=]\s*[\"'][^\"']{20,}[\"']"
        ),
        "generic credential literal",
    ),
]

TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".ts", ".json", ".md", ".sh", ".bash", ".txt",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".example",
}


def fail(message: str) -> None:
    print(f"secret-scrub: FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def is_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    try:
        chunk = path.read_bytes()[:2048]
        return b"\x00" not in chunk
    except OSError:
        return False


def tracked_files(repo_root: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files"],
            capture_output=True, text=True, check=True,
        ).stdout
        return [repo_root / line for line in out.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, OSError):
        return []


def gitignored(root: Path, target: Path) -> bool:
    try:
        rel = target.resolve().relative_to(root.resolve())
    except ValueError:
        return True  # outside the repo cannot be tracked; safe by construction
    out = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", str(rel)],
        capture_output=True,
    )
    return out.returncode == 0


def expand_paths(paths: list[Path]) -> list[Path]:
    """Expand directories recursively into the files beneath them.

    A supplied directory is walked (symlinks not followed, .git skipped) so
    `--scan examples/` inspects the tree it names instead of reporting a
    misleading zero-file success. A supplied path that does not exist is a
    hard error: a typo'd path must not produce a green 0-scan result.
    """
    missing = [p for p in paths if not p.exists()]
    if missing:
        fail("no such path (nothing was scanned): " + ", ".join(str(m) for m in missing))
    files: list[Path] = []
    for path in paths:
        if path.is_dir() and not path.is_symlink():
            for root, dirs, names in os.walk(path):
                dirs[:] = [d for d in dirs if d != ".git"]
                for name in names:
                    files.append(Path(root) / name)
        else:
            files.append(path)
    # De-duplicate while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def scan(paths: list[Path], repo_root: Path) -> None:
    if not paths:
        paths = tracked_files(repo_root)
    paths = expand_paths(paths)
    findings: list[tuple[str, str]] = []
    checked = 0
    for path in paths:
        if not path.is_file() or not is_text(path):
            continue
        checked += 1
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for pattern, label in PATTERNS:
            if pattern.search(text):
                findings.append((str(path), label))
    if findings:
        for path, label in findings:
            print(f"secret-scrub: FAIL {path}: {label}", file=sys.stderr)
        raise SystemExit(1)
    print(f"secret-scrub: OK ({checked} text files scanned, 0 findings)")


def check_config(config_path: Path, repo_root: Path) -> None:
    import json

    if not config_path.is_file():
        fail(f"missing config file: {config_path}")
    try:
        config = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot parse {config_path}: {exc}")

    adapters = config.get("adapters")
    if not isinstance(adapters, dict) or not adapters:
        fail("config has no adapters map")

    for name, entry in sorted(adapters.items()):
        if not isinstance(entry, dict):
            fail(f"adapters.{name} must be an object")
        # No key material anywhere in the config itself.
        raw = json.dumps(entry)
        for pattern, label in PATTERNS:
            if pattern.search(raw):
                fail(f"adapters.{name} contains inline {label}")
        key_ref = entry.get("apiKeyRef")
        if not isinstance(key_ref, str) or not key_ref.strip():
            fail(f"adapters.{name}.apiKeyRef is missing")
        # apiKeyRef must be a path reference, not a literal secret.
        stripped = key_ref.strip()
        if not (
            "/" in stripped or stripped.startswith("~") or stripped.endswith(".key")
        ):
            fail(f"adapters.{name}.apiKeyRef ('{stripped}') does not look like a path")
        key_path = Path(stripped).expanduser()
        if not key_path.is_absolute():
            key_path = (config_path.parent / key_path).resolve()
        if not key_path.is_file():
            fail(f"adapters.{name}: key file missing: {key_path}")
        mode = stat.S_IMODE(key_path.stat().st_mode)
        if mode & 0o077:
            fail(
                f"adapters.{name}: key {key_path} is group/other readable "
                f"(mode {oct(mode)}; run chmod 600)"
            )
        if not gitignored(repo_root, key_path):
            fail(
                f"adapters.{name}: key {key_path} is inside the repo tree and NOT "
                f"gitignored — it could be committed"
            )
        print(f"secret-scrub: adapters.{name} OK (key={key_path}, mode={oct(mode)})")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", nargs="*", default=None, metavar="PATH")
    group.add_argument("--check-config", metavar="FILE")
    args = parser.parse_args()
    if args.scan is not None:
        paths = [Path(p) for p in (args.scan or [])]
        scan(paths, repo_root)
    else:
        check_config(Path(args.check_config).expanduser(), repo_root)


if __name__ == "__main__":
    main()
