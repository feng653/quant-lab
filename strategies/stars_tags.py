"""
Star-tagging registry — maps every strategy to its open-source provenance.

All star counts verified against GitHub as of July 2026.
"""

from strategies.base import StrategyMeta

STRATEGY_CATALOG: list[StrategyMeta] = [
    # ── Technical strategies (ported from je-suis-tm/quant-trading) ──
    StrategyMeta(
        name="ma_cross",
        source_project="je-suis-tm/quant-trading",
        source_stars=10400,
        category="technical",
        description="Dual moving average crossover — buys when short MA crosses above long MA",
    ),
    StrategyMeta(
        name="rsi_reversal",
        source_project="je-suis-tm/quant-trading",
        source_stars=10400,
        category="technical",
        description="RSI mean-reversion — buys at oversold (RSI<30), sells at overbought (RSI>70)",
    ),
    StrategyMeta(
        name="bollinger_breakout",
        source_project="je-suis-tm/quant-trading",
        source_stars=10400,
        category="technical",
        description="Bollinger Band breakout — enters on band penetration, exits on middle reversion",
    ),
    StrategyMeta(
        name="macd_signal",
        source_project="je-suis-tm/quant-trading",
        source_stars=10400,
        category="technical",
        description="MACD golden/death cross — DIF crossing DEA with histogram confirmation",
    ),
    # ── Factor strategies (inspired by Qlib Alpha158) ──
    StrategyMeta(
        name="alpha158_lgb",
        source_project="microsoft/qlib",
        source_stars=46600,
        category="factor",
        description="Alpha158 factors + LightGBM ranking — Qlib's standard ML pipeline",
        paper_ref="Yang et al. (2020) arXiv:2009.11189",
    ),
    StrategyMeta(
        name="alpha158_xgb",
        source_project="microsoft/qlib",
        source_stars=46600,
        category="factor",
        description="Alpha158 factors + XGBoost ranking — alternative tree model benchmark",
    ),
    # ── ML strategies (deep models from Qlib model zoo) ──
    StrategyMeta(
        name="lstm_rank",
        source_project="microsoft/qlib",
        source_stars=46600,
        category="ml",
        description="Alpha158 factors + LSTM (GPU-accelerated) — recurrent deep model for stock ranking",
    ),
    StrategyMeta(
        name="transformer_rank",
        source_project="microsoft/qlib",
        source_stars=46600,
        category="ml",
        description="Alpha158 factors + Transformer (GPU-accelerated) — attention-based deep model",
    ),
    # ── Portfolio strategies ──
    StrategyMeta(
        name="pairs_trading",
        source_project="je-suis-tm/quant-trading",
        source_stars=10400,
        category="portfolio",
        description="Pairs trading via cointegration — spread deviation → entry, reversion → exit",
    ),
    StrategyMeta(
        name="risk_parity",
        source_project="robertmartin8/PyPortfolioOpt",
        source_stars=4800,
        category="portfolio",
        description="Risk Parity portfolio — equal risk contribution from each position, monthly rebalance",
    ),
]

STRATEGY_MAP: dict[str, StrategyMeta] = {m.name: m for m in STRATEGY_CATALOG}
