"""
Daily simulation engine — deterministic full-window re-simulation.

Compatibility shim: the execution logic moved to ``kernel/sim_engine.py`` with a
parameterized cost model. This module re-exports the old signatures so the
production daily pipeline (sim_runner, daily_recommend, daily_performance) keeps
working without edits.

Behavioral changes: none. The old module constants (COMMISSION, SLIPPAGE, etc.)
are still available and produce identical results to the original code when used
as defaults.
"""

from __future__ import annotations

# re-export everything production code expects
from kernel.sim_engine import (  # noqa: F401
    INITIAL_CASH, COMMISSION, SLIPPAGE, STAMP_DUTY,
    MAX_POS, RB, TARGET_VOL, MIN_EXPOSURE, MAX_EXPOSURE, MODES,
    CostModel, DEFAULT_COSTS,
    simulate_strategy, summary_metrics,
)
