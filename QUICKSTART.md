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
python main.py --list-strategies
```

### 完整回测 (6个策略 × 2个池子)

```bash
python run_all.py
```

约5-10分钟，输出：
- `reports/complete_report.md` — 完整对比报告
- `reports/report_csi500.md` — CSI 500 单独报告
- `reports/report_csi800.md` — CSI 800 单独报告
- `results/all_results.json` — 详细回测数据

### 快速集成测试 (10只股票, 1分钟)

```bash
python test_integration.py
```

### 每日数据更新

```bash
python main.py --step daily-update
```

### 每日模拟交易 + 邮件通知

```bash
python main.py --step daily
```

一次性完成：拉数据 → 生成信号 → 模拟成交 → QQ邮箱推送

### Windows 定时任务 (每日18:00自动执行)

```powershell
# PowerShell 管理员运行
$action = New-ScheduledTaskAction -Execute "D:\doc\量化\project2\.venv\Scripts\python.exe" -Argument "main.py --step daily" -WorkingDirectory "D:\doc\量化\project2"
$trigger = New-ScheduledTaskTrigger -Daily -At 18:00
Register-ScheduledTask -TaskName "QuantDaily" -Action $action -Trigger $trigger
```

## 4. 项目结构

```
quant-strategy-verification/
├── main.py                    # CLI入口
├── run_all.py                 # 完整回测
├── test_final.py              # 最终测试
├── test_integration.py        # 快速验证
├── config/                    # 参数配置
├── data/                      # 数据管道 + 每日更新
├── strategies/                # 10个策略
├── backtest/                  # 回测引擎
├── execution/                 # 模拟盘 + 邮件通知
├── evaluation/                # 指标 + 报告
├── docs/                      # 策略文档 + 架构说明
├── reports/                   # 回测报告
├── results/                   # 详细数据
└── state/                     # 模拟账户状态
```

## 5. 文档索引

| 文档 | 内容 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构设计 + 数据流图 |
| [docs/PERFORMANCE_ANALYSIS.md](docs/PERFORMANCE_ANALYSIS.md) | 回测绩效全面分析 |
| [docs/strategies/](docs/strategies/) | 10个策略分文档 |
| [docs/web_resources/](../docs/web_resources/) | 量化资源调研 |
