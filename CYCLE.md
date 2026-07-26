# CYCLE — 每次迭代必做清单

> 本文件是**每一轮开发迭代的固定流程**。无论迭代内容是什么（新策略、新页面、修 bug、
> 参数调优），开始前和收尾时都对照本清单执行。目标：让实验可积累、文档不腐化、
> 生产链路不被破坏。

---

## 一、迭代开始（环境与健康检查，2 分钟）

- [ ] **Web 服务在运行**：访问 http://localhost:8600 正常；
      若不在，用 venv 解释器启动 `.venv\Scripts\python.exe dispatch\web\app.py`
- [ ] **端口无僵尸进程**：`Get-CimInstance Win32_Process -Filter "Name='python.exe'"`
      中 app.py 实例应只有 1 个；多余实例会抢占 8600 端口导致新代码不生效
- [ ] **数据是最新的**：/lab 数据面板看缓存截止日 = 最近交易日；
      不是则点"拉取数据"或等 15:35 自动 pipeline
- [ ] **git 工作区干净**：`git status` 无意外改动；有遗留改动先提交或 stash
- [ ] **明确本轮目标**：在 TODO.md 里找到（或新增）对应条目

## 二、研究迭代循环（实验工作流）

每做一个策略对比/参数调优实验，走完整闭环，**禁止用一次性脚本出结论**：

1. **提假设** — 一句话写清要验证什么（例："GBR 月频优于日频"）
2. **发射实验** — 优先用 `/research` 页面发射台；批量/脚本化用
   `kernel.runner.RunSpec + execute_and_save()`。**必须打 tag**（如 `gbr_rb`），
   否则实验混进排行榜无法筛选
3. **检查结果** — `/research/runs?tag=<标签>` 按指标排序；
      进 `/research/run/<id>` 看回撤形态、成本拖累、数据/代码版本
4. **头对头对比** — `/research/compare?runs=a,b` 看指标差异表 + 净值叠加；
      差异 < 噪声水平的结论不成立
5. **记录结论** — 在 run 的 note 里写一句话结论；
      重要发现写入 `research/docs/` 对应文档（参考 GBR_VALIDATION.md 的写法）
6. **可复现核验** — 详情页确认 data_version / code_version 已记录

> 判断结论成立的最低标准（P1 落地后强制执行）：同窗口、同池、同成本对齐；
> Sharpe 差异有统计显著性；试过 N 组参数就要在结论里写明 N（多重检验）。

## 三、收尾清单（每次迭代结束前）

- [ ] **生产链路未破坏**：以下页面全部 200 ——
      `/` `/overview` `/strategies` `/trades` `/compare` `/lab` `/reports` `/jobs`
      `/scheduler` `/assistant` `/research/` `/research/runs` `/research/run/<id>`
      （至少测一个），`/research/compare?runs=a,b`
- [ ] **缓存隔离未破坏**：检查 `dispatch/state/signals_cache/prod/` 和
      `dispatch/state/signals_cache/research/` 目录各存各的，没有互相污染；
      生产缓存文件最后修改时间在最近一次 pipeline 之后
- [ ] **生产数值未漂移**：改了 `kernel/sim_engine.py` 的话，必须跑一次
      kernel/shim 数值一致性测试（同一 pivot+signals，新旧接口逐笔成交相等）
- [ ] **测试脚本清理**：临时验证脚本放 `%TEMP%`，不进仓库；
      有价值的长留测试放 `tests/`
- [ ] **TODO.md 更新**：完成项打勾并标注日期；新发现的缺口记入 backlog
- [ ] **文档同步**（见第四节触发条件）
- [ ] **git 提交**：按规范（第五节），实验数据文件（research.db）不提交

## 四、文档同步触发条件

改了以下任何一项，**同一次提交内**必须更新对应文档：

| 改动 | 必须更新 |
|---|---|
| 新增/删除 Web 页面或路由 | README.md（Web 页列表）+ QUICKSTART.md |
| 目录结构调整（新增包、移动模块） | README.md（仓库结构）+ ARCHITECTURE.md |
| 新增策略 | README.md（策略目录）+ `research/docs/strategies/` 新增分文档 |
| 新增/修改环境变量或 .env 配置 | QUICKSTART.md（配置节） |
| 修改每日 pipeline 行为或调度时间 | ARCHITECTURE.md + CYCLE.md（健康检查节） |
| 新增指标/实验类型 | ARCHITECTURE.md（研究层节） |
| 迭代流程本身变化 | 本文件（CYCLE.md） |

## 五、Git 提交规范

- 提交信息格式：`<类型>: <一句话说明>`，参考历史
  （`feat:` 新功能 / `fix:` 修复 / `docs:` 纯文档 / `chore:` 杂项 / `refactor:` 重构）
- **不提交**：`dispatch/state/research.db*`（实验数据）、`trades.db*`、
  `strategy_state.json`、缓存 parquet、邮件归档、`.env`（均在 .gitignore）
- **提交前**确认 `git status` 里无上述文件
- 一次提交做一件事；文档更新与对应代码改动同提交
- 不 push、不改 git 配置，除非用户明确要求

## 六、生产链路红线（任何时候不得违反）

1. **trades.db 与 research.db 物理隔离** — 生产战绩表永远不被研究实验写入
2. **缓存 scope 分离** — 生产 pipeline 传 `cache_scope="prod"`（sim_runner.py:85），
   实验默认 `"research"`；信号缓存与模型文件各自独立目录
3. **每日 15:35 pipeline 行为稳定** — 改动 kernel 层时保持
   `services/sim_engine.py` shim 的默认成本常量不变（0.001/0.001/0.001）
4. **参数未晋升前不影响生产** — 在 /strategies 改参数 ≠ 改生产参数；
   生产读 deployments 表（P1 实施）或注册中心默认值（当前过渡态）
5. **邮件格式变化需谨慎** — 收件人每天看，版式突变要单独说明
6. **重启 Web 服务先杀旧进程** — 否则新代码不生效且表现为"改了没反应"

## 七、每日自动运行（无需人工）

| 时间 | 任务 | 负责 |
|---|---|---|
| 15:35 交易日 | 数据更新 → 信号 → 重模拟 → 推荐邮件 + 表现邮件 + 企业微信 | Web 进程内 APScheduler |
| 周日 03:00 | 数据清理 | 同上 |
| 登录时 | Web 服务自启 | Windows 任务计划 QuantWeb |
