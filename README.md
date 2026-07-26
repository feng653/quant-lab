# quant-lab

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

多策略 A 股量化研究 + 每日模拟交易分发系统。

**11 个策略 · CSI 500/800 · 2019-2026 · 实验可积累的研究工作台 + 每日邮件/微信报告。**

---

## 仓库结构

```
core/        共享层 — 配置、数据抓取、策略库（注册中心）、回测引擎
dispatch/    分发系统 — 每日模拟、邮件、微信、Web 服务
  ├── kernel/     执行内核（纯 Python）：sim_engine（成本模型参数化）、
  │               runner（RunSpec→RunResult 统一接口）、
  │               model_store（ML 模型持久化，二次运行秒过）、
  │               data/signal 服务
  ├── research/   研究层：实验存储（research.db）、完整指标套件（36 项）
  ├── services/   生产服务（兼容层，逐步向 kernel 迁移）
  ├── state/      trades.db（生产战绩）+ research.db（实验库，物理隔离）
  └── web/        Flask 一站式服务（ui/ 布局层 + 蓝图）
research/    历史研究系统 — 全历史回测脚本、评估、报告、文档
execution/   实盘接入层（vnpy / xtquant，预留）
scripts/     运维工具（A/B 回测、数据清理）
tests/       测试
```

## 快速开始

```bash
git clone https://github.com/feng653/quant-lab.git
cd quant-lab
pip install -r requirements.txt
cp .env.example .env   # 填写 QQ 邮箱 / DEEPSEEK_API_KEY / WECOM_WEBHOOK_URL

# ── 一站式 Web 服务（仪表盘 + 调度器，推荐）──
python dispatch/web/app.py          # → http://localhost:8600

# ── 或手动跑每日 pipeline ──
python dispatch/run_daily.py        # 更新数据 → 模拟 → 双邮件 + 企业微信

# ── 历史研究系统 ──
python research/run_backtest.py     # 全历史回测（全策略 × 双股票池）
python scripts/gbr_validation.py    # AM GBR 验证报告
```

## 研究工作台（/research）

每个回测结果**自动落库**（`dispatch/state/research.db`），可查询、可排序、可对比、可复现：

| 页面 | 作用 |
|---|---|
| `/research` | 实验发射台：策略 × 窗口 × 股票池 × 模式，一键发射 |
| `/research/runs` | 实验排行榜：36 项指标可排序，按策略/标签/池筛选 |
| `/research/run/<id>` | 单实验深潜：净值+回撤带图、全指标卡、成交明细、数据/代码版本 |
| `/research/compare?runs=a,b` | 头对头：指标差异表 + 归一化净值叠加 |

每个实验记录 `data_version`（数据指纹）、`code_version`（git HEAD）、
**`params_hash`**（生效参数全集 MD5），结果永远可追溯可复现。

## 每日分发系统

从**固定起点（2026-05-25）**开始模拟，每个策略独立运行 100 万元账户，
**两种仓位模式**（等权 vs 波动率自适应），全部成交逐笔记录于
`dispatch/state/trades.db`（与研究实验库物理隔离）。

- **一站式 Web 服务**（QuantWeb 登录自启，端口 8600）：托管仪表盘和
  APScheduler，每日 15:35 自动跑 pipeline（数据更新 → walk-forward 信号 →
  重模拟 → 推荐邮件 + 表现邮件 + 企业微信推送）
- **策略注册中心**：策略放在 `core/strategies/` 用 `@register_strategy`
  装饰器自动发现；Web 管理页可开关启停、调参数、获取 AI 推荐参数（DeepSeek）
- **Web 页面**：主页（最新报告）/ 总览 / 策略管理 / **研究工作台** / 实验室
  （数据、一键训练、一键回测）/ AI 助手 / 成交记录 / 对比 / 报告归档 /
  任务 / 调度
- **11 个策略**：4 技术 + 2 组合（pairs 已停用——A 股无法做空）+ 4 ML
  walk-forward + AM GBR（迁移自 AlphaMaster，[已验证](research/docs/GBR_VALIDATION.md)：
  宣称 Sharpe 3.12 被证伪，真实 alpha 在月频调仓）

## 企业微信推送设置

1. 安装企业微信 App，注册个人团队（任意名称，无需认证）
2. 建群 → 群设置 → 群机器人 → 添加 → 复制 webhook 地址
3. 写入 `.env`：`WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/...`

消息只经过腾讯服务器，无第三方中转（不同于 PushPlus）。

## 回测结果（2024-01 ~ 2026-06，完整数据）

| 排名 | 策略 | 股票池 | 年化% | Sharpe | 最大回撤 | 来源 |
|:---:|----------|------|--------:|-------:|------|--------|
| 1 | **MA Cross** | CSI 800 | **+33.4** | **0.97** | -24.7% | ★10.4k |
| 2 | **MACD Sig.** | CSI 800 | +16.0 | 0.85 | -11.2% | ★10.4k |
| 3 | **MACD Sig.** | CSI 500 | +20.8 | 0.81 | -23.6% | ★10.4k |
| 4 | MA Cross | CSI 500 | +19.0 | 0.61 | -31.0% | ★10.4k |
| 5 | Bollinger | CSI 500 | +8.3 | 0.49 | -18.6% | ★10.4k |
| 6 | Bollinger | CSI 800 | +5.8 | 0.35 | -15.3% | ★10.4k |
| 7 | Risk Parity | CSI 500 | +5.3 | 0.24 | -10.5% | ★4.8k |

[完整绩效分析 →](research/docs/PERFORMANCE_ANALYSIS.md)

## 策略目录

| 策略 | 类别 | 来源 | Stars | 文档 |
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

## 特性

- **实验可积累**：回测结果持久化 research.db，跨次对比、排序、复现。支持批量调参（RunSpec.params 覆盖注册默认值 + params_hash 落库）
- **模型缓存**：ML 训练产物落盘，同参数二次运行跳过重训（LSTM 从约 40 秒降到秒级）
- **生产/实验隔离**：信号缓存 + 模型存储按 scope=（prod|research）物理分区，实验永不影响生产
- **完整指标**：36 项（Sortino/Calmar/IR/Alpha/Beta/回撤时长/VaR/换手/成本拖累等）
- **成本模型参数化**：佣金/印花税/滑点可调，支持成本敏感性分析
- **2 个股票池**：CSI 500（427 只）+ CSI 800（687 只）
- **7 年完整数据**：2019-2026，每日自动增量更新
- **真实每日模拟**：11 策略 × 2 仓位模式，逐笔成交 SQLite 记录
- **Walk-forward ML**：LGB/XGB/LSTM/Transformer 月度重训，无前视
- **基准与成本感知**：CSI 500 买入持有基准，佣金/印花税/滑点分项
- **市场环境分类**：牛/熊/震荡/高波动识别 + 适配策略映射
- **AI 评论**：DeepSeek 生成每日市场点评（可选）
- **多渠道**：QQ 邮件 + 企业微信 + 本地 Web 仪表盘
- **A 股规则**：T+1、印花税、100 股整手

## 已知局限

- **幸存者偏差**：akshare 只提供当前指数成分股，历史回测使用当前成分
  （P3 计划修复）；每个实验结论需带着这个前提阅读
- 前复权价格以最新交易日为锚，公司行为可能导致历史行轻微漂移（已接受的折衷）

## 文档

| 文档 | 内容 |
|----------|---------|
| [CYCLE.md](CYCLE.md) | **每次迭代必做清单**（开发流程） |
| [QUICKSTART.md](QUICKSTART.md) | 安装与使用指南 |
| [TODO.md](TODO.md) | 功能规划与已完成记录 |
| [research/docs/ARCHITECTURE.md](research/docs/ARCHITECTURE.md) | 架构与数据流 |
| [research/docs/PERFORMANCE_ANALYSIS.md](research/docs/PERFORMANCE_ANALYSIS.md) | 绩效分析 + A/B 仓位 |
| [research/docs/strategies/](research/docs/strategies/) | 10 篇策略分文档 |

## License

MIT
