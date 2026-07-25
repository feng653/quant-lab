# TODO — 功能规划 Backlog

> 任务记录。已完成标注日期，未完成按优先级排列。

## 已完成

### 2026-07-25 系统重做 (第一波)
- [x] 统一数据管道 (services/data_service.py)，运行前自动补齐到最新交易日
- [x] SQLite 交易数据库 (trades + daily_snapshot)，全量逐笔成交可回查
- [x] 10 策略真实逐日模拟 (ML 策略 walk-forward 重训，废弃合成净值)
- [x] 模拟起始日固定 (2026-05-25) 并在邮件表头标注
- [x] 累计收益口径 = 模拟起始以来 = 近两月收益
- [x] CSI 500 基准买入持有对比 (表格超额列 + 图表灰线)
- [x] 成本分析 (佣金/印花税/滑点分项 + 构成图)
- [x] 策略相关性热力图 + 最高/最低相关对标注
- [x] 市场环境分类 (🐂/🐻/📊/🌊) + 适配策略标注
- [x] 自适应波动率仓位模式 + 等权/自适应双模拟双线对比
- [x] A/B 仓位对比自动写入 PERFORMANCE_ANALYSIS.md
- [x] 推荐邮件: 10 策略完整操作建议 (买入代码×股数×金额 + 卖出 + 持仓)
- [x] 跨策略共识推荐 (≥2策略)
- [x] Flask Web 仪表盘 (dispatch/web/app.py)
- [x] AI 市场评论 (DeepSeek API, 读 DEEPSEEK_API_KEY)
- [x] LSTM/Transformer 真实序列模型 (2层, walk-forward 月度重训)
- [x] 数据清理脚本 (scripts/cleanup_data.py)
- [x] 仪表盘端口 8080→8600 (避开 qBittorrent), DASH_PORT 可配

### 2026-07-25 一站式 Web 服务 (第二波)
- [x] **策略注册中心** (core/strategies/registry.py): 标准化装饰器注册 + 自动扫描发现, 新策略放入目录即被 Web 检测
- [x] **10 策略标准化迁移**到 core/strategies/{technical,portfolio,ml,factor}/, 全部参数化 (param_schema)
- [x] **pairs_trading 停用** (A股无法做空, 模拟 -55.78%), 历史数据保留可查
- [x] **sim_engine 再平衡频率策略级参数化** (日频/月频策略共存)
- [x] **策略管理页** /strategies: 启用开关、参数表单、重新扫描、AI推荐参数
- [x] **AM GBR 策略迁移** (project3 AlphaMaster): 13维特征+GBDT排序, 注册进策略库
- [x] **GBR 验证报告** (research/docs/GBR_VALIDATION.md): 证伪 project3 宣称 Sharpe 3.12 (日频全成本 -75.64%), 发现月频真实 alpha (+60.30%, Sharpe 0.944), 默认月频
- [x] **job_runner 后台任务** + **APScheduler 调度** (每日 15:35 pipeline, 周日 03:00 清理, 当日去重锁)
- [x] **历史报告页** /reports + **主页改为最新报告** (iframe 嵌入 + 功能导航卡)
- [x] **实验室** /lab: 数据面板(状态+拉取)、训练面板(ML一键训练)、回测面板(任意范围)
- [x] **任务中心** /jobs + **调度中心** /scheduler (状态查看+手动触发)
- [x] **成交记录优化**: 统计卡(胜率/持仓天数/已实现盈亏)、按日/按策略/按个股分组、FIFO 往返配对、持仓批次、CSV 导出
- [x] **策略净值成标点** (▲买 ▼卖 叠加在净值图上)
- [x] **AI 参数建议** (services/ai_advisor.py, DeepSeek 生成+schema校验+一键应用)
- [x] **AI 数据管理助手** /assistant (DeepSeek 意图识别→白名单动作, 支持数据/策略/成交/调度/pipeline 自然语言管理)
- [x] **企业微信 webhook 通知** (notify/wechat_wecom.py, 替代 PushPlus 无第三方泄露面)
- [x] **前端 CSS 体系化** (CSS变量/组件/导航激活态/响应式)
- [x] **QuantWeb 常驻任务** (登录自启 Web 服务), QuantDaily 已禁用 (调度并入 Web)
- [x] requirements.txt 补全 (flask/apscheduler/lightgbm/xgboost/torch/sklearn 等)

## P2 — 待做 (按优先级)

- [ ] **K 线自动跳转** (已评估: plotly 交互式 K线 + 成标点, ~2.5-3h; trades 每行加 📈 链接跳转到该股票该日期 K 线; 数据已就绪) — **待确认是否实施**
- [ ] **PA_Agent 融入** (已明确排除在本次之外, 待启动):
  - [ ] 29 套中文交易分析提示词导入 (市场诊断框架/通道/震荡/K线信号/二元决策等)
  - [ ] 两阶段 LLM 分析引擎 (Stage1 市场诊断→Stage2 交易决策) + /analyst Web 页
  - [ ] NLP 市场情绪因子 (5维, 第12策略特征增强)
- [ ] **微信推送正式启用**: 按 README 指引注册企业微信→建群→机器人→WECOM_WEBHOOK_URL 写入 .env
- [ ] **信号强度评分**: 每个信号 0-10 强度分
- [ ] **策略健康监控**: 连续20日 Sharpe<0 邮件标黄, 40日建议暂停
- [ ] **仓位集中度预警**: 单票>8% 或前5>40% 标记
- [ ] **滚动 Sharpe 曲线** / 月度收益热力图
- [ ] **邮件 CSV 附件** (当日成交明细)
- [ ] **仪表盘局域网访问/开机自启服务化** (当前 AtLogon 任务, 可改 NSSM 服务)

## P3 — 远期愿景

- [ ] 实盘信号桥接: MiniQMT (xtquant) / vnpy
- [ ] 多资产扩展: ETF、可转债、股指期货
- [ ] 分钟级数据 (5min/15min 信号)
- [ ] 多因子动态轮动 (按市场环境调策略权重)
- [ ] ML 特征工程扩展: 财务因子 (PE/PB/ROE)、行业因子、资金流向
- [ ] LSTM/TF 超参搜索与特征归因, 与 LGB 集成
- [ ] 实时行情 API 替换 akshare 日线
