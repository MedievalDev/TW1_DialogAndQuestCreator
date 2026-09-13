"""Start TW1 Quest Creator (QuestForge 2) without a console window.

Double click this file, or run ``py -3.12 -m questforge2`` from this folder.
It is also the entry script of the exe build (build_exe.spec).
"""

import os
import sys
import time

_T0 = time.perf_counter()
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from questforge2.app import main  # noqa: E402

main(start_time=_T0)
