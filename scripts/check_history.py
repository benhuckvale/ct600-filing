#!/usr/bin/env python3
"""Check that no personal or company identifiers appear in git history.

Usage:
    git log -p | python scripts/check_history.py

Reads sensitive values from .env and returns/*.yaml, then scans stdin
for any matches. Reports the surrounding diff context for each hit.
"""
import os
import sys
import glob
import yaml
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Values that are intentionally public or are placeholders in the template
DUMMY = {
    "dummy", "0000", "", "yes", "no", "Director", "Secretary", "Company",
    "ct600-filing", "Other - PDF attached with explanation",
    "Micro-entity accounts filed separately with Companies House.",
    # Generic, public company classifications — these are taxonomy enumeration
    # values (not personal identifiers), and appear as mapping keys in the code.
    "Private limited company", "Public limited company",
    "Company limited by guarantee", "Limited liability partnership",
    "England and Wales", "England", "Wales", "Scotland", "Northern Ireland",
}


def load_env(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            val = val.strip()
            if val and val not in DUMMY:
                values[key.strip()] = val
    return values


def load_returns(directory: Path) -> dict[str, str]:
    values = {}
    for path in directory.glob("return-*.yaml"):  # skip return.yaml template
        try:
            data = yaml.safe_load(path.read_text())
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        def collect(d: dict, prefix: str = "") -> None:
            import re
            for k, v in d.items():
                key = f"{prefix}{k}"
                if isinstance(v, dict):
                    collect(v, key + ".")
                elif isinstance(v, str) and v not in DUMMY and len(v) > 3:
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                        continue  # plain date — not an identifier
                    values[f"{path.name}:{key}"] = v
                elif isinstance(v, (int, float)):
                    pass  # figures are not identifiers

        collect(data)
    return values


def main() -> None:
    env_values = load_env(ROOT / ".env")
    # Only scan returns/*.yaml — the root return.yaml is a template with placeholder values
    return_values = load_returns(ROOT / "returns")

    all_secrets: dict[str, str] = {**env_values, **return_values}

    if not all_secrets:
        print("No sensitive values found in .env or returns/ — nothing to check.")
        sys.exit(0)

    print(f"Checking for {len(all_secrets)} sensitive value(s)...\n")

    text = sys.stdin.read()
    lines = text.splitlines()

    found_any = False
    for label, secret in all_secrets.items():
        hits = [i for i, line in enumerate(lines) if secret in line]
        if hits:
            found_any = True
            print(f"FOUND  [{label}] = {secret[:4]}{'*' * (len(secret) - 4)}")
            for i in hits[:3]:
                ctx_start = max(0, i - 2)
                ctx_end = min(len(lines), i + 3)
                for j, line in enumerate(lines[ctx_start:ctx_end], ctx_start):
                    marker = ">>>" if j == i else "   "
                    print(f"  {marker} {line[:120]}")
            if len(hits) > 3:
                print(f"       ... and {len(hits) - 3} more occurrence(s)")
            print()

    if found_any:
        print("ACTION REQUIRED: sensitive values found in git history.")
        sys.exit(1)
    else:
        print("Clean — no sensitive values found in git history.")
        sys.exit(0)


if __name__ == "__main__":
    main()
