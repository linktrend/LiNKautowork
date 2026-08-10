#!/usr/bin/env python3
"""Executable entrypoint for the IDE Development v2 installer.

Usage examples:
  python3 scripts/ide-development.py version --json
  python3 scripts/ide-development.py plan --target /path/to/repo --package /path/to/system --json
  python3 scripts/ide-development.py install --target /path/to/repo --dry-run --json
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ide_development.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
