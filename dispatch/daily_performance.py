"""
Daily Performance Email (rebuilt) — 10 strategies × 2 sizing modes, real simulation.

Every strategy is independently simulated from simulation_start (fixed, labeled
in the email header) with full trade-level records in SQLite. The email contains:
overview, market regime, performance table with benchmark excess return,
equal-vs-adaptive comparison, per-strategy dual-line charts with CSI 500
benchmark, cost breakdown, correlation heatmap, today's trade detail,
and optional AI commentary.

Schedule: 16:00 daily via Task Scheduler (or via run_daily.py).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ROOT = Path(__file__).resolve().parent


def _fmt_pct(v, signed=True):
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def build_performance_html(ctx: dict, ai_text: str | None = None) -> str:
    from services import trade_db
    from charts.generator import correlation_heatmap, cost_bar_chart, strategy_dual_chart

    state = ctx["state"]; market = ctx["market"]; bench = ctx["benchmark"]
    sim_start = ctx["sim_start"]; latest = ctx["latest_date"]; n_days = ctx["n_days"]
    today = datetime.now().strftime("%Y-%m-%d"); now = datetime.now().strftime("%H:%M")
    bench_ret = next(iter(state["strategies"].values()))["equal"]["bench_ret"] if state["strategies"] else 0

    # ── sort strategies by equal-mode sharpe (enabled only; disabled listed separately) ──
    disabled = {k: v for k, v in state["strategies"].items() if v.get("disabled")}
    keys = sorted([k for k in state["strategies"] if k not in disabled],
                  key=lambda k: state["strategies"][k]["equal"]["sharpe"], reverse=True)
    disabled_note = ""
    if disabled:
        parts = [f"{v['label']}（{v.get('note', '已停用')}）" for v in disabled.values()]
        disabled_note = "<p style='color:#999;font-size:11px'>已停用策略（保留历史，不再模拟/推荐）: " + " | ".join(parts) + "</p>"

    # ── overview cards ──
    total_assets = sum(state["strategies"][k]["equal"]["final_equity"] for k in keys)
    avg_ret = sum(state["strategies"][k]["equal"]["total_return"] for k in keys) / max(len(keys), 1)
    n_beat = sum(1 for k in keys if state["strategies"][k]["equal"]["total_return"] > bench_ret)
    best_k = keys[0] if keys else None

    # ── performance table (equal mode) ──
    rows = ""
    for k in keys:
        e = state["strategies"][k]["equal"]
        lb = state["strategies"][k]["label"]
        excess = e["total_return"] - bench_ret
        em = "🟢" if e["sharpe"] > 0.5 else ("🟡" if e["sharpe"] > 0 else "🔴")
        rows += (f"<tr><td style='text-align:left'>{em} <b>{lb}</b></td>"
                 f"<td class='{'green' if e['today_return']>0 else 'red'}'>{_fmt_pct(e['today_return'])}</td>"
                 f"<td class='{'green' if e['total_return']>0 else 'red'}'>{_fmt_pct(e['total_return'])}</td>"
                 f"<td>{_fmt_pct(e['annual_return'])}</td><td>{e['sharpe']:.3f}</td>"
                 f"<td class='red'>{_fmt_pct(e['max_dd'])}</td><td>{e['volatility']:.1f}%</td>"
                 f"<td>{len(e['positions'])}</td>"
                 f"<td class='{'green' if excess>0 else 'red'}'>{_fmt_pct(excess)}</td></tr>")

    # ── A/B mode comparison table ──
    ab_rows = ""
    for k in keys:
        eq = state["strategies"][k]["equal"]; ad = state["strategies"][k]["adaptive"]
        lb = state["strategies"][k]["label"]
        delta = ad["total_return"] - eq["total_return"]
        winner = "自适应" if delta > 0.1 else ("等权" if delta < -0.1 else "持平")
        ab_rows += (f"<tr><td style='text-align:left'><b>{lb}</b></td>"
                    f"<td class='{'green' if eq['total_return']>0 else 'red'}'>{_fmt_pct(eq['total_return'])}</td>"
                    f"<td class='red'>{_fmt_pct(eq['max_dd'])}</td><td>{eq['sharpe']:.3f}</td>"
                    f"<td class='{'green' if ad['total_return']>0 else 'red'}'>{_fmt_pct(ad['total_return'])}</td>"
                    f"<td class='red'>{_fmt_pct(ad['max_dd'])}</td><td>{ad['sharpe']:.3f}</td>"
                    f"<td class='{'green' if delta>0 else 'red'}'>{_fmt_pct(delta)}</td><td>{winner}</td></tr>")

    # ── per-strategy dual charts ──
    chart_parts = ['<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center">']
    for k in keys:
        e = state["strategies"][k]["equal"]; ad = state["strategies"][k]["adaptive"]
        lb = state["strategies"][k]["label"]
        idx = pd.to_datetime(e["dates"])
        s_eq = pd.Series(e["equity"], index=idx)
        s_ad = pd.Series(ad["equity"], index=pd.to_datetime(ad["dates"]))
        c = strategy_dual_chart(lb, s_eq, s_ad, bench, sim_start)
        if c:
            chart_parts.append(f'<div style="flex:1;min-width:480px;max-width:620px">{c}</div>')
    chart_parts.append("</div>")
    charts_html = "\n".join(chart_parts)

    # ── cost analysis ──
    snaps = trade_db.get_snapshots(mode="equal")
    tr_all = trade_db.get_trades(mode="equal", limit=100000)
    cost_rows = []
    for k in keys:
        e = state["strategies"][k]["equal"]; c = e["costs"]
        turnover = float(tr_all[tr_all["strategy"] == k]["value"].sum()) if not tr_all.empty else 0.0
        cost_rows.append({"label": state["strategies"][k]["label"], **c,
                          "turnover": turnover,
                          "pct": (c["total"] / turnover * 100) if turnover > 0 else 0})
    cost_tbl_rows = "".join(
        f"<tr><td style='text-align:left'><b>{r['label']}</b></td><td>{r['commission']:,.0f}</td>"
        f"<td>{r['stamp_duty']:,.0f}</td><td>{r['slippage']:,.0f}</td><td><b>{r['total']:,.0f}</b></td>"
        f"<td>{r['turnover']:,.0f}</td><td>{r['pct']:.2f}%</td></tr>" for r in cost_rows)
    cost_chart = cost_bar_chart(cost_rows)

    # ── correlation heatmap (equal-mode daily returns) ──
    heat_html, corr_note = "", ""
    if not snaps.empty:
        piv = snaps.pivot_table(index="date", columns="strategy", values="daily_ret")
        labels = {k: state["strategies"][k]["label"] for k in keys}
        piv = piv[[c for c in piv.columns]]
        corr = piv.corr()
        # find max/min off-diagonal pairs
        pairs = [(corr.index[i], corr.columns[j], corr.iloc[i, j])
                 for i in range(len(corr)) for j in range(i + 1, len(corr))]
        if pairs:
            mx = max(pairs, key=lambda x: x[2]); mn = min(pairs, key=lambda x: x[2])
            corr_note = (f"⚠️ 最高相关: <b>{labels.get(mx[0],mx[0])} × {labels.get(mx[1],mx[1])}</b> ({mx[2]:.2f}) — 同向性高，分散效果差 &nbsp;|&nbsp; "
                         f"✅ 最低相关: <b>{labels.get(mn[0],mn[0])} × {labels.get(mn[1],mn[1])}</b> ({mn[2]:.2f}) — 对冲效果好")
        heat_html = correlation_heatmap(piv, labels, f"策略日收益相关性矩阵 (模拟期 {sim_start} 起, {len(piv)} 个交易日)")

    # ── today's trades ──
    tr_today = trade_db.get_trades(mode="equal", date=latest, limit=500)
    if tr_today.empty:
        trades_rows = "<tr><td colspan='7' style='color:#999'>最近交易日无成交</td></tr>"
    else:
        labels = {k: state["strategies"][k]["label"] for k in keys}
        trades_rows = "".join(
            f"<tr style='background:{'#e8f5e9' if t['action']=='buy' else '#fce4ec'}'>"
            f"<td>{labels.get(t['strategy'], t['strategy'])}</td><td style='font-family:monospace'>{t['code']}</td>"
            f"<td>{'买入' if t['action']=='buy' else '卖出'}</td><td>{int(t['shares'])}</td>"
            f"<td>{t['price']:.2f}</td><td>{t['value']:,.0f}</td>"
            f"<td>{t['commission']+t['stamp_duty']+t['slippage_cost']:,.1f}</td></tr>"
            for _, t in tr_today.iterrows())

    # ── market regime card ──
    regime_strats = ", ".join(state["strategies"][s]["label"] for s in market.get("strategies", [])
                              if s in state["strategies"] and not state["strategies"][s].get("disabled"))
    ai_block = f'<div class="card"><h2>🤖 AI 市场评论</h2><p style="color:#333;font-size:13px;line-height:1.9">{ai_text}</p></div>' if ai_text else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{font-family:'Segoe UI','Microsoft YaHei',sans-serif;margin:20px;background:#f0f2f5}}
h1{{color:#1a1a2e;border-bottom:3px solid #4472C4;padding-bottom:8px}}
h2{{color:#333;margin:16px 0 8px 0}}
.card{{background:#fff;border-radius:10px;padding:16px;margin:12px 0;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
table{{border-collapse:collapse;width:100%}}
th{{background:#4472C4;color:#fff;padding:9px 6px;text-align:center;font-size:12px}}
td{{padding:7px 6px;text-align:center;border-bottom:1px solid #e8e8e8;font-size:12px}}
.green{{color:#2e7d32;font-weight:bold}}.red{{color:#c62828;font-weight:bold}}
.metrics{{display:flex;gap:14px;flex-wrap:wrap;margin:8px 0}}
.mc{{flex:1;min-width:120px;background:#f8f9fa;border-radius:8px;padding:12px;text-align:center}}
.mv{{font-size:21px;font-weight:bold;color:#1a1a2e}}.ml{{font-size:11px;color:#666;margin-top:4px}}
.hdr{{background:#1a1a2e;color:#fff;border-radius:10px;padding:14px 18px;margin:12px 0;font-size:13px;line-height:1.9}}
.hdr b{{color:#ffd54f}}
.footer{{color:#999;font-size:11px;margin-top:24px;border-top:1px solid #eee;padding-top:12px}}
</style></head><body>
<h1>📊 量化组合日报 — 10策略 × 双仓位模式 独立模拟</h1>
<div class="hdr">
<b>模拟起始: {sim_start}</b> | 已运行: <b>{n_days}</b> 个交易日 | 数据截止: <b>{latest}</b> | 生成: {today} {now}<br>
每策略独立账户 1,000,000 元 | 模式: 等权(实线) vs 自适应波动率仓位(虚线) | 基准: 中证500买入持有 | 全部成交记录见 SQLite (dispatch/state/trades.db)
</div>

<div class="card"><h2>💰 综合概览 (等权模式)</h2>
<div class="metrics">
<div class="mc"><div class="mv">{total_assets:,.0f}</div><div class="ml">10策略总资产</div></div>
<div class="mc"><div class="mv" style="color:{'#2e7d32' if avg_ret>=0 else '#c62828'}">{avg_ret:+.2f}%</div><div class="ml">平均累计收益</div></div>
<div class="mc"><div class="mv" style="color:{'#2e7d32' if bench_ret>=0 else '#c62828'}">{bench_ret:+.2f}%</div><div class="ml">中证500同期</div></div>
<div class="mc"><div class="mv">{n_beat}/{len(keys)}</div><div class="ml">跑赢基准策略数</div></div>
<div class="mc"><div class="mv">{state['strategies'][best_k]['label'] if best_k else '-'}</div><div class="ml">当前最佳策略</div></div>
</div></div>

<div class="card"><h2>🌐 市场环境</h2>
<p style='font-size:14px'><span style='color:{market["color"]};font-weight:bold;font-size:16px'>{market["label"]}</span>
&nbsp; {market["desc"]}<br>
<span style='color:#666;font-size:12px'>中证500: 近20日 {market["ret_20d"]:+.2f}% | 近60日 {market["ret_60d"]:+.2f}% | 20日年化波动率 {market["vol_20d"]}% | 收盘 {market.get("bench_close","-")}<br>
当前环境适配策略: <b>{regime_strats or "-"}</b></span></p></div>

<div class="card"><h2>🏆 策略表现 (等权模式, 累计收益 = 模拟起始以来)</h2>
<table><tr><th>策略</th><th>今日%</th><th>累计%</th><th>年化%</th><th>Sharpe</th><th>MaxDD</th><th>波动率</th><th>持仓</th><th>超额vs基准</th></tr>
{rows}</table></div>

<div class="card"><h2>🔀 仓位模式对比: 等权 vs 自适应波动率仓位</h2>
<p style='color:#666;font-size:12px'>自适应模式: 目标波动15%, 暴露 = clamp(0.15/市场20日波动, 0.3, 1.0)。高波动降仓位, 低波动加仓位。</p>
<table><tr><th>策略</th><th>等权累计%</th><th>等权DD</th><th>等权Sharpe</th><th>自适应累计%</th><th>自适应DD</th><th>自适应Sharpe</th><th>差值</th><th>更优</th></tr>
{ab_rows}</table></div>

<div class="card"><h2>📉 净值走势 (实线=等权, 虚线=自适应, 灰点线=中证500基准)</h2>{charts_html}</div>

<div class="card"><h2>💸 成本分析 (等权模式, 模拟期间累计)</h2>
<table><tr><th>策略</th><th>佣金(元)</th><th>印花税(元)</th><th>滑点(元)</th><th>总成本(元)</th><th>总成交额(元)</th><th>成本占比</th></tr>
{cost_tbl_rows}</table>{cost_chart}</div>

<div class="card"><h2>📊 策略相关性</h2>{heat_html}
<p style='color:#666;font-size:12px;line-height:1.7'>{corr_note}</p></div>

<div class="card"><h2>📝 最近交易日成交明细 ({latest}, 等权模式)</h2>
<table><tr><th>策略</th><th>代码</th><th>方向</th><th>股数</th><th>价格</th><th>金额(元)</th><th>成本(元)</th></tr>
{trades_rows}</table>
<p style='color:#999;font-size:11px'>完整历史成交: dispatch/state/trades.db → trades 表 | 或运行 Web 仪表盘查看</p></div>

{ai_block}

{disabled_note}
<div class="card"><h2>⚠️ 风险提示</h2><p style='color:#666;font-size:11px;line-height:1.7'>
⛔ 本报告由量化模型自动生成, 全部为模拟交易, 不构成投资建议。模拟起始 {sim_start}, 历史表现不代表未来收益。
交易成本已计入(佣金0.1%双边+印花税0.1%卖出+滑点0.1%)。Pairs策略需要做空能力, 其模拟结果仅供参考。</p></div>
<p class="footer">Generated by quant-lab | dispatch/daily_performance.py | {today} {now}</p></body></html>"""


def build_ai_context(ctx: dict) -> str:
    state = ctx["state"]; m = ctx["market"]
    lines = [f"市场环境: {m['label']}, 中证500近20日{m['ret_20d']}%, 近60日{m['ret_60d']}%, 20日年化波动率{m['vol_20d']}%",
             f"模拟起始: {ctx['sim_start']}, 已运行{ctx['n_days']}个交易日, 基准中证500同期{ctx['benchmark'].iloc[-1]/ctx['benchmark'].iloc[0]*100-100:+.2f}%",
             "策略表现(等权, 累计收益/Sharpe):"]
    keys = sorted([k for k in state["strategies"] if not state["strategies"][k].get("disabled")],
                  key=lambda k: state["strategies"][k]["equal"]["sharpe"], reverse=True)
    for k in keys:
        e = state["strategies"][k]["equal"]
        lines.append(f"  {state['strategies'][k]['label']}: {e['total_return']:+.2f}% (Sharpe {e['sharpe']:+.2f}, MaxDD {e['max_dd']:+.1f}%)")
    return "\n".join(lines)


def save_mail(html: str, prefix: str) -> Path:
    t = datetime.now()
    md = ROOT / "mail" / t.strftime("%Y%m")
    md.mkdir(parents=True, exist_ok=True)
    fn = md / f"{prefix}_{t.strftime('%Y%m%d')}.html"
    for old in md.glob(f"{prefix}_{t.strftime('%Y%m%d')}*.html"):
        if old != fn:
            old.unlink()
    fn.write_text(html, encoding="utf-8")
    return fn


def main(run_sim: bool = True):
    from services.data_service import is_trading_day
    if not is_trading_day():
        logger.info("Skip: not trading day")
        return
    if run_sim:
        from services.sim_runner import run_simulation
        ctx = run_simulation()
    else:
        raise ValueError("run_sim=False only used via run_daily")

    from ai_commentary import generate_commentary
    ai_text = generate_commentary(build_ai_context(ctx))
    html = build_performance_html(ctx, ai_text)

    from notify.email_qq import send_daily_report
    ok = send_daily_report(f"[量化日报] {datetime.now().strftime('%Y-%m-%d')} 10策略双模式模拟 (起始{ctx['sim_start']})", html)
    logger.info("Email: %s", "OK" if ok else "FAIL")
    p = save_mail(html, "performance")
    logger.info("Saved: %s", p)


if __name__ == "__main__":
    main()
