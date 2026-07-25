# quant-lab

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

Multi-strategy quantitative research + daily simulation & dispatch pipeline for Chinese A-shares.

**10 strategies · CSI 500/800 · 2019-2026 · daily simulated trading with email/WeChat reports.**

---

## Repository Layout

```
core/        shared layer — config, data fetchers, strategy library, backtest engine
research/    research system — full-history backtests, evaluation, reports, docs
dispatch/    dispatch system — daily simulation, emails, WeChat, web dashboard
execution/   live-trading adapters (vnpy / xtquant, reserved)
scripts/     ops tools (A/B backtest, cleanup)
tests/       test suites
```

## Quick Start

```bash
git clone https://github.com/feng653/quant-lab.git
cd quant-lab
pip install -r requirements.txt
cp .env.example .env   # fill QQ mail / DEEPSEEK_API_KEY / PUSHPLUS_TOKEN

# ── dispatch system (daily) ──
python dispatch/run_daily.py        # update data → simulate 10 strategies → 2 emails + WeChat
python dispatch/web/app.py          # web dashboard → http://localhost:8600

# ── research system ──
python research/run_backtest.py     # full-history backtest (all strategies, both pools)
python scripts/ab_position_backtest.py   # A/B position sizing analysis
```

## Daily Dispatch System

Simulation starts from a **fixed origin (2026-05-25)**, every strategy runs an
independent 1,000,000 CNY account in **two sizing modes** (equal-weight vs
adaptive volatility). All trades are recorded in SQLite (`dispatch/state/trades.db`).

- **15:35 daily** (Task Scheduler `QuantDaily`): data auto-update → walk-forward
  signals → re-simulation → recommendation email (per-strategy buys/sells with
  suggested sizing) + performance email (benchmark comparison, cost analysis,
  correlation heatmap, AI commentary) + WeChat push
- ML strategies (LGB/XGB/LSTM/Transformer) retrain monthly, walk-forward
- Web dashboard: browse all trades, per-strategy curves, comparisons any time

## Backtest Results (2024-01 ~ 2026-06, Complete Data)

| Rank | Strategy | Pool | Annual% | Sharpe | MaxDD | Source |
|:---:|----------|------|--------:|-------:|------|--------|
| 1 | **MA Cross** | CSI 800 | **+33.4** | **0.97** | -24.7% | ★10.4k |
| 2 | **MACD Sig.** | CSI 800 | +16.0 | 0.85 | -11.2% | ★10.4k |
| 3 | **MACD Sig.** | CSI 500 | +20.8 | 0.81 | -23.6% | ★10.4k |
| 4 | MA Cross | CSI 500 | +19.0 | 0.61 | -31.0% | ★10.4k |
| 5 | Bollinger | CSI 500 | +8.3 | 0.49 | -18.6% | ★10.4k |
| 6 | Bollinger | CSI 800 | +5.8 | 0.35 | -15.3% | ★10.4k |
| 7 | Risk Parity | CSI 500 | +5.3 | 0.24 | -10.5% | ★4.8k |

[Full Performance Analysis →](research/docs/PERFORMANCE_ANALYSIS.md)

## Strategy Catalog

| Strategy | Category | Source | Stars | Doc |
|----------|----------|--------|:---:|------|
| MACD Signal | technical | je-suis-tm/quant-trading | 10.4k | [→](research/docs/strategies/04-macd-signal.md) |
| MA Cross | technical | je-suis-tm/quant-trading | 10.4k | [→](research/docs/strategies/01-ma-cross.md) |
| Bollinger | technical | je-suis-tm/quant-trading | 10.4k | [→](research/docs/strategies/03-bollinger-breakout.md) |
| RSI Reversal | technical | je-suis-tm/quant-trading | 10.4k | [→](research/docs/strategies/02-rsi-reversal.md) |
| Alpha158+LGB | factor | microsoft/qlib | 46.6k | [→](research/docs/strategies/07-alpha158-lgb.md) |
| Alpha158+XGB | factor | microsoft/qlib | 46.6k | [→](research/docs/strategies/08-alpha158-xgb.md) |
| LSTM Rank | ml | microsoft/qlib | 46.6k | [→](research/docs/strategies/09-lstm-rank.md) |
| Pairs Trading | portfolio | je-suis-tm/quant-trading | 10.4k | [→](research/docs/strategies/05-pairs-trading.md) |
| Risk Parity | portfolio | PyPortfolioOpt | 4.8k | [→](research/docs/strategies/06-risk-parity.md) |

## Features

- **2 stock pools**: CSI 500 (427 stocks) + CSI 800 (687 stocks)
- **Full 7-year data**: 2019-2026, auto-incremental daily updates
- **Real daily simulation**: 10 strategies × 2 sizing modes, trade-level SQLite records
- **Walk-forward ML**: LGB/XGB/LSTM/Transformer retrained monthly, no look-ahead
- **Benchmark & cost aware**: CSI 500 buy-hold baseline, commission/stamp/slippage split
- **Market regime**: bull/bear/choppy/high-vol classification with strategy mapping
- **AI commentary**: DeepSeek-generated daily market review (optional)
- **Multi-channel**: QQ email + WeChat (PushPlus) + local web dashboard
- **A-share rules**: T+1, stamp duty, 100-share lots

## Docs

| Document | Content |
|----------|---------|
| [QUICKSTART.md](QUICKSTART.md) | Setup & usage guide |
| [TODO.md](TODO.md) | Feature backlog |
| [research/docs/ARCHITECTURE.md](research/docs/ARCHITECTURE.md) | Architecture & data flow |
| [research/docs/PERFORMANCE_ANALYSIS.md](research/docs/PERFORMANCE_ANALYSIS.md) | Performance analysis + A/B sizing |
| [research/docs/strategies/](research/docs/strategies/) | 10 per-strategy documents |

## License

MIT
