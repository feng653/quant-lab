"""
Strategy registry — standardized algorithm module interface + auto-discovery.

A strategy is registered in ONE place (its own module under core/strategies/)
via the @register_strategy decorator. The dispatch system discovers all
strategies by scanning this package — drop a new file in and it appears in
the web admin automatically.

Two strategy kinds:
  - signal strategies: provide f(pivot, params) -> {date_str: [signals]}
  - ML strategies: no signal func; walk-forward engine trains ml_model_type
    ("lgb"|"xgb"|"lstm"|"transformer"|"gbr") on factor data

Per-strategy execution params (rebalance_days, max_positions) are part of the
spec, so e.g. daily-rebalancing strategies coexist with monthly ones.

Runtime enable/params overrides live in dispatch/state/strategy_config.json.
"""

from __future__ import annotations

import importlib
import json
import logging
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = PROJECT_ROOT / "dispatch" / "state" / "strategy_config.json"

REGISTRY: dict[str, "StrategySpec"] = {}
_scanned = False


@dataclass
class StrategySpec:
    key: str
    label: str
    category: str                      # technical | portfolio | factor | ml
    desc: str = ""
    signal_func: Callable | None = None
    ml_model_type: str | None = None   # lgb | xgb | lstm | transformer | gbr
    feature_set: str = "basic8"        # basic8 (8因子) | alpha13 (GBR 13维特征)
    param_schema: dict[str, dict] = field(default_factory=dict)
    enabled_by_default: bool = True
    rebalance_days: int = 30
    max_positions: int = 20
    note: str = ""

    def default_params(self) -> dict[str, Any]:
        return {k: v.get("default") for k, v in self.param_schema.items()}


def register_strategy(key: str, label: str, category: str, desc: str = "",
                      params: dict[str, dict] | None = None,
                      enabled_by_default: bool = True,
                      rebalance_days: int = 30, max_positions: int = 20,
                      note: str = ""):
    """Decorator for signal strategies: f(pivot, params) -> {date_str: [...]}"""
    def deco(func):
        REGISTRY[key] = StrategySpec(
            key=key, label=label, category=category, desc=desc,
            signal_func=func, param_schema=params or {},
            enabled_by_default=enabled_by_default,
            rebalance_days=rebalance_days, max_positions=max_positions, note=note)
        return func
    return deco


def register_ml_strategy(key: str, label: str, ml_model_type: str, category: str = "ml",
                         desc: str = "", params: dict[str, dict] | None = None,
                         enabled_by_default: bool = True,
                         rebalance_days: int = 30, max_positions: int = 20,
                         feature_set: str = "basic8", note: str = "") -> None:
    """Register an ML strategy (signals produced by the walk-forward engine)."""
    REGISTRY[key] = StrategySpec(
        key=key, label=label, category=category, desc=desc,
        signal_func=None, ml_model_type=ml_model_type, feature_set=feature_set,
        param_schema=params or {}, enabled_by_default=enabled_by_default,
        rebalance_days=rebalance_days, max_positions=max_positions, note=note)


def scan_strategies(force: bool = False) -> dict[str, StrategySpec]:
    """Import every module under core.strategies subpackages → decorators fire."""
    global _scanned
    if _scanned and not force:
        return REGISTRY
    import core.strategies as pkg
    for sub in ("technical", "portfolio", "factor", "ml"):
        try:
            subpkg = importlib.import_module(f"core.strategies.{sub}")
        except ImportError:
            continue
        for m in pkgutil.iter_modules(subpkg.__path__):
            if m.name.startswith("_"):
                continue
            try:
                importlib.import_module(f"core.strategies.{sub}.{m.name}")
            except Exception as e:
                logger.error("Strategy module import failed %s.%s: %s", sub, m.name, e)
    _scanned = True
    logger.info("Registry scan: %d strategies discovered", len(REGISTRY))
    return REGISTRY


def rescan() -> dict[str, StrategySpec]:
    """Force re-import of all strategy modules (picks up newly added files)."""
    global _scanned
    _scanned = False
    return scan_strategies(force=True)


# ────────────────────────── runtime config (enable + params) ──────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def is_enabled(key: str) -> bool:
    cfg = load_config()
    if key in cfg and "enabled" in cfg[key]:
        return bool(cfg[key]["enabled"])
    spec = REGISTRY.get(key)
    return spec.enabled_by_default if spec else False


def set_enabled(key: str, enabled: bool, note: str | None = None) -> None:
    cfg = load_config()
    entry = cfg.setdefault(key, {})
    entry["enabled"] = enabled
    if note is not None:
        entry["note"] = note
    save_config(cfg)


def get_params(key: str) -> dict[str, Any]:
    """Spec defaults merged with user overrides."""
    spec = REGISTRY.get(key)
    params = spec.default_params() if spec else {}
    cfg = load_config().get(key, {})
    params.update(cfg.get("params", {}))
    return params


def set_params(key: str, params: dict[str, Any]) -> None:
    cfg = load_config()
    entry = cfg.setdefault(key, {})
    entry.setdefault("enabled", is_enabled(key))
    entry["params"] = params
    save_config(cfg)


def get_enabled_strategies() -> list[str]:
    scan_strategies()
    return [k for k in REGISTRY if is_enabled(k)]


def get_spec(key: str) -> StrategySpec | None:
    scan_strategies()
    return REGISTRY.get(key)
