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

### 2026-07-26 重构核验

- [x] **注册中心端到端核验**: 自动发现 11 策略 (10 启用, pairs_trading 停用), 覆盖 technical/portfolio/ml/factor 四类
- [x] **双特征引擎核验**: basic8 → 91,400 样本×8 特征; alpha13 → 708,846 样本×13 特征 (数据 1,833 日×427 股)
- [x] **sim_runner 核验**: 逐策略读取 spec 的 rebalance_days/max_positions; 停用策略保留 DB 历史指标
- [x] **Web 层核验**: dispatch/web/app.py 经 strategy_meta() 消费注册中心, 新策略文件落盘即在 UI 出现, 无需改代码
- [x] **修正 alphamaster_rank.py 文档字符串**: 原文称默认 rb=1 "复现原版日频", 与代码 (rb=30) 矛盾, 会把读者指向验证已证伪的配置; 现同时标注日频 -75.64%/Sharpe -2.521 与月频 +60.30%/Sharpe +0.944
- [x] 清理临时核验脚本 (_check_registry.py)

### 2026-07-26 研究工作台 P0 (实验可积累)

> 背景: 系统原是"生产模拟观察窗", 回测结果只存内存、重启即失, 无法跨次对比。
> P0 把实验存储与对比变为一等公民。流程规范见 [CYCLE.md](CYCLE.md)。

- [x] **实验存储 research.db** (dispatch/research/store.py): runs/run_metrics(长表)/run_equity/run_trades/sweeps 五表, 只追加不覆盖, 与生产 trades.db 物理隔离; 每 run 记录 data_version(数据指纹)+code_version(git HEAD) 可复现
- [x] **执行内核 dispatch/kernel/**: sim_engine 成本模型参数化 (CostModel, 默认值与原常量逐笔一致, 支持 .scaled(n) 成本敏感性); runner.py 统一 RunSpec→RunResult 接口; data/signal 服务 re-export
- [x] **完整指标套件** (dispatch/research/metrics.py): 7 项 → 36 项 (Sortino/Calmar/IR/Alpha/Beta/回撤时长/水下时间/VaR/CVaR/盈亏比/换手/成本拖累/月度年度收益); VOL_FLOOR 防护平坦曲线产生伪 Sharpe
- [x] **研究页面** (dispatch/web/research.py): /research 发射台, /research/runs 排行榜(可排序+筛选), /research/run/<id> 深潜(净值回撤图+全指标+成交+版本), /research/compare 头对头(指标差异+净值叠加)
- [x] **layout 抽离** (dispatch/web/ui/layout.py): page/nav/CSS 移出 app.py, 4 个旧蓝图改直接引用, 函数内循环导入根除
- [x] **实验室回测自动入库**: backtest_service.run_backtest() persist=True 默认写 research.db 并返回 run_id, 重启不再丢结果
- [x] **生产链路零变化验证**: kernel/shim 数值一致性测试(同 pivot+signals 逐笔成交相等), 14 个页面全部 200
- [x] 清理 6 个僵尸 app.py 进程 (旧代码占用 8600 端口导致"改了没反应")

### 2026-07-26 P0 补完 — ML 训练隔离

> 背景: 审查发现实验/生产共享 4 个可变状态（参数文件、信号缓存、未持久化模型、无锁写入），
> 实验可意外影响生产。本阶段修致命隔离缺口。

- [x] **params_override 管道**: `generate_all_signals` → `generate_ml_signals` → `_ml_top_codes_at_retrains` 三函数接受显式参数覆盖, `RunSpec.params` 生效, 调参不碰全局配置
- [x] **effective_params 落库**: `store.py` runs 表加 `params_hash` 列 + 自动迁移; `runner.py`/`backtest_service.py` 计算 `{**get_params, **spec.params}` 全集并 hash 落库 — 修 P0 可复现漏洞
- [x] **缓存分区 + 原子写入**: 缓存路径 `{scope}/{strategy}/{params_hash}.json` (scope=prod|research), 不同参数天然不同文件, 删除全局失效逻辑; `os.replace` 原子替换 + `.tmp` 清理
- [x] **模型持久化** (kernel/model_store.py): `{scope}/{strategy}/{params_hash}/{retrain_date}.pkl` + `.json` 元数据, 二次运行跳过重训 (load_model 命中)
- [x] **生产缓存隔离**: `sim_runner.py` 传 `cache_scope="prod"`, 实验与生产信号/模型全程独立目录
- [x] **lab 回测修复**: (a) `request.form.get("mode")` 从后台线程移到路由层 — 修复 RuntimeError; (b) 缩进修正 — modes 循环从策略循环外移到内, 所有策略结果显示
- [x] **data_version 双格式**: 同时支持 raw OHLCV (columns: date/code) 和 pivot (index=date, columns=code), 模型元数据不再静默丢失
- [x] **runner.py truthiness 修复**: `rebalance_days=0` 不再被 `or` 错误替换为默认值
- [x] 代码审查: 2 BLOCKER + 1 CRITICAL + 2 WARNING 全部修复, web 服务验证 13/13 页 200

## P1 — 研究深度 (下一迭代, ~4h)

- [ ] **参数扫描引擎**: RunSpec 网格展开 → 子 run 批量执行, parent_sweep_id 关联; /research/sweep/<id> 敏感面热力图 + 稳定区识别
- [ ] **成本扫描**: CostModel.scaled() 序列 (0.5x/1x/2x/3x), 回答"成本高到多少 alpha 消失"
- [ ] **统计显著性** (dispatch/research/stats.py): Sharpe 标准误与 t 值、bootstrap 置信区间、deflated Sharpe (多重检验惩罚, 用 store.trial_count())
- [ ] **分时段/分环境表现**: 分年/分季收益表, 牛熊震荡分段指标
- [ ] **IS/OOS 对比面**: ML 策略样本内外 gap 报告

## P2 — 工程与效度 (~6h)

- [ ] **feature_store 因子缓存**: key=(feature_set,pool,data_version)→parquet, 消灭 basic8 每次 8.2s 重算
- [ ] **/api/v1 JSON 层**: 页面与外部工具共用同一数据源
- [ ] **plotly 交互图**: 扫描热力图/多曲线叠加/缩放 (静态 matplotlib 在扫描分析上体验差)
- [ ] **历史成分股**: 修幸存者偏差 (akshare 仅当前成分, 需另找数据源); 未修前每个 run 页标注"已知局限"
- [ ] **容量/冲击成本模型** + **组合权重优化页** (/research/portfolio: 边际 Sharpe, 等权/风险平价/最优权重)

## P2 — 原有待做 (按优先级)

- [ ] **补跑完整 run_simulation()**: 2026-07-26 核验未执行全量 pipeline, 逐策略回测数值尚未在重构后确认, 出下一份报告前应先跑一次
- [ ] **ML walk-forward 缓存失效路径验证**: 超参变更时 params-hash 强制重训的逻辑未被实际触发测试
- [ ] **K 线自动跳转** (已评估: plotly 交互式 K线 + 成标点, ~2.5-3h; trades 每行加 📈 链接跳转到该股票该日期 K 线; 数据已就绪) — **待确认是否实施**
- [ ] **PA_Agent 融入** (已明确排除在本次之外, 待启动):
  - [ ] 29 套中文交易分析提示词导入 (市场诊断框架/通道/震荡/K线信号/二元决策等)
  - [ ] 两阶段 LLM 分析引擎 (Stage1 市场诊断→Stage2 交易决策) + /analyst Web 页
  - [ ] NLP 市场情绪因子 (5维, 第12策略特征增强)
- [ ] **微信推送正式启用**: 按 README 指引注册企业微信→建群→机器人→WECOM_WEBHOOK_URL 写入 .env
- [ ] **信号强度评分**: 每个信号 0-10 强度分
- [ ] **策略健康监控**: 连续20日 Sharpe<0 邮件标黄, 40日建议暂停
- [ ] **仓位集中度预警**: 单票>8% 或前5>40% 标记
- [ ] **滚动 Sharpe 曲线** / 月度收益热力图 (注: 研究页 run 详情已有月度数据, 此条指生产仪表盘)
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
