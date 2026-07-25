# TODO — 功能规划 Backlog

> 仅作功能记录，按优先级排序。完成后移入"已完成"。

## 已完成 (2026-07-25 系统重做)

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
- [x] Flask Web 仪表盘 (dispatch/web/app.py, http://localhost:8600, 端口可用 DASH_PORT 配置)
- [x] AI 市场评论 (DeepSeek API, 读 DEEPSEEK_API_KEY 环境变量)
- [x] LSTM/Transformer 真实序列模型 (2层LSTM / 2层TransformerEncoder, walk-forward 月度重训)
- [x] 微信 PushPlus 推送接口 (notify/wechat_pushplus.py)
- [x] 数据清理脚本 (scripts/cleanup_data.py)
- [x] 每日自动运行任务 QuantDaily 15:35 (run_daily.py)

## P2 — 中期优化

- [ ] **微信推送正式启用**: 注册 PushPlus (https://www.pushplus.plus) 获取 token, 写入 .env 的 PUSHPLUS_TOKEN
- [ ] **信号强度评分**: 不只是买/卖, 每个信号给出 0-10 强度分 (技术形态完成度/ML预测分位数)
- [ ] **策略健康监控**: 连续 20 交易日 Sharpe<0 的策略在邮件中自动标黄告警, 连续 40 日则建议暂停
- [ ] **仓位集中度预警**: 单票占比 >8% 或前5持仓 >40% 时邮件标记
- [ ] **滚动 Sharpe 曲线**: 20日滚动 Sharpe 子图, 观察策略失效拐点
- [ ] **月度收益热力图**: 每策略月度收益矩阵 (回测期+模拟期)
- [ ] **邮件 CSV 附件**: 当日成交明细以 CSV 附件随表现邮件发送
- [ ] **仪表盘增强**: 部署为开机自启服务, 支持局域网访问; 增加持仓历史变化图

## P3 — 远期愿景

- [ ] **实盘信号桥接**: 信号导出 MiniQMT (xtquant) / vnpy 接口, paper_xtquant.py 对接
- [ ] **多资产扩展**: ETF、可转债、股指期货策略接入同一模拟框架
- [ ] **分钟级数据**: 盘中 5min/15min 级别信号 (数据源: akshare 分钟接口)
- [ ] **多因子动态轮动**: 根据市场环境分类自动调整策略权重组合
- [ ] **ML 特征工程扩展**: 财务因子 (PE/PB/ROE)、行业因子、资金流向 (见 PERFORMANCE_ANALYSIS.md 七)
- [ ] **LSTM/TF 调优**: 超参搜索 (hidden size/层数/seq_len)、特征归因、与 LGB 集成
- [ ] **实时行情 API**: 接入券商/数据商实时行情替换 akshare 日线
