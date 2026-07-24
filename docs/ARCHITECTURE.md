# Architecture Documentation

## Overview

This pipeline tests open-source quantitative strategies against Chinese A-share data using a rigorous, survivorship-bias-free backtesting methodology.

## Architecture Layers

```
                   ┌─────────────────────────────────────┐
                   │              main.py                 │
                   │       CLI entry / orchestration       │
                   └────────┬────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
    ┌────▼─────┐      ┌─────▼──────┐     ┌─────▼─────┐
    │  config  │      │    data    │     │ strategies│
    │ settings │      │ pipeline   │     │  4 types  │
    └──────────┘      └─────┬──────┘     └─────┬─────┘
                            │                  │
                     ┌──────▼──────┐    ┌──────▼──────┐
                     │  akshare    │    │  technical  │─ ma_cross, rsi,
                     │  baostock   │    │  factor     │  bollinger, macd
                     │  processor  │    │  ml         │─ alpha158_lgb,
                     │  universe   │    │  portfolio  │  xgb, lstm
                     └─────────────┘    └──────┬──────┘
                                               │ signals
                                        ┌──────▼──────┐
                                        │  backtest   │
                                        │  engine     │─ backtrader + A-share
                                        │  broker     │  rules (T+1, limits)
                                        │  runner     │
                                        └──────┬──────┘
                                               │ results
                                        ┌──────▼──────┐
                                        │ evaluation  │
                                        │ metrics     │─ Sharpe, Calmar, MDD
                                        │ report      │─ Markdown + HTML
                                        │ comparison  │─ cross-strategy rank
                                        └──────┬──────┘
                                               │
                                        ┌──────▼──────┐
                                        │ execution   │
                                        │ paper_vnpy  │─ Local paper trading
                                        │ paper_xtquant│─ MiniQMT (reserved)
                                        └─────────────┘
```

## Key Design Decisions

### 1. Survivorship Bias Prevention

Index composition changes every 6 months (June & December). The `data/universe.py` module tracks historical constituent changes using AKShare's `index_stock_cons` endpoint. On each backtest date, only stocks that were actually in the index on that date are eligible for trading.

### 2. Signal-First Architecture

Strategies produce **stateless signal dictionaries** — `{date: [{code, action, weight}]}`. The backtest engine replays these signals independently. This decoupling means:
- Strategies are pure signal generators (testable in isolation)
- The same signals feed both backtrader (backtest) and vnpy/MiniQMT (paper/live)

### 3. Star-Tagged Provenance

Every strategy carries `stars_tags.py` metadata declaring its GitHub origin project, star count, and academic paper reference. The report generator surfaces this provenance in comparison tables.

### 4. Execution Layer Abstraction

`execution/base.py` defines the `ExecutionProvider` ABC. Two implementations exist:
- `VnpyPaperProvider` — local paper account simulation (zero dependency on brokers)
- `XtquantProvider` — reserved stub for MiniQMT paper trading

Swap providers via configuration without touching strategy code.

## Strategy Implementation Patterns

### Technical Strategies (events-driven)
Each technical strategy:
1. Prepares indicator columns on the full price DataFrame (vectorized)
2. Generates buy/sell signal dates using pandas boolean masks
3. Returns signal dict consumed by backtrader engine

### Factor/ML Strategies (Qlib-based)
Factor and ML strategies delegate data handling to Qlib's `DataHandlerLP`:
1. Qlib loads the Alpha158/Alpha360 pre-defined factor set
2. Models (LGB/XGB/LSTM) train on the training segment
3. Predictions are converted to buy signals (top 10% each date)
4. GPU training available via `--device cuda`

### Portfolio Strategies (cross-sectional)
Portfolio strategies process the entire stock universe at each rebalance date:
- Pairs Trading: Engle-Granger cointegration test → spread trading
- Risk Parity: inverse-volatility weighting → monthly rebalance

## A-Share Market Rules

| Rule | Implementation |
|------|---------------|
| T+1 settlement | Buy orders cannot be sold same day — enforced at engine level |
| Price limits (±10%) | Orders rejected if stock at daily limit, flagged in processor |
| Stamp duty (0.1% sell) | Modeled in `backtest/engine.py:AShareCommission` |
| Lot size (100 shares) | Order quantities rounded to multiples of 100 |
| Suspended stocks | Filtered by zero-volume check in `broker.py` |

## Data Flow

```
AKShare (primary: web scraping, 500+ endpoints)
    │
    ├─ index_stock_cons() ────►  index constituents
    ├─ stock_zh_a_hist()  ────►  daily OHLCV (前复权)
    └─ stock_financial_abstract() ►  PE, PB, ROE, etc.

BaoStock (fallback: dedicated server)
    │
    └─ query_history_k_data_plus() ►  daily OHLCV (fallback)

Processor:
    clean_ohlcv() → compute_returns() → price_limit_filter()
                                                  │
Universe:                                         │
    build_universe_mapping() ────── align with ───┘
                                                  │
Backtest Engine:                                  │
    run_single_strategy() ← signals ← strategy ───┘
                                                  │
Evaluation:                                       │
    metrics → report → comparison → output files
```

## Dependencies

| Package | Purpose |
|---------|---------|
| backtrader | Event-driven backtest engine |
| akshare | Primary A-share data source |
| baostock | Fallback data source |
| pandas, numpy | Data processing |
| statsmodels | Cointegration tests (pairs trading) |
| pyqlib (optional) | Qlib framework for ML strategies |
| torch (optional) | GPU-accelerated DL models |
| vnpy (optional) | Paper/live trading execution |
