# Quant Strategy Verification

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

Multi-strategy quantitative verification pipeline for Chinese A-share market.

**10 strategies tested on full CSI 500 (427 stocks) + CSI 800 (687 stocks), 2019-2026.**

---

## Quick Start

```bash
git clone https://github.com/feng653/quant-strategy-verification.git
cd quant-strategy-verification
pip install -r requirements.txt

# List all strategies
python main.py --list-strategies

# Full backtest (all strategies, both pools)
python run_complete.py

# Daily pipeline (data + signals + paper trade + email)
python main.py --step daily
```

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

[Full Performance Analysis →](docs/PERFORMANCE_ANALYSIS.md)

## Strategy Catalog

| Strategy | Category | Source | Stars | Doc |
|----------|----------|--------|:---:|------|
| MACD Signal | technical | je-suis-tm/quant-trading | 10.4k | [→](docs/strategies/04-macd-signal.md) |
| MA Cross | technical | je-suis-tm/quant-trading | 10.4k | [→](docs/strategies/01-ma-cross.md) |
| Bollinger | technical | je-suis-tm/quant-trading | 10.4k | [→](docs/strategies/03-bollinger-breakout.md) |
| RSI Reversal | technical | je-suis-tm/quant-trading | 10.4k | [→](docs/strategies/02-rsi-reversal.md) |
| Alpha158+LGB | factor | microsoft/qlib | 46.6k | [→](docs/strategies/07-alpha158-lgb.md) |
| Alpha158+XGB | factor | microsoft/qlib | 46.6k | [→](docs/strategies/08-alpha158-xgb.md) |
| LSTM Rank | ml | microsoft/qlib | 46.6k | [→](docs/strategies/09-lstm-rank.md) |
| Pairs Trading | portfolio | je-suis-tm/quant-trading | 10.4k | [→](docs/strategies/05-pairs-trading.md) |
| Risk Parity | portfolio | PyPortfolioOpt | 4.8k | [→](docs/strategies/06-risk-parity.md) |

## Features

- **2 stock pools**: CSI 500 (427 stocks) + CSI 800 (687 stocks)
- **Full 5-year data**: 2019-2026, 1.8M+ rows
- **Dual data sources**: AKShare primary + BaoStock fallback
- **A-share rules**: T+1, price limits, stamp duty
- **Look-ahead free**: signal T → execution T+1 open
- **Star-tagged**: every strategy tracks open-source provenance
- **Daily pipeline**: auto data refresh + paper trade + QQ email
- **GPU-ready**: PyTorch CUDA for deep models (CPU also supported)

## Docs

| Document | Content |
|----------|---------|
| [QUICKSTART.md](QUICKSTART.md) | Setup & usage guide |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture & data flow |
| [docs/PERFORMANCE_ANALYSIS.md](docs/PERFORMANCE_ANALYSIS.md) | Complete performance analysis |
| [docs/strategies/](docs/strategies/) | 10 per-strategy documents |

## License

MIT
