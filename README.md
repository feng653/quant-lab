# Quant Strategy Verification

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

Multi-strategy quantitative verification pipeline for the Chinese A-share market.

**Tests open-source strategies from top GitHub repos on CSI 800 and CSI 500 stock pools, with historical data from 2019-2023 (train) and 2024-2026 (out-of-sample backtest).**

---

## Features

- **10 strategies** across 4 categories (technical, factor, ML, portfolio)
- **2 stock pools**: CSI 800 (large+mid cap) and CSI 500 (mid cap)
- **Dual data sources**: AKShare primary + BaoStock fallback
- **A-share rules**: T+1 settlement, price limits, stamp duty simulation
- **Star-tagged provenance**: every strategy tracks its open-source origin
- **ML GPU support**: LSTM/Transformer via Qlib + PyTorch CUDA
- **Paper trading ready**: vnpy integration with MiniQMT reserved

## Quick Start

```bash
# Install
pip install -r requirements.txt

# List all strategies
python main.py --list-strategies

# Download data
python main.py --step data --pool csi800,csi500

# Run technical strategies
python main.py --step backtest --strategies ma_cross,rsi_reversal,bollinger_breakout,macd_signal

# Run ML strategies (CPU)
python main.py --step ml --strategies alpha158_lgb,alpha158_xgb

# Run ML strategies (GPU)
python main.py --step ml --strategies lstm_rank --device cuda

# Full pipeline
python main.py --step all --pool csi800,csi500 --device cuda
```

## Strategy Catalog

| Strategy | Source | Stars | Category |
|----------|--------|:-----:|----------|
| ma_cross | je-suis-tm/quant-trading | 10.4k | technical |
| rsi_reversal | je-suis-tm/quant-trading | 10.4k | technical |
| bollinger_breakout | je-suis-tm/quant-trading | 10.4k | technical |
| macd_signal | je-suis-tm/quant-trading | 10.4k | technical |
| alpha158_lgb | microsoft/qlib | 46.6k | factor |
| alpha158_xgb | microsoft/qlib | 46.6k | factor |
| lstm_rank | microsoft/qlib | 46.6k | ml |
| transformer_rank | microsoft/qlib | 46.6k | ml |
| pairs_trading | je-suis-tm/quant-trading | 10.4k | portfolio |
| risk_parity | robertmartin8/PyPortfolioOpt | 4.8k | portfolio |

## Project Structure

```
quant-strategy-verification/
├── config/          # Parameters, dates, costs
├── data/            # AKShare + BaoStock fetchers, processor, universe
├── strategies/      # 4 categories: technical/factor/ml/portfolio
├── backtest/        # backtrader engine, broker, batch runner
├── execution/       # vnpy paper trading, MiniQMT stub
├── evaluation/      # metrics, reports, comparison
├── main.py          # CLI entry point
└── docs/            # Architecture documentation
```

## Data Sources

| Source | Coverage | Free |
|--------|----------|:----:|
| [AKShare](https://github.com/akfamily/akshare) (★21.5k) | 500+ endpoints: OHLCV, financials, constituents | Yes |
| [BaoStock](http://baostock.com) | Core OHLCV + financials via dedicated server | Yes |

## Backtest Configuration

| Parameter | Value |
|-----------|-------|
| Train period | 2019-01 ~ 2023-12 |
| Backtest period | 2024-01 ~ 2026-06 |
| Initial capital | 1,000,000 CNY |
| Commission | 0.1% per side |
| Stamp duty | 0.1% on sell |
| Slippage | 0.1% |
| Frequency | Daily |

## License

MIT
