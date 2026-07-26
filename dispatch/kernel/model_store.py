"""Model persistence for walk-forward training.

Each model is keyed by (scope, strategy, params_hash, retrain_date),
written to ``state/models/``. The same key that identifies the signal cache
also identifies its backing model — so eviction rules are consistent.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent / "state" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def save_model(model, strategy: str, params: dict, retrain_date: str,
               data_ver: str = "", code_ver: str = "",
               n_samples: int = 0, feature_list: list[str] | None = None,
               scope: str = "research") -> None:
    """Persist trained model + metadata to disk."""
    ph = _phash(params)
    model_dir = MODEL_DIR / scope / strategy / ph
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / f"{retrain_date}.pkl"
    meta_path = model_dir / f"{retrain_date}.json"

    try:
        import joblib
        joblib.dump(model, model_path)
    except Exception:
        import pickle
        with open(model_path, "wb") as f:
            pickle.dump(model, f)

    meta_path.write_text(json.dumps({
        "retrain_date": retrain_date,
        "params_hash": ph,
        "data_version": data_ver,
        "code_version": code_ver,
        "n_samples": n_samples,
        "features": feature_list or [],
    }, ensure_ascii=False, indent=2))
    logger.info("Saved model: %s/%s/%s/%s", scope, strategy, ph, retrain_date)


def load_model(strategy: str, params: dict, retrain_date: str,
               scope: str = "research"):
    """Load a cached model, or None if not found."""
    ph = _phash(params)
    model_path = MODEL_DIR / scope / strategy / ph / f"{retrain_date}.pkl"
    if not model_path.exists():
        return None

    logger.info("Loading cached model: %s/%s/%s/%s", scope, strategy, ph, retrain_date)
    try:
        import joblib
        return joblib.load(model_path)
    except Exception:
        import pickle
        with open(model_path, "rb") as f:
            return pickle.load(f)


def _phash(params: dict) -> str:
    s = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(s.encode()).hexdigest()[:8]
