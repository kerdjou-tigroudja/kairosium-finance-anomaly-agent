"""Point d'entrée Agent Engine — le CLI génère `agent_engine_app.py` avec `from .agent import app`."""

from __future__ import annotations

import sys
from pathlib import Path

# Le runtime charge le bundle sans que la racine projet soit sur sys.path.
_pkg_root = Path(__file__).resolve().parent
_root = str(_pkg_root)
if _root not in sys.path:
    sys.path.insert(0, _root)

from orchestrator.agent import root_agent  # noqa: E402
from orchestrator.app import app  # noqa: E402

__all__ = ["root_agent", "app"]
