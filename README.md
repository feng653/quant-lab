# Quant Strategy Verification

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

Multi-strategy quantitative verification pipeline for Chinese A-share market.

**10 open-source strategies tested on CSI 500 & CSI 800, with daily paper trading & QQ email notification.**

---

## Quick Start

```bash
git clone https://github.com/feng653/quant-strategy-verification.git
cd quant-strategy-verification
pip install -r requirements.txt

# List strategies
python main.py --list-strategies

# Run full backtest
python run_all.py

# Daily pipeline (data + signals + paper trade + email)
python main.py --step daily
```

## Strategy Results (100 stocks, 2024-2026)

| Strategy | Pool | Return | Sharpe | MaxDD | Source |
|----------|------|--------|--------|-------|--------|
| MACD Signal | CSI 800 | **+275%** | **2.17** | -23% | ★10.4k |
| MA Cross | CSI 500 | +202% | 1.52 | -30% | ★10.4k |
| MACD Signal | CSI 500 | +163% | 1.58 | -23% | ★10.4k |
| Bollinger | CSI 800 | +70% | 1.00 | -16% | ★10.4k |
| Pairs Trading | CSI 500 | +22% | 0.38 | -16% | ★10.4k |
| RSI Reversal | CSI 800 | -7% | -0.32 | -17% | ★10.4k |

[Full analysis →](docs/PERFORMANCE_ANALYSIS.md)

## Strategy Catalog (10 strategies, 4 categories)

| Strategy | Category | Source | Stars |
|----------|----------|--------|:-----:|
| MACD Signal | technical | je-suis-tm/quant-trading | 10.4k |
| MA Cross | technical | je-suis-tm/quant-trading | 10.4k |
| Bollinger Breakout | technical | je-suis-tm/quant-trading | 10.4k |
| RSI Reversal | technical | je-suis-tm/quant-trading | 10.4k |
| Alpha158 + LightGBM | factor | microsoft/qlib | 46.6k |
| Alpha158 + XGBoost | factor | microsoft/qlib | 46.6k |
| LSTM Rank | ml | microsoft/qlib | 46.6k |
| Transformer Rank | ml | microsoft/qlib | 46.6k |
| Pairs Trading | portfolio | je-suis-tm/quant-trading | 10.4k |
| Risk Parity | portfolio | PyPortfolioOpt | 4.8k |

Per-strategy docs: [docs/strategies/](docs/strategies/)

## Features

- **2 stock pools**: CSI 500 (mid-cap) + CSI 800 (large+mid cap)
- **Dual data sources**: AKShare (primary) + BaoStock (fallback)
- **A-share rules**: T+1, price limits, stamp duty
- **Look-ahead free**: signal T → execution T+1 open
- **Star-tagged**: every strategy tracks open-source provenance
- **Daily pipeline**: auto data refresh + paper trade + QQ email
- **GPU-ready**: LSTM/Transformer via PyTorch CUDA (optional)

## Docs

| Document | Content |
|----------|---------|
| [QUICKSTART.md](QUICKSTART.md) | Setup & usage guide |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture & data flow |
| [docs/PERFORMANCE_ANALYSIS.md](docs/PERFORMANCE_ANALYSIS.md) | Full backtest analysis |
| [docs/strategies/](docs/strategies/) | 10 per-strategy documents |

## License

MIT
