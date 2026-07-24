"""
Alpha158 factor strategy — XGBoost ranking.

Source: microsoft/qlib ★ 46.6k
Logic: Same pipeline as LightGBM, using XGBoost as the ranking model.
        Useful as a benchmark comparison against LGB.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd

from config.settings import config as cfg
from strategies.base import BaseStrategy, StrategyMeta
from strategies.factor.alpha158 import QLIB_DATA_DIR
from strategies.stars_tags import STRATEGY_MAP

logger = logging.getLogger(__name__)


class Alpha158XGBStrategy(BaseStrategy):
    meta = STRATEGY_MAP["alpha158_xgb"]

    def __init__(self, pool_name: str = "csi800", n_estimators: int = 200, learning_rate: float = 0.05, max_depth: int = 6) -> None:
        super().__init__(pool_name)
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.meta.params = {"n_estimators": n_estimators, "learning_rate": learning_rate, "max_depth": max_depth}

    def prepare_data(self, df: pd.DataFrame) -> None:
        self.raw_df = df.copy()

    def generate_signals(self) -> dict[str, list[dict[str, Any]]]:
        import qlib
        from qlib.config import REG_CN
        from qlib.contrib.model.gbdt import XGBModel
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP

        provider_uri = str(QLIB_DATA_DIR / "cn_data")
        qlib.init(provider_uri=provider_uri, region=REG_CN)

        dataset = DatasetH(
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
                "train": (cfg.period.train_start, cfg.period.train_end),
                "valid": (cfg.period.backtest_start, cfg.period.backtest_end),
                "test": (cfg.period.backtest_start, cfg.period.backtest_end),
            },
        )

        model = XGBModel(
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            n_estimators=self.n_estimators,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=1.0,
            reg_lambda=1.0,
            nthread=os.cpu_count() or 4,
            early_stopping_rounds=20,
            eval_metric="rmse",
            verbosity=0,
        )
        model.fit(dataset)
        preds = model.predict(dataset)

        return self._predictions_to_signals(preds)

    def _predictions_to_signals(self, pred_df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
        signals: dict[str, list[dict[str, Any]]] = {}
        top_frac = 0.10
        dates = pred_df.index.get_level_values("datetime").unique()
        score_col = pred_df.columns[0]
        for dt in dates:
            day_preds = pred_df.loc[pd.IndexSlice[dt, :]]
            if isinstance(day_preds, pd.Series):
                day_preds = day_preds.to_frame()
            day_preds = day_preds.sort_values(score_col, ascending=False)
            n_top = max(1, int(len(day_preds) * top_frac))
            top_codes = day_preds.head(n_top).index.get_level_values("instrument").tolist()
            d = str(dt.date())
            for code in top_codes:
                signals.setdefault(d, []).append({"code": code, "action": "buy", "weight": 1.0 / n_top})
        return signals
