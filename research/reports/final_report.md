# 量化策略回测对比报告

**生成时间**: 2026-07-24 21:38

## 策略概览

| 策略 | 来源 | Stars | 类别 |
|------|------|-------|------|
| ma_cross | je-suis-tm/quant-trading | ★ 10400 | technical |
| rsi_reversal | je-suis-tm/quant-trading | ★ 10400 | technical |
| bollinger_breakout | je-suis-tm/quant-trading | ★ 10400 | technical |
| macd_signal | je-suis-tm/quant-trading | ★ 10400 | technical |

## 回测结果

**参数配置**: 初始资金 1,000,000 元, 单边手续费 0.1%, 滑点 0.1%

| 策略 | 股票池 | 累计收益(%) | Sharpe | 最大回撤(%) | 总交易笔数 |
|------|--------|------------|--------|------------|-----------|
| ma_cross | csi500 | 71.65 | 0.939 | -22.6 | 364 |
| rsi_reversal | csi500 | -13.64 | -0.624 | -21.91 | 1525 |
| bollinger_breakout | csi500 | 331.65 | 0.0 | -100.05 | 1470 |
| macd_signal | csi500 | 148.93 | 1.415 | -23.19 | 1795 |