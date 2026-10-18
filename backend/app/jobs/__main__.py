"""`python -m app.jobs once|loop` (see app/jobs/runner.py)."""
from __future__ import annotations

import asyncio
import sys

from app.jobs.runner import main

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if mode not in ("once", "loop"):
        raise SystemExit("usage: python -m app.jobs once|loop")
    try:
        asyncio.run(main(mode))
    except KeyboardInterrupt:
        pass
