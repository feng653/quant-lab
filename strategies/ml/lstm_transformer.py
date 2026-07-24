"""
LSTM ranking strategy (GPU-accelerated).

Source: microsoft/qlib ★ 46.6k
Logic: Alpha158 factors → LSTM sequential model → stock ranking.
        Uses PyTorch backend; automatically detects CUDA availability.

GPU: Set device='cuda' to leverage NVIDIA GPU for training.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from config.settings import config as cfg
from strategies.base import BaseStrategy, StrategyMeta
from strategies.factor.alpha158 import QLIB_DATA_DIR
from strategies.stars_tags import STRATEGY_MAP

logger = logging.getLogger(__name__)


class LSTMStrategy(BaseStrategy):
    meta = STRATEGY_MAP["lstm_rank"]

    def __init__(
        self,
        pool_name: str = "csi800",
        d_feat: int = 20,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.0,
        n_epochs: int = 100,
        lr: float = 0.001,
        early_stop: int = 10,
        device: str = "cpu",
    ) -> None:
        super().__init__(pool_name)
        self.d_feat = d_feat
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.n_epochs = n_epochs
        self.lr = lr
        self.early_stop = early_stop
        self.device = device
        self.meta.params = {
            "d_feat": d_feat, "hidden_size": hidden_size, "num_layers": num_layers,
            "dropout": dropout, "n_epochs": n_epochs, "lr": lr, "device": device,
        }

    def prepare_data(self, df: pd.DataFrame) -> None:
        self.raw_df = df.copy()

    def generate_signals(self) -> dict[str, list[dict[str, Any]]]:
        import torch
        import qlib
        from qlib.config import REG_CN
        from qlib.contrib.model.pytorch_lstm import LSTM
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP

        provider_uri = str(QLIB_DATA_DIR / "cn_data")
        qlib.init(provider_uri=provider_uri, region=REG_CN)

        if self.device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available, falling back to CPU")
            self.device = "cpu"

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

        model = LSTM(
            d_feat=self.d_feat,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
            n_epochs=self.n_epochs,
            lr=self.lr,
            early_stop=self.early_stop,
            batch_size=2000,
            metric="loss",
            loss="mse",
            optimizer="adam",
            GPU=1 if self.device == "cuda" else 0,
            seed=42,
        )
        model.fit(dataset)
        preds = model.predict(dataset)

        signals: dict[str, list[dict[str, Any]]] = {}
        top_frac = 0.10
        dates = preds.index.get_level_values("datetime").unique()
        score_col = preds.columns[0]
        for dt in dates:
            day_preds = preds.loc[pd.IndexSlice[dt, :]]
            if isinstance(day_preds, pd.Series):
                day_preds = day_preds.to_frame()
            day_preds = day_preds.sort_values(score_col, ascending=False)
            n_top = max(1, int(len(day_preds) * top_frac))
            top_codes = day_preds.head(n_top).index.get_level_values("instrument").tolist()
            d = str(dt.date())
            for code in top_codes:
                signals.setdefault(d, []).append({"code": code, "action": "buy", "weight": 1.0 / n_top})
        return signals
