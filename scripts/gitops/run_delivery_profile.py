#!/usr/bin/env python3
"""Run a declared managed delivery profile without shell interpolation.

The repository may supply ``.github/linktrend-delivery-mode.json``.  Consumers
otherwise use the installed managed default at ``.ide-development/config``.
Both forms must contain a non-empty argv-only profile; missing or malformed
configuration is a gate failure, never a silent skip.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def load_profile(root: Path, profile: str) -> tuple[Path, list[list[str]]]:
    candidates = [
        root / ".github" / "linktrend-delivery-mode.json",
        root / ".ide-development" / "config" / "delivery.json",
    ]
    config_path = next((path for path in candidates if path.is_file()), None)
    if config_path is None:
        raise SystemExit("delivery_profile_config_missing")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        commands = data["profiles"][profile]["commands"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"delivery_profile_config_invalid:{config_path}:{exc}") from exc
    if not isinstance(commands, list) or not commands:
        raise SystemExit(f"delivery_profile_commands_missing:{config_path}:{profile}")
    validated: list[list[str]] = []
    for command in commands:
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
            raise SystemExit(f"delivery_profile_command_invalid:{config_path}:{profile}")
        validated.append(command)
    return config_path, validated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=("fast", "full"))
    args = parser.parse_args()
    root = Path.cwd()
    config_path, commands = load_profile(root, args.profile)
    print(json.dumps({"profile": args.profile, "config": str(config_path), "commands": commands}, sort_keys=True))
    for command in commands:
        subprocess.run(command, cwd=root, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
