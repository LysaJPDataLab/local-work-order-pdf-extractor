from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".example"}

# General leakage patterns only: no company-specific keywords or identifiers are
# embedded in this checker, so the checker itself remains safe to publish.
CHECKS = {
    "absolute Windows user path": re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+"),
    "email address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "GitHub token-like string": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "private-key header": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def main() -> int:
    errors: list[str] = []
    for path in iter_files():
        rel = path.relative_to(ROOT)
        if path.suffix.lower() == ".pdf":
            errors.append(f"PDF found in public source tree: {rel}")
            continue
        if path.suffix.lower() in {".csv", ".xlsx", ".xls", ".parquet"}:
            errors.append(f"Data file found in public source tree: {rel}")
            continue
        if path.name.lower() in {".env", "credentials", "secrets.json"}:
            errors.append(f"Sensitive configuration file found: {rel}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore", ".gitattributes"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            errors.append(f"Could not inspect text file: {rel}")
            continue
        for label, pattern in CHECKS.items():
            if pattern.search(content):
                errors.append(f"Possible {label} in {rel}")

    if errors:
        print("Public release check FAILED:")
        for error in errors:
            print(f" - {error}")
        return 1
    print("Public release check passed: no common private artifacts or leakage patterns found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
