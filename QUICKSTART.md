# 快速启动指南

## 1. 环境准备

```bash
cd D:\doc\量化\project2
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. 配置通知渠道

复制 `.env.example` 为 `.env`，填写：

```
QQ_EMAIL=你的QQ号@qq.com
QQ_AUTH_CODE=QQ邮箱SMTP授权码
TO_EMAIL=接收报告的邮箱
DEEPSEEK_API_KEY=可选，AI 评论/助手用
WECOM_WEBHOOK_URL=可选，企业微信群机器人
```

获取授权码：QQ邮箱 → 设置 → 账户 → POP3/SMTP服务 → 生成授权码

## 3. 日常使用（推荐）

启动一站式 Web 服务：

```bash
.venv\Scripts\python.exe dispatch\web\app.py    # → http://localhost:8600
```

（已配置 Windows 任务计划 QuantWeb 登录自启，正常情况无需手动启动。）

| 页面 | 用途 |
|---|---|
| `/` | 主页：最新推荐/表现报告 |
| `/overview` | 策略卡片、净值对比、最新成交 |
| `/research` | **研究发射台**：选策略/窗口/池 → 一键回测并入库 |
| `/research/runs` | **实验排行榜**：全历史实验按指标排序筛选 |
| `/strategies` | 策略开关、参数调整、AI 推荐参数 |
| `/lab` | 数据面板（状态+拉取）、一键训练、一键回测（自动入库） |
| `/trades` | 逐笔成交、分组汇总、FIFO 盈亏配对、CSV 导出 |
| `/compare` | 生产模拟净值对比（自选策略） |
| `/assistant` | AI 助手：自然语言管理数据与任务 |
| `/jobs` `/scheduler` | 后台任务与调度中心 |

## 4. 研究实验（命令行方式）

页面发射之外，也可以脚本化发射实验（结果同样入 research.db）：

```python
import sys; sys.path.insert(0, 'dispatch')
import services  # 路径引导，必须
from kernel.runner import RunSpec, execute_and_save

spec = RunSpec(strategy='ma_cross', start='2024-06-01', end='2024-08-31',
               pool='csi500', mode='equal', tag='my_experiment')
run_id = execute_and_save(spec)   # 完成后到 /research/run/<run_id> 查看
```

批量回测（实验室同源，自动入库）：

```python
from services.backtest_service import run_backtest
run_backtest(['ma_cross', 'rsi_reversal'], '2024-06-01', pool='csi500', tag='v2')
```

## 5. 其他运行命令

### 历史全量回测（旧研究系统，backtrader 引擎）

```bash
python research/run_backtest.py    # 约10-15分钟，输出 research/reports/
```

### 每日邮件（手动触发，一般不需要）

```bash
python dispatch/run_now.py          # 推荐邮件 + 表现邮件一次完成
python dispatch/run_daily.py        # 完整每日 pipeline
```

### 集成测试

```bash
python tests/test_integration.py
```

## 6. 项目结构

```
quant-lab/
├── .env / .env.example / .gitignore
├── README.md / QUICKSTART.md / CYCLE.md / TODO.md / requirements.txt
│
├── core/                       # 共享核心
│   ├── config/settings.py      # 参数配置
│   ├── data/                   # 数据管道 (AKShare + BaoStock)
│   │   └── cache/              # 行情缓存 (parquet)
│   ├── strategies/             # 11 个策略（注册中心自动发现）
│   │   ├── technical/          # MA Cross, RSI, Bollinger, MACD
│   │   ├── factor/             # AlphaMaster GBR
│   │   ├── ml/                 # Alpha158 LGB/XGB, LSTM, Transformer
│   │   └── portfolio/          # Pairs Trading(停用), Risk Parity
│   └── backtest/               # 旧回测引擎 (backtrader, 历史研究用)
│
├── dispatch/                   # 分发系统（每日模拟 + Web）
│   ├── kernel/                 # 执行内核（纯 Python，零 Flask 依赖）
│   │   ├── sim_engine.py       # 模拟引擎（成本模型 CostModel 参数化）
│   │   ├── runner.py           # 统一运行接口 RunSpec → RunResult
│   │   ├── data_service.py     # 数据访问（re-export services）
│   │   └── signal_service.py   # 信号生成（re-export services）
│   ├── research/               # 研究层
│   │   ├── store.py            # 实验存储 research.db（5 表，只追加）
│   │   └── metrics.py          # 完整指标套件（36 项）
│   ├── services/               # 生产服务（含 sim_engine 兼容 shim）
│   ├── state/
│   │   ├── trades.db           # 生产战绩（每日覆盖，单时间线）
│   │   └── research.db         # 实验库（只追加，多维实验空间）
│   ├── charts/generator.py     # matplotlib 图表
│   ├── notify/                 # 通知渠道（QQ 邮件 / 企业微信 / PushPlus）
│   ├── mail/YYYYMM/            # 邮件归档
│   └── web/
│       ├── app.py              # Flask 入口（主页/总览/策略/成交/对比）
│       ├── research.py         # 研究工作台蓝图（/research/*）
│       ├── ui/layout.py        # 页面外壳/CSS/导航（蓝图共用）
│       └── admin/lab/reports/assistant.py  # 其余蓝图
│
├── research/                   # 历史研究系统（脚本 + 文档）
│   ├── run_backtest.py / run_all.py
│   ├── evaluation/             # 指标 + 报告生成
│   ├── results/ reports/       # 回测产出
│   └── docs/                   # 文档（架构/绩效/策略分文档）
│
├── execution/                  # 实盘接入层（预留）
├── tests/                      # 测试
└── scripts/                    # 运维脚本
```

## 7. 文档索引

| 文档 | 内容 |
|------|------|
| [CYCLE.md](CYCLE.md) | **每次迭代必做清单**（先读这个） |
| [TODO.md](TODO.md) | 功能规划与已完成记录 |
| [research/docs/ARCHITECTURE.md](research/docs/ARCHITECTURE.md) | 架构设计 + 数据流 |
| [research/docs/PERFORMANCE_ANALYSIS.md](research/docs/PERFORMANCE_ANALYSIS.md) | 回测绩效全面分析 |
| [research/docs/GBR_VALIDATION.md](research/docs/GBR_VALIDATION.md) | GBR 策略验证（研究方法论范例） |
| [research/docs/strategies/](research/docs/strategies/) | 10 篇策略分文档 |

## 8. GitHub

仓库地址: https://github.com/feng653/quant-lab
