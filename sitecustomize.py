"""Start coverage in subprocesses when COVERAGE_PROCESS_START is set.

Imported by Python at interpreter startup when this directory is on the
subprocess PYTHONPATH (see tests/conftest.py run_cli). A no-op otherwise.
"""

from __future__ import annotations

import os

if os.environ.get("COVERAGE_PROCESS_START"):
    import coverage

    coverage.process_startup()
