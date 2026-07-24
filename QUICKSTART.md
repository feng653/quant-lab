# 快速启动指南

## 1. 环境准备

```bash
cd D:\doc\量化\project2
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. 配置QQ邮箱通知

复制 `.env.example` 为 `.env`，填写：

```
QQ_EMAIL=你的QQ号@qq.com
QQ_AUTH_CODE=QQ邮箱SMTP授权码
TO_EMAIL=接收报告的邮箱
```

获取授权码：QQ邮箱 → 设置 → 账户 → POP3/SMTP服务 → 生成授权码

## 3. 运行命令

### 查看所有策略

```bash
python research/run_backtest.py --list-strategies
```

### 完整回测 (10个策略 × CSI 500 / CSI 800)

```bash
python research/run_backtest.py
```

约10-15分钟（首次需下载完整数据，之后缓存加速），输出：
- `research/reports/complete_report.md` — 完整对比报告
- `research/reports/report_csi500.md` — CSI 500 单独报告
- `research/reports/report_csi800.md` — CSI 800 单独报告
- `research/results/all_results.json` — 详细回测数据

### ML Walk-Forward 回测

```bash
python research/run_ml_walkforward.py
```

### 快速集成测试

```bash
python tests/test_integration.py
```

### 每日推荐邮件 (手动触发)

```bash
python dispatch/daily_recommend.py
```

### 每日表现邮件 (手动触发)

```bash
python dispatch/daily_performance.py
```

### 一键双邮件 (手动触发)

```bash
python dispatch/run_now.py
```

一次性完成：推荐邮件 + 表现邮件（含图表），保存到 `dispatch/mail/YYYYMM/`

## 4. Windows 定时任务

```powershell
# PowerShell 管理员运行
$python = "D:\doc\量化\project2\.venv\Scripts\python.exe"
$workdir = "D:\doc\量化\project2"

# 每日推荐邮件 15:30
$action1 = New-ScheduledTaskAction -Execute $python -Argument "dispatch\daily_recommend.py" -WorkingDirectory $workdir
$trigger1 = New-ScheduledTaskTrigger -Daily -At 15:30
Register-ScheduledTask -TaskName "QuantRecommend" -Action $action1 -Trigger $trigger1 -Force

# 每日表现邮件 16:00
$action2 = New-ScheduledTaskAction -Execute $python -Argument "dispatch\daily_performance.py" -WorkingDirectory $workdir
$trigger2 = New-ScheduledTaskTrigger -Daily -At 16:00
Register-ScheduledTask -TaskName "QuantPerformance" -Action $action2 -Trigger $trigger2 -Force
```

## 5. 项目结构

```
quant-lab/
├── .env / .env.example / .gitignore
├── README.md / QUICKSTART.md / requirements.txt
│
├── core/                       # 共享核心
│   ├── config/settings.py      # 参数配置
│   ├── data/                   # 数据管道 (AKShare + BaoStock)
│   │   └── cache/              # 行情数据缓存 (parquet)
│   ├── strategies/             # 10个策略
│   │   ├── technical/          # MA Cross, RSI, Bollinger, MACD
│   │   ├── factor/             # Alpha158+LGB, Alpha158+XGB
│   │   ├── ml/                 # LSTM, Transformer
│   │   └── portfolio/          # Pairs Trading, Risk Parity
│   └── backtest/               # 回测引擎 (backtrader)
│
├── research/                   # 研究系统 (回测 + 训练 + 分析)
│   ├── run_backtest.py         # 完整回测入口
│   ├── run_ml_walkforward.py   # ML Walk-Forward 训练
│   ├── run_all.py              # 6策略快速回测
│   ├── evaluation/             # 指标计算 + 报告生成
│   ├── results/                # 回测数据 (JSON)
│   ├── reports/                # 回测报告 (Markdown / HTML)
│   └── docs/                   # 文档
│       ├── ARCHITECTURE.md
│       ├── PERFORMANCE_ANALYSIS.md
│       ├── COMPLETION_REPORT.md
│       ├── strategies/         # 10个策略分文档
│       └── resources/          # 量化资源调研
│
├── dispatch/                   # 信息分发系统 (邮件 + 微信 + 仪表盘)
│   ├── daily_recommend.py      # 每日推荐邮件
│   ├── daily_performance.py    # 每日表现邮件 (含图表)
│   ├── run_now.py              # 手动触发双邮件
│   ├── charts/generator.py     # matplotlib 图表
│   ├── notify/                 # 通知渠道
│   │   ├── base.py             # 通知抽象
│   │   └── email_qq.py         # QQ邮箱 SMTP
│   ├── state/                  # 模拟账户状态
│   │   ├── account.py
│   │   └── strategy_state.json
│   ├── mail/YYYYMM/            # 邮件归档 (按月分文件夹)
│   └── web/                    # Flask 仪表盘 (预留)
│
├── execution/                  # 实盘接入层 (预留)
│   ├── paper_vnpy.py
│   └── paper_xtquant.py
│
├── tests/                      # 测试
│   ├── test_integration.py
│   └── test_backtest.py
│
└── scripts/                    # 运维脚本
```

## 6. 文档索引

| 文档 | 内容 |
|------|------|
| [research/docs/ARCHITECTURE.md](research/docs/ARCHITECTURE.md) | 架构设计 + 数据流图 |
| [research/docs/PERFORMANCE_ANALYSIS.md](research/docs/PERFORMANCE_ANALYSIS.md) | 回测绩效全面分析 |
| [research/docs/strategies/](research/docs/strategies/) | 10个策略分文档 |
| [research/docs/COMPLETION_REPORT.md](research/docs/COMPLETION_REPORT.md) | 项目完整工作记录 |

## 7. GitHub

仓库地址: https://github.com/feng653/quant-lab
