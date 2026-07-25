"""AlphaMaster GBR Rank — migrated from project3 (alphamaster+agent).

13-dim cross-section features + GradientBoostingRegressor ranking, TopK=30.
Original: github.com/rosemarycox5334-debug/AlphaMaster (AGPL-3.0), A-share
pipeline in project3 claimed Sharpe 3.12 — but its backtest traded at the
same close whose features generated the signal (implicit look-ahead) and
used 0.03% commission with daily full rebalancing.

Here it runs under quant-lab's strict execution semantics:
signals T-1 → execution T close, commission 0.1% + stamp 0.1% + slippage 0.1%.
Default rebalance_days=1 reproduces the original daily rebalancing; compare
with rebalance_days=30 in the validation report (research/docs/GBR_VALIDATION.md).
"""

from core.strategies.registry import register_ml_strategy

register_ml_strategy(
    key="alphamaster_gbr", label="AM GBR", ml_model_type="gbr", category="factor",
    desc="AlphaMaster迁移: 13维特征+GBDT排序 TopK30 月频调仓",
    feature_set="alpha13",
    rebalance_days=30, max_positions=30,
    note="project3迁移策略。验证显示选股有真实alpha(月频Sharpe 0.944), 但原版日频调仓在真实成本下亏损-75.6%, 故默认月频。详见 research/docs/GBR_VALIDATION.md",
    params={
        "retrain_every": {"type": "int", "default": 30, "min": 5, "max": 63, "desc": "重训间隔(交易日)"},
        "top_k": {"type": "int", "default": 30, "min": 5, "max": 100, "desc": "入选股票数"},
        "train_window": {"type": "int", "default": 200, "min": 60, "max": 500, "desc": "训练窗口(交易日)"},
        "horizon": {"type": "int", "default": 1, "min": 1, "max": 20, "desc": "标签-前向收益天数"},
        "n_estimators": {"type": "int", "default": 40, "min": 10, "max": 200, "desc": "树数量"},
        "max_depth": {"type": "int", "default": 3, "min": 2, "max": 8, "desc": "最大深度"},
        "learning_rate": {"type": "float", "default": 0.05, "min": 0.01, "max": 0.3, "desc": "学习率"},
        "subsample": {"type": "float", "default": 0.6, "min": 0.3, "max": 1.0, "desc": "子采样"},
    },
)
