"""Shared services for the dispatch system — path bootstrap."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # project root
for _p in (ROOT, ROOT / "core", ROOT / "research", ROOT / "dispatch"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
