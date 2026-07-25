"""Transformer sequence ranking strategy — 2-layer TransformerEncoder."""

from core.strategies.registry import register_ml_strategy

register_ml_strategy(
    key="transformer_rank", label="TF", ml_model_type="transformer", category="ml",
    desc="Transformer序列排序, 每月重训",
    params={
        "retrain_every": {"type": "int", "default": 21, "min": 5, "max": 63, "desc": "重训间隔(交易日)"},
        "top_pct": {"type": "float", "default": 0.1, "min": 0.02, "max": 0.5, "desc": "入选比例"},
        "horizon": {"type": "int", "default": 20, "min": 1, "max": 60, "desc": "标签-前向收益天数"},
        "seq_len": {"type": "int", "default": 10, "min": 5, "max": 30, "desc": "序列长度"},
        "d_model": {"type": "int", "default": 48, "min": 16, "max": 128, "desc": "模型维度"},
        "epochs": {"type": "int", "default": 25, "min": 5, "max": 100, "desc": "训练轮数"},
        "lr": {"type": "float", "default": 0.001, "min": 0.0001, "max": 0.01, "desc": "学习率"},
        "max_train": {"type": "int", "default": 80000, "min": 10000, "max": 300000, "desc": "最大训练样本"},
    },
)
