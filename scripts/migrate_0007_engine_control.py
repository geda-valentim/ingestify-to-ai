#!/usr/bin/env python3
"""Create the control-plane schema. Safe on databases not stamped by Alembic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from shared.database import engine
from shared.engine_control.migration import upgrade

if __name__ == "__main__":
    upgrade(engine)
    print(
        "0007 control tables ready; enable ENGINE_CONTROL_ENABLED after configuring executors."
    )
