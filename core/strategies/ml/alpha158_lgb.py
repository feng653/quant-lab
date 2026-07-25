"""Alpha158-style LightGBM walk-forward rank strategy."""

from core.strategies.registry import register_ml_strategy

register_ml_strategy(
    key="alpha158_lgb_wf", label="LGB WF", ml_model_type="lgb", category="ml",
    desc="Walk-Forward, 每月重训, 排名第1",
    params={
        "retrain_every": {"type": "int", "default": 21, "min": 5, "max": 63, "desc": "重训间隔(交易日)"},
        "top_pct": {"type": "float", "default": 0.1, "min": 0.02, "max": 0.5, "desc": "入选比例"},
        "horizon": {"type": "int", "default": 20, "min": 1, "max": 60, "desc": "标签-前向收益天数"},
        "n_estimators": {"type": "int", "default": 150, "min": 50, "max": 500, "desc": "树数量"},
        "learning_rate": {"type": "float", "default": 0.05, "min": 0.01, "max": 0.3, "desc": "学习率"},
        "max_depth": {"type": "int", "default": 6, "min": 2, "max": 12, "desc": "最大深度"},
    },
)
