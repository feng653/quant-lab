"""
Alpha158 factor strategy — LightGBM ranking.

Source: microsoft/qlib ★ 46.6k
Logic: Use Qlib's Alpha158 factor set to train LightGBM,
        predict next-period returns, buy top-ranked stocks.

GPU: LightGBM is primarily CPU-based; GPU build is optional.
      For daily-frequency A-share data, CPU suffices.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config.settings import config as cfg
from strategies.base import BaseStrategy, StrategyMeta
from strategies.stars_tags import STRATEGY_MAP

logger = logging.getLogger(__name__)

QLIB_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "qlib_data"


class Alpha158LGBStrategy(BaseStrategy):
    meta = STRATEGY_MAP["alpha158_lgb"]

    def __init__(self, pool_name: str = "csi800", n_estimators: int = 200, learning_rate: float = 0.05) -> None:
        super().__init__(pool_name)
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.meta.params = {"n_estimators": n_estimators, "learning_rate": learning_rate}

    def prepare_data(self, df: pd.DataFrame) -> None:
        self.raw_df = df.copy()

    def _build_qlib_dataset(self) -> None:
        """Convert raw OHLCV data to Qlib binary format."""
        import qlib
        from qlib.config import REG_CN
        from qlib.data import D
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP

        provider_uri = str(QLIB_DATA_DIR / "cn_data")
        qlib.init(provider_uri=provider_uri, region=REG_CN)

        train_period = (cfg.period.train_start, cfg.period.train_end)
        valid_period = (cfg.period.backtest_start, cfg.period.backtest_end)
        test_period = (cfg.period.backtest_start, cfg.period.backtest_end)

        self.dataset = DatasetH(
            handler=DataHandlerLP(
                instruments="csi800" if self.pool == "csi800" else "csi500",
                start_time=cfg.period.train_start,
                end_time=cfg.period.backtest_end,
                freq="day",
                infer_processors=[
                    {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
                    {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
                ],
            ),
            segments={
                "train": train_period,
                "valid": valid_period,
                "test": test_period,
            },
        )

    def generate_signals(self) -> dict[str, list[dict[str, Any]]]:
        import lightgbm as lgb
        import qlib
        from qlib.contrib.model.gbdt import LGBModel

        self._build_qlib_dataset()

        model = LGBModel(
            loss="mse",
            colsample_bytree=0.8,
            learning_rate=self.learning_rate,
            subsample=0.8,
            lambda_l1=1.0,
            lambda_l2=1.0,
            num_leaves=64,
            num_threads=os.cpu_count() or 4,
            early_stopping_rounds=20,
            num_boost_round=self.n_estimators,
            verbose_eval=50,
        )

        model.fit(self.dataset)
        predictions = model.predict(self.dataset)

        return self._predictions_to_signals(predictions)

    def _predictions_to_signals(self, pred_df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
        """Convert Qlib prediction scores to buy signals — top 10% each period."""
        from config.settings import config

        signals: dict[str, list[dict[str, Any]]] = {}
        top_frac = 0.10

        dates = pred_df.index.get_level_values("datetime").unique()
        for dt in dates:
            day_preds = pred_df.loc[pd.IndexSlice[dt, :]]
            if isinstance(day_preds, pd.Series):
                day_preds = day_preds.to_frame()

            if "score" not in day_preds.columns and len(day_preds.columns) > 0:
                score_col = day_preds.columns[0]
            else:
                score_col = "score" if "score" in day_preds.columns else day_preds.columns[0]

            day_preds = day_preds.sort_values(score_col, ascending=False)
            n_top = max(1, int(len(day_preds) * top_frac))
            top_codes = day_preds.head(n_top).index.get_level_values("instrument").tolist()

            d = str(dt.date())
            for code in top_codes:
                signals.setdefault(d, []).append({"code": code, "action": "buy", "weight": 1.0 / n_top})

        return signals
