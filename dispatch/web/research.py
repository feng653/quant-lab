"""
Research blueprint — experiment launcher, leaderboard, detail, compare.

Four pages:
  /research             landing + experiment launcher
  /research/runs        sortable run leaderboard with filters
  /research/run/<id>    single run deep dive
  /research/compare     head-to-head comparison of selected runs

This is the core of the P0 milestone: every backtest result is now persistent
and queryable, not just a one-time output in job_runner memory.
"""

from __future__ import annotations

import logging

from flask import Blueprint, request, redirect
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from charts.generator import fig_to_base64
from research.store import (list_runs, get_run, get_equity, get_trades,
                             distinct_values, stats, delete_run, set_run_fields)
from kernel.runner import RunSpec, execute_and_save
from kernel.sim_engine import CostModel, INITIAL_CASH
from core.strategies.registry import scan_strategies
from web.ui import page, card, scard, table, cls, num, signed
from services.signal_service import strategy_meta

logger = logging.getLogger(__name__)
bp = Blueprint("research", __name__, url_prefix="/research")

scan_strategies()
STRATEGY_META = strategy_meta()
LABELS = {k: v["label"] for k, v in STRATEGY_META.items()}


# ═══════════════════════════════════════════════════════════════
# /research — landing + launcher
# ═══════════════════════════════════════════════════════════════

@bp.route("/")
def landing():
    st = stats()
    cards = (scard("实验总数", str(st["n_runs"]), f"{st['n_strategies']} 个策略") +
             scard("参数扫描", str(st["n_sweeps"]), "网格搜索历史") +
             scard("成交笔数", f"{st['n_trades']:,}", "跨所有run"))

    strat_opts = "".join(f"<option value='{k}'>{LABELS.get(k, k)}</option>"
                         for k in sorted(STRATEGY_META.keys()))

    form = f"""
<form method='post' action='/research/launch' class='filters' style='display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px'>
  <div><label style='font-size:12px;color:var(--sub)'>策略</label><br>
    <select name='strategy' required style='width:100%'>{strat_opts}</select></div>
  <div><label style='font-size:12px;color:var(--sub)'>起始日期</label><br>
    <input type='date' name='start' required style='width:100%' value='2024-06-01'></div>
  <div><label style='font-size:12px;color:var(--sub)'>结束日期</label><br>
    <input type='date' name='end' style='width:100%' placeholder='默认最新'></div>
  <div><label style='font-size:12px;color:var(--sub)'>股票池</label><br>
    <select name='pool' style='width:100%'>
      <option value='csi500' selected>CSI 500</option>
      <option value='csi800'>CSI 800</option>
    </select></div>
  <div><label style='font-size:12px;color:var(--sub)'>模式</label><br>
    <select name='mode' style='width:100%'>
      <option value='equal' selected>等权</option>
      <option value='adaptive'>自适应</option>
    </select></div>
  <div><label style='font-size:12px;color:var(--sub)'>标签（可选）</label><br>
    <input type='text' name='tag' style='width:100%' placeholder='v2.1'></div>
  <div style='display:flex;align-items:flex-end'><button type='submit' style='width:100%'>🚀 启动实验</button></div>
</form>
<div class='warn'>提交后同步执行（约15~60秒，期间页面会等待），完成后自动跳转到该实验的详情页；
全部历史实验见 <a href='/research/runs'>实验列表</a></div>
"""

    body = f"<div class='grid'>{cards}</div>" + card("实验发射台", form)
    return page("研究", body, "/research")


@bp.route("/launch", methods=["POST"])
def launch():
    spec = RunSpec(
        strategy=request.form.get("strategy", ""),
        start=request.form.get("start", ""),
        end=request.form.get("end") or None,
        pool=request.form.get("pool", "csi500"),
        mode=request.form.get("mode", "equal"),
        tag=request.form.get("tag", "").strip(),
        kind="backtest",
        update_data=False,
    )
    try:
        rid = execute_and_save(spec)
        return redirect(f"/research/run/{rid}")
    except Exception as e:
        logger.exception("Launch failed")
        return page("启动失败", card("错误", f"<pre>{e}</pre>"), "/research")


# ═══════════════════════════════════════════════════════════════
# /research/runs — leaderboard
# ═══════════════════════════════════════════════════════════════

@bp.route("/runs")
def runs_list():
    strategy = request.args.get("strategy", "")
    tag = request.args.get("tag", "")
    pool = request.args.get("pool", "")
    order = request.args.get("order", "created_at")
    desc = request.args.get("desc", "1") == "1"

    runs = list_runs(strategy=strategy, tag=tag, pool=pool, order_by=order, desc=desc, limit=300)

    strat_opts = "".join(f"<option value='{s}' {'selected' if s==strategy else ''}>{LABELS.get(s,s)}</option>"
                         for s in [""] + distinct_values("strategy"))
    tag_opts = "".join(f"<option value='{t}' {'selected' if t==tag else ''}>{t}</option>"
                       for t in [""] + distinct_values("tag"))
    pool_opts = "".join(f"<option value='{p}' {'selected' if p==pool else ''}>{p}</option>"
                        for p in [""] + distinct_values("pool"))

    filters = f"""
<form method='get' class='filters'>
  <select name='strategy'><option value=''>全部策略</option>{strat_opts}</select>
  <select name='tag'><option value=''>全部标签</option>{tag_opts}</select>
  <select name='pool'><option value=''>全部池</option>{pool_opts}</select>
  <select name='order'>
    <option value='created_at' {'selected' if order=='created_at' else ''}>创建时间</option>
    <option value='sharpe' {'selected' if order=='sharpe' else ''}>Sharpe</option>
    <option value='annual_return' {'selected' if order=='annual_return' else ''}>年化收益</option>
    <option value='calmar' {'selected' if order=='calmar' else ''}>Calmar</option>
    <option value='sortino' {'selected' if order=='sortino' else ''}>Sortino</option>
  </select>
  <label style='font-size:12px'><input type='checkbox' name='desc' value='1' {'checked' if desc else ''}> 降序</label>
  <button type='submit'>筛选</button>
  <a href='/research/runs' style='margin-left:8px;font-size:12px;color:var(--sub)'>清空</a>
</form>
"""

    headers = ["ID", "策略", "标签", "窗口", "天数", "池", "模式", "年化%", "Sharpe",
               "Sortino", "Calmar", "MaxDD%", "波动%", "胜率%", "成交", "创建时间"]
    rows = []
    for r in runs:
        rid = r["id"]
        rows.append([
            f"<a href='/research/run/{rid}' class='mono'>{rid[:8]}</a>",
            LABELS.get(r["strategy"], r["strategy"]),
            f"<span class='pill'>{r['tag']}</span>" if r.get("tag") else "<span class='dim'>—</span>",
            f"<span class='mono dim' style='font-size:10px'>{r['window_start']} ~ {r['window_end']}</span>",
            str(r.get("n_days") or 0),
            r.get("pool", ""),
            r.get("mode", "equal"),
            signed(r.get("annual_return"), 2, "%"),
            num(r.get("sharpe"), 3),
            num(r.get("sortino"), 3),
            num(r.get("calmar"), 3),
            signed(r.get("max_dd"), 2, "%", invert=True),
            num(r.get("volatility"), 2, "%"),
            num(r.get("win_rate"), 1, "%"),
            str(r.get("n_trades") or 0),
            f"<span class='mono dim' style='font-size:10px'>{r['created_at'][:16]}</span>",
        ])

    tbl = table(headers, rows, sortable=True, css_class="lb")
    summary = f"<p style='color:var(--sub);font-size:12px'>共 {len(runs)} 个实验，按 {order} {'降序' if desc else '升序'}</p>"
    body = card("实验排行榜", filters + summary + tbl,
                extra=" <a href='/research' style='float:right;font-size:12px'>🚀 新建</a>")
    return page("实验列表", body, "/research")


# ═══════════════════════════════════════════════════════════════
# /research/run/<id> — detail
# ═══════════════════════════════════════════════════════════════

@bp.route("/run/<run_id>")
def run_detail(run_id: str):
    r = get_run(run_id)
    if r is None:
        return page("未找到", card("错误", f"Run {run_id} 不存在"), "/research")

    equity_list = get_equity(run_id)
    trades_list = get_trades(run_id, limit=1000)

    # header
    label = LABELS.get(r["strategy"], r["strategy"])
    tag_badge = f"<span class='pill'>{r['tag']}</span>" if r.get("tag") else ""
    hdr = f"<h2>{label} {tag_badge} <span class='mono dim' style='font-size:14px'>{run_id}</span></h2>"

    # metadata
    params_str = str(r.get("params", {})) if r.get("params") else "默认"
    cost_model = r.get("cost") or {}
    cost_str = f"{cost_model.get('commission', 0.001)*10000:.1f} bp 佣金, {cost_model.get('slippage', 0.001)*10000:.1f} bp 滑点"

    meta_grid = f"""
<div class='kv'>
  <div class='k'>策略</div><div>{r['strategy']}</div>
  <div class='k'>窗口</div><div>{r['window_start']} ~ {r['window_end']} ({r.get('n_days', 0)} 天)</div>
  <div class='k'>股票池</div><div>{r.get('pool', 'csi500')}</div>
  <div class='k'>模式</div><div>{r.get('mode', 'equal')}</div>
  <div class='k'>调仓周期</div><div>{r.get('rebalance_days', 30)} 天</div>
  <div class='k'>最大持仓</div><div>{r.get('max_positions', 20)}</div>
  <div class='k'>成本模型</div><div>{cost_str}</div>
  <div class='k'>参数</div><div class='mono' style='font-size:11px'>{params_str}</div>
  <div class='k'>数据版本</div><div class='mono dim' style='font-size:10px'>{r.get('data_version', '—')}</div>
  <div class='k'>代码版本</div><div class='mono dim' style='font-size:10px'>{r.get('code_version', '—')}</div>
  <div class='k'>耗时</div><div>{r.get('duration_sec', 0):.2f} 秒</div>
  <div class='k'>创建时间</div><div>{r.get('created_at', '')[:19]}</div>
</div>
"""

    # metrics
    m = r.get("metrics", {})
    metric_cards = (
        scard("总收益", signed(m.get("total_return"), 2, "%"), f"起始 {INITIAL_CASH:,.0f}") +
        scard("年化收益", signed(m.get("annual_return"), 2, "%"), f"Sharpe {num(m.get('sharpe'), 3)}") +
        scard("最大回撤", signed(m.get("max_dd"), 2, "%", invert=True),
              f"持续 {m.get('max_dd_duration', 0)} 天") +
        scard("波动率", num(m.get("volatility"), 2, "%"), f"下行 {num(m.get('downside_vol'), 2, '%')}") +
        scard("Sortino", num(m.get("sortino"), 3), f"Calmar {num(m.get('calmar'), 3)}") +
        scard("胜率", num(m.get("win_rate"), 1, "%"),
              f"盈亏比 {num(m.get('profit_factor'), 2)}") +
        scard("成交笔数", str(m.get("n_trades", 0)),
              f"换手 {num(m.get('turnover_ratio'), 2)}") +
        scard("成本拖累", num(m.get("cost_drag_pct"), 2, "%"),
              f"总成本 {num(m.get('total_cost'), 0)}")
    )
    if m.get("alpha") is not None:
        metric_cards += (
            scard("Alpha", signed(m.get("alpha"), 2, "%"), f"Beta {num(m.get('beta'), 3)}") +
            scard("IR", num(m.get("info_ratio"), 3), f"超额 {signed(m.get('excess_return'), 2, '%')}")
        )

    # equity chart
    chart_html = ""
    if equity_list:
        idx = pd.to_datetime([e["date"] for e in equity_list])
        eq = pd.Series([e["equity"] for e in equity_list], index=idx)
        fig, ax = plt.subplots(figsize=(11, 5))
        ax.plot(eq.index, eq.values, color="#4472C4", linewidth=1.8, label="净值")
        ax.axhline(y=INITIAL_CASH, color="gray", linestyle=":", alpha=0.5, label="起始")
        peak = eq.cummax()
        ax.fill_between(eq.index, eq.values, peak.values, where=(eq < peak),
                         color="#c62828", alpha=0.15, label="回撤")
        ax.legend(fontsize=9, loc="best")
        ax.set_title(f"{label} 净值曲线", fontsize=13, fontweight="bold")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        chart_html = f"<img src='data:image/png;base64,{fig_to_base64(fig)}' style='width:100%'>"

    # trades sample
    trades_rows = []
    for t in trades_list[:50]:
        bg = "#e8f5e9" if t["action"] == "buy" else "#fce4ec"
        trades_rows.append([
            f"<span style='background:{bg};padding:2px 6px;border-radius:3px'>{t['date']}</span>",
            t["code"],
            "买入" if t["action"] == "buy" else "卖出",
            str(t["shares"]),
            f"{t['price']:.2f}",
            f"{t['value']:,.0f}",
            f"{t['commission']:.2f}",
        ])
    trades_tbl = table(["日期", "代码", "方向", "股数", "价格", "金额", "佣金"], trades_rows) if trades_rows else "<p class='dim'>无成交</p>"
    trades_note = f"<p style='font-size:11px;color:var(--sub)'>显示前50笔，共 {len(trades_list)} 笔</p>" if len(trades_list) > 50 else ""

    # actions
    actions = f"""
<div style='margin-top:16px;display:flex;gap:10px'>
  <a href='/research/runs'><button class='secondary'>← 返回列表</button></a>
  <a href='/research/compare?runs={run_id}'><button>📊 加入对比</button></a>
  <form method='post' action='/research/run/{run_id}/delete' style='display:inline' 
        onsubmit='return confirm("确定删除此实验？")'>
    <button type='submit' class='secondary' style='background:#c62828;color:#fff'>🗑 删除</button>
  </form>
</div>
"""

    body = (hdr + card("元数据", meta_grid) +
            f"<div class='grid'>{metric_cards}</div>" +
            card("净值曲线", chart_html) +
            card("成交记录", trades_note + trades_tbl) +
            actions)
    return page(f"{label} - {run_id[:8]}", body, "/research")


@bp.route("/run/<run_id>/delete", methods=["POST"])
def run_delete(run_id: str):
    delete_run(run_id)
    return redirect("/research/runs")


# ═══════════════════════════════════════════════════════════════
# /research/compare — head-to-head
# ═══════════════════════════════════════════════════════════════

@bp.route("/compare")
def compare():
    run_ids = request.args.get("runs", "").split(",")
    run_ids = [r.strip() for r in run_ids if r.strip()]

    if len(run_ids) < 2:
        hint = f"""
<p>通过 URL 参数指定 run ID，例如 <code>/research/compare?runs=abc123,def456</code></p>
<p>或从实验详情页点击"加入对比"按钮</p>
<p><a href='/research/runs'>→ 实验列表</a></p>
"""
        return page("对比", card("选择实验", hint), "/research")

    runs_data = [get_run(rid) for rid in run_ids]
    runs_data = [r for r in runs_data if r is not None]

    if len(runs_data) < 2:
        return page("对比", card("错误", "至少需要2个有效run"), "/research")

    # header
    titles = " vs ".join(f"{LABELS.get(r['strategy'], r['strategy'])} ({r['id'][:8]})"
                         for r in runs_data)
    hdr = f"<h2>对比：{titles}</h2>"

    # metrics table
    metric_keys = [("total_return", "总收益 %"), ("annual_return", "年化 %"),
                   ("sharpe", "Sharpe"), ("sortino", "Sortino"), ("calmar", "Calmar"),
                   ("max_dd", "最大回撤 %"), ("volatility", "波动 %"),
                   ("win_rate", "胜率 %"), ("n_trades", "成交笔数"),
                   ("turnover_ratio", "换手"), ("alpha", "Alpha %"), ("beta", "Beta")]
    headers = ["指标"] + [f"{LABELS.get(r['strategy'], r['strategy'])} ({r['id'][:6]})"
                         for r in runs_data]
    rows = []
    for k, label in metric_keys:
        vals = [r.get("metrics", {}).get(k) for r in runs_data]
        if all(v is None or v == "" for v in vals):
            continue
        row = [label]
        for v in vals:
            if k in ("sharpe", "sortino", "calmar", "turnover_ratio", "beta"):
                row.append(num(v, 3))
            elif k == "n_trades":
                row.append(str(int(v)) if v else "—")
            elif k in ("total_return", "annual_return", "max_dd", "volatility", "win_rate", "alpha"):
                row.append(signed(v, 2, "%", invert=(k == "max_dd")))
            else:
                row.append(num(v, 2))
        rows.append(row)

    metric_tbl = table(headers, rows)

    # equity overlay
    chart_html = ""
    try:
        fig, ax = plt.subplots(figsize=(11, 5))
        colors = ["#4472C4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
        for i, r in enumerate(runs_data):
            eq_list = get_equity(r["id"])
            if not eq_list:
                continue
            idx = pd.to_datetime([e["date"] for e in eq_list])
            eq = pd.Series([e["equity"] for e in eq_list], index=idx)
            norm = eq / eq.iloc[0]
            label_str = f"{LABELS.get(r['strategy'], r['strategy'])} ({r['id'][:6]})"
            ax.plot(norm.index, norm.values, color=colors[i % len(colors)],
                    linewidth=1.5, label=label_str)
        ax.axhline(y=1.0, color="gray", linestyle=":", alpha=0.5)
        ax.legend(fontsize=9, loc="best")
        ax.set_title("归一化净值对比", fontsize=13, fontweight="bold")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        chart_html = f"<img src='data:image/png;base64,{fig_to_base64(fig)}' style='width:100%'>"
    except Exception as e:
        logger.exception("Chart failed")
        chart_html = f"<p class='dim'>图表生成失败: {e}</p>"

    body = hdr + card("指标对比", metric_tbl) + card("净值叠加", chart_html)
    return page("对比", body, "/research")
