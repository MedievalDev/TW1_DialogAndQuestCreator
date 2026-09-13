"""Entry point: ``py -3.12 -m questforge2`` from the repository root."""

import os
import sys
import time

_T0 = time.perf_counter()

# The format modules live in the repository root next to this package.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from questforge2.app import main  # noqa: E402

main(start_time=_T0)
