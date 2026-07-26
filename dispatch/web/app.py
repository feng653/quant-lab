"""
quant-lab one-stop web service — homepage, dashboards, admin, lab, reports.

  python dispatch/web/app.py   →   http://localhost:8600

Port: 8600 default (8080 conflicts with qBittorrent). Override via DASH_PORT
in .env / environment, or `--port N`.

On startup: strategy registry scan + APScheduler (daily 15:35 pipeline,
weekly Sun 03:00 cleanup). This process is the all-day service: Task
Scheduler "QuantWeb" launches it at logon.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from flask import Flask, jsonify, request

from charts.generator import fig_to_base64
from services import trade_db
from services.signal_service import strategy_meta
from services.sim_runner import load_state
from services.market_service import classify_market

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

app = Flask(__name__)

STRATEGY_META = strategy_meta()
LABELS = {k: v["label"] for k, v in STRATEGY_META.items()}
COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
          "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

# page shell / CSS / nav now live in web.ui.layout — imported here so the
# existing `from web.app import page` calls in blueprints keep working.
from web.ui.layout import BASE_CSS, NAV_ITEMS, nav, page  # noqa: E402,F401


# ═══════════════════════════════════════════════════════════════
# HOMEPAGE — latest daily report embedded
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def home():
    from web.reports import latest_report_path
    rec = latest_report_path("recommend")
    perf = latest_report_path("performance")

    def frame(p, label):
        if p is None:
            return f"<div class='card' style='text-align:center;color:#999;padding:40px'>{label}报告尚未生成</div>"
        rel = f"{p.parent.name}/{p.name}"
        return (f"<div class='card'><h3>{label} <small style='color:#666'>{p.stem.split('_')[-1]}</small>"
                f"<a href='/reports/file/{rel}' target='_blank' style='float:right;font-size:12px'>新窗口打开 ↗</a></h3>"
                f"<iframe class='report' src='/reports/file/{rel}'></iframe></div>")

    navcards = "".join(
        f"<a class='navcard' href='{u}'><div class='ico'>{t.split()[0]}</div><div class='t'>{t.split(None,1)[1]}</div><div class='d'>{d}</div></a>"
        for u, t, d in [
            ("/overview", "📊 总览", "策略卡片/净值对比/最新成交"),
            ("/strategies", "🎛️ 策略管理", "启用开关/参数调整/AI推荐参数/自动检测"),
            ("/lab", "🧪 实验室", "数据拉取/一键训练/一键回测"),
            ("/assistant", "🤖 AI助手", "自然语言管理数据与任务"),
            ("/trades", "📝 成交记录", "逐笔成交/分组汇总/盈亏配对"),
            ("/compare", "📈 策略对比", "自选策略净值对比"),
            ("/reports", "📁 历史报告", "每日推荐+表现报告存档"),
            ("/scheduler", "⏰ 调度中心", "每日pipeline状态与手动触发"),
        ])
    body = f"""
{frame(perf, '📊 最新表现报告')}
{frame(rec, '📈 最新推荐报告')}
<div class='grid' style='margin-top:16px'>{navcards}</div>"""
    return page("主页", body, "/")


# ═══════════════════════════════════════════════════════════════
# OVERVIEW (former homepage)
# ═══════════════════════════════════════════════════════════════

def _equity_df(mode: str = "equal") -> pd.DataFrame:
    snaps = trade_db.get_snapshots(mode=mode)
    if snaps.empty:
        return pd.DataFrame()
    return snaps.pivot_table(index="date", columns="strategy", values="equity")


def _equity_chart(series_map: dict[str, pd.Series], title: str, normalize: bool = True) -> str:
    fig, ax = plt.subplots(figsize=(11, 5))
    for i, (name, s) in enumerate(series_map.items()):
        if len(s) < 2:
            continue
        v = s / s.iloc[0] if normalize else s
        ax.plot(v.index, v.values, color=COLORS[i % len(COLORS)], linewidth=1.5, label=name)
    if normalize:
        ax.axhline(y=1.0, color="gray", linestyle=":", alpha=0.5)
    ax.legend(fontsize=9, loc="best")
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig_to_base64(fig)


@app.route("/overview")
def overview():
    state = load_state()
    strats = state.get("strategies", {})
    meta = state.get("meta", {})
    market = classify_market()

    cards = ""
    keys = sorted(strats, key=lambda k: strats[k]["equal"].get("sharpe", -99), reverse=True)
    for k in keys:
        s = strats[k]
        e = s["equal"]
        ret = e.get("total_return", 0)
        cls = "green" if ret > 0 else "red"
        off = " <span class='badge-off'>已停用</span>" if s.get("disabled") else ""
        style = "opacity:0.55;" if s.get("disabled") else ""
        cards += (f"<div class='scard' style='{style}'><h3><a href='/strategy/{k}'>{s['label']}</a>{off}</h3>"
                  f"<div class='big {cls}'>{ret:+.2f}%</div>"
                  f"<div class='sub'>Sharpe {e.get('sharpe',0):.3f} | MaxDD {e.get('max_dd',0):+.1f}%<br>"
                  f"今日 {e.get('today_return',0):+.2f}% | 持仓 {len(e.get('positions',{}))}<br>"
                  f"自适应 {s.get('adaptive',{}).get('total_return',0):+.2f}%</div></div>")

    eq = _equity_df("equal")
    series = {LABELS.get(c, c): pd.Series(eq[c].values, index=pd.to_datetime(eq.index)) for c in eq.columns}
    chart = _equity_chart(series, f"策略净值对比 (起始 {meta.get('simulation_start','-')}, 等权模式)") if not eq.empty else ""

    latest = trade_db.latest_date()
    tr = trade_db.get_trades(mode="equal", date=latest, limit=100)
    tr_rows = "".join(
        f"<tr style='background:{'#e8f5e9' if t['action']=='buy' else '#fce4ec'}'>"
        f"<td>{t['date']}</td><td>{LABELS.get(t['strategy'], t['strategy'])}</td>"
        f"<td style='font-family:monospace'>{t['code']}</td>"
        f"<td>{'买入' if t['action']=='buy' else '卖出'}</td><td>{int(t['shares'])}</td>"
        f"<td>{t['price']:.2f}</td><td>{t['value']:,.0f}</td></tr>"
        for _, t in tr.iterrows()) or "<tr><td colspan='7'>最近交易日无成交</td></tr>"

    enabled_keys = [k for k in keys if not strats[k].get("disabled")]
    bench_ret = strats[enabled_keys[0]]["equal"].get("bench_ret", 0) if enabled_keys else 0
    body = f"""
<div class='card'><b>模拟起始:</b> {meta.get('simulation_start','-')} &nbsp;|&nbsp;
<b>数据截止:</b> {latest} &nbsp;|&nbsp; <b>市场:</b> <span style='color:{market['color']}'>{market['label']}</span>
(中证500近20日 {market['ret_20d']:+.2f}% | 同期基准 {bench_ret:+.2f}%) &nbsp;|&nbsp;
<b>更新:</b> {meta.get('updated','-')[:16]}</div>
<div class='grid'>{cards}</div>
<div class='card'>{chart}</div>
<div class='card'><h3>最近交易日成交 ({latest}, 等权模式) — <a href='/trades'>全部记录</a></h3>
<table><tr><th>日期</th><th>策略</th><th>代码</th><th>方向</th><th>股数</th><th>价格</th><th>金额</th></tr>{tr_rows}</table></div>"""
    return page("总览", body, "/overview")


# ═══════════════════════════════════════════════════════════════
# STRATEGY DETAIL (with trade markers on equity chart)
# ═══════════════════════════════════════════════════════════════

def _equity_with_markers(name: str, s: dict, trades: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(11, 5))
    series_map = {"等权": ("equal", "-"), "自适应": ("adaptive", "--")}
    color = "#4472C4"
    for cn, (mode, ls) in series_map.items():
        e = s.get(mode)
        if not e or not e.get("equity"):
            continue
        idx = pd.to_datetime(e["dates"])
        nav = pd.Series(e["equity"], index=idx) / e["equity"][0]
        ax.plot(nav.index, nav.values, linewidth=1.6, linestyle=ls, label=f"{cn} {((nav.iloc[-1]-1)*100):+.1f}%")
    if not trades.empty:
        eq_dates = pd.to_datetime(s["equal"]["dates"])
        eq_vals = pd.Series(s["equal"]["equity"], index=eq_dates) / s["equal"]["equity"][0]
        for _, t in trades.iterrows():
            td = pd.Timestamp(t["date"])
            if td not in eq_vals.index:
                continue
            y = eq_vals[td]
            if t["action"] == "buy":
                ax.scatter([td], [y * 0.985], marker="^", color="#2e7d32", s=45, zorder=5)
            else:
                ax.scatter([td], [y * 1.015], marker="v", color="#c62828", s=45, zorder=5)
        from matplotlib.lines import Line2D
        ax.scatter([], [], marker="^", color="#2e7d32", s=45, label="买入")
        ax.scatter([], [], marker="v", color="#c62828", s=45, label="卖出")
    ax.axhline(y=1.0, color="gray", linestyle=":", alpha=0.5)
    ax.legend(fontsize=9, loc="best")
    ax.set_title(f"{name} 净值与成标点 (▲买 ▼卖)", fontsize=13, fontweight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig_to_base64(fig)


@app.route("/strategy/<name>")
def strategy_detail(name: str):
    state = load_state()
    strats = state.get("strategies", {})
    if name not in strats:
        return page("未找到", f"<div class='card'>策略 {name} 不存在</div>"), 404
    s = strats[name]
    off_badge = " <span class='badge-off'>已停用</span>" if s.get("disabled") else ""

    tr = trade_db.get_trades(strategy=name, mode="equal", limit=2000)
    chart = _equity_with_markers(s["label"], s, tr)

    mrows = ""
    for mode, cn in (("equal", "等权"), ("adaptive", "自适应")):
        e = s.get(mode)
        if not e:
            continue
        mrows += (f"<tr><td>{cn}</td><td class='{'green' if e.get('total_return',0)>0 else 'red'}'>{e.get('total_return',0):+.2f}%</td>"
                  f"<td>{e.get('annual_return',0):+.2f}%</td><td>{e.get('sharpe',0):.3f}</td><td>{e.get('max_dd',0):+.1f}%</td>"
                  f"<td>{e.get('volatility',0):.1f}%</td><td>{e.get('win_rate',0):.1f}%</td><td>{e.get('costs',{}).get('total',0):,.0f}</td></tr>")

    pos = s["equal"].get("positions", {})
    pos_rows = "".join(f"<tr><td style='font-family:monospace'>{c}</td><td>{v}</td></tr>"
                       for c, v in pos.items()) or "<tr><td colspan='2'>空仓</td></tr>"

    tr_all = trade_db.get_trades(strategy=name, limit=4000).sort_values("date", ascending=False)
    tr_rows = "".join(
        f"<tr style='background:{'#e8f5e9' if t['action']=='buy' else '#fce4ec'}'>"
        f"<td>{t['date']}</td><td>{t['mode']}</td><td style='font-family:monospace'>{t['code']}</td>"
        f"<td>{'买入' if t['action']=='buy' else '卖出'}</td><td>{int(t['shares'])}</td>"
        f"<td>{t['price']:.2f}</td><td>{t['value']:,.0f}</td>"
        f"<td>{t['commission']+t['stamp_duty']+t['slippage_cost']:,.1f}</td></tr>"
        for _, t in tr_all.head(300).iterrows()) or "<tr><td colspan='8'>无成交</td></tr>"

    body = f"""
<div class='card'><h2>{s['label']}{off_badge} <small style='color:#666'>{s['desc']}</small></h2>{chart}</div>
<div class='card'><h3>指标对比</h3>
<table><tr><th>模式</th><th>累计%</th><th>年化%</th><th>Sharpe</th><th>MaxDD</th><th>波动率</th><th>日胜率</th><th>总成本(元)</th></tr>{mrows}</table></div>
<div class='grid'>
<div class='scard' style='max-width:320px'><h3>当前持仓 (等权, {len(pos)})</h3>
<table><tr><th>代码</th><th>股数</th></tr>{pos_rows}</table></div>
<div class='scard' style='flex:3'><h3>成交记录 (最近300条, 全部见 <a href='/trades?strategy={name}'>筛选</a>)</h3>
<table><tr><th>日期</th><th>模式</th><th>代码</th><th>方向</th><th>股数</th><th>价格</th><th>金额</th><th>成本</th></tr>{tr_rows}</table></div>
</div>"""
    return page(s["label"], body)


# ═══════════════════════════════════════════════════════════════
# TRADES browser — stats cards, group views, round trips, CSV export
# ═══════════════════════════════════════════════════════════════

def _stat_cards(st: dict) -> str:
    if not st:
        return ""
    def card(v, l):
        return f"<div class='scard' style='min-width:110px'><div class='big' style='font-size:18px'>{v}</div><div class='sub'>{l}</div></div>"
    cards = card(st.get("n_trades", 0), "总成交笔数") + card(f"{st.get('turnover',0)/10000:,.0f}万", "总成交额")
    cards += card(f"{st.get('total_cost',0):,.0f}元", "总成本")
    if "win_rate" in st:
        cards += (card(f"{st['win_rate']}%", "往返胜率") + card(f"{st['avg_hold_days']}天", "平均持仓")
                  + card(f"{st['realized_pnl']:,.0f}元", "已实现盈亏"))
    cards += card(st.get("n_open", 0), "当前持仓批次")
    return f"<div class='grid'>{cards}</div>"


@app.route("/trades")
def trades():
    from services import roundtrip as rt

    strategy = request.args.get("strategy", "")
    mode = request.args.get("mode") or "equal"
    date = request.args.get("date", "")
    action = request.args.get("action", "")
    tab = request.args.get("tab", "detail")

    strat_opts = "<option value=''>全部策略</option>" + "".join(
        f"<option value='{k}' {'selected' if k==strategy else ''}>{v['label']}</option>"
        for k, v in STRATEGY_META.items())
    mode_opts = "".join(f"<option value='{m}' {'selected' if m==mode else ''}>{c}</option>"
                        for m, c in (("equal", "等权"), ("adaptive", "自适应")))
    action_opts = "".join(f"<option value='{a}' {'selected' if a==action else ''}>{c}</option>"
                          for a, c in (("", "全部方向"), ("buy", "买入"), ("sell", "卖出")))
    tab_links = " | ".join(
        f"<a href='/trades?tab={t}&strategy={strategy}&mode={mode}' style={'font-weight:bold' if tab==t else ''}>{n}</a>"
        for t, n in [("detail", "逐笔明细"), ("date", "按日汇总"), ("strategy", "按策略汇总"),
                     ("code", "按个股汇总"), ("roundtrip", "往返盈亏"), ("open", "持仓批次")])

    stats_html = _stat_cards(rt.summary_stats(strategy or None, mode))
    content = ""

    if tab == "detail":
        df = trade_db.get_trades(strategy=strategy or None, mode=mode or None,
                                 date=date or None, limit=100000)
        if action:
            df = df[df["action"] == action]
        df = df.sort_values(["date", "id"], ascending=[False, True]).head(500)
        rows = "".join(
            f"<tr style='background:{'#e8f5e9' if t['action']=='buy' else '#fce4ec'}'>"
            f"<td>{t['date']}</td><td>{LABELS.get(t['strategy'], t['strategy'])}</td><td>{t['mode']}</td>"
            f"<td style='font-family:monospace'>{t['code']}</td><td>{'买入' if t['action']=='buy' else '卖出'}</td>"
            f"<td>{int(t['shares'])}</td><td>{t['price']:.2f}</td><td>{t['value']:,.0f}</td>"
            f"<td>{t['commission']+t['stamp_duty']+t['slippage_cost']:,.1f}</td></tr>"
            for _, t in df.iterrows()) or "<tr><td colspan='9'>无记录</td></tr>"
        content = (f"<a href='/trades/csv?strategy={strategy}&mode={mode}'>⬇️ 导出CSV</a>"
                   f"<table><tr><th>日期</th><th>策略</th><th>模式</th><th>代码</th><th>方向</th><th>股数</th><th>价格</th><th>金额</th><th>成本</th></tr>{rows}</table>")

    elif tab == "date":
        g = rt.group_by_date(mode)
        rows = "".join(f"<tr><td>{r['date']}</td><td>{int(r['n'])}</td><td>{r['buy_amt']:,.0f}</td>"
                       f"<td>{r['sell_amt']:,.0f}</td><td>{r['cost']:,.0f}</td></tr>"
                       for _, r in g.iterrows()) or "<tr><td colspan='5'>无</td></tr>"
        content = f"<table><tr><th>日期</th><th>笔数</th><th>买入金额</th><th>卖出金额</th><th>成本</th></tr>{rows}</table>"

    elif tab == "strategy":
        g = rt.group_by_strategy(mode)
        rows = "".join(f"<tr><td>{LABELS.get(r['strategy'], r['strategy'])}</td><td>{int(r['n'])}</td>"
                       f"<td>{int(r['n_codes'])}</td><td>{r['turnover']:,.0f}</td><td>{r['cost']:,.0f}</td></tr>"
                       for _, r in g.iterrows()) or "<tr><td colspan='5'>无</td></tr>"
        content = f"<table><tr><th>策略</th><th>笔数</th><th>涉及股票</th><th>成交额</th><th>成本</th></tr>{rows}</table>"

    elif tab == "code":
        g = rt.group_by_code(strategy or None, mode)
        rows = "".join(f"<tr><td style='font-family:monospace'>{r['code']}</td><td>{int(r['n'])}</td>"
                       f"<td>{int(r['n_strats'])}</td><td>{r['turnover']:,.0f}</td></tr>"
                       for _, r in g.iterrows()) or "<tr><td colspan='4'>无</td></tr>"
        content = f"<table><tr><th>代码</th><th>笔数</th><th>涉及策略数</th><th>成交额</th></tr>{rows}</table>"

    elif tab == "roundtrip":
        closed, _ = rt.compute_roundtrips(strategy or None, mode)
        if closed.empty:
            rows = "<tr><td colspan='9'>暂无已闭合往返</td></tr>"
        else:
            closed = closed.sort_values("sell_date", ascending=False).head(300)
            rows = "".join(
                f"<tr><td>{LABELS.get(r['strategy'], r['strategy'])}</td><td style='font-family:monospace'>{r['code']}</td>"
                f"<td>{r['buy_date']}</td><td>{r['sell_date']}</td><td>{int(r['shares'])}</td>"
                f"<td>{r['hold_days']}天</td>"
                f"<td class='{'green' if r['pnl_pct']>0 else 'red'}'>{r['pnl_pct']:+.2f}%</td>"
                f"<td class='{'green' if r['pnl']>0 else 'red'}'>{r['pnl']:,.0f}</td></tr>"
                for _, r in closed.iterrows())
        content = f"<table><tr><th>策略</th><th>代码</th><th>买入日</th><th>卖出日</th><th>股数</th><th>持仓</th><th>盈亏%</th><th>盈亏(元)</th></tr>{rows}</table>"

    elif tab == "open":
        _, open_pos = rt.compute_roundtrips(strategy or None, mode)
        rows = "".join(
            f"<tr><td>{LABELS.get(r['strategy'], r['strategy'])}</td><td style='font-family:monospace'>{r['code']}</td>"
            f"<td>{int(r['shares'])}</td><td>{r['avg_price']:.2f}</td><td>{r['first_buy']}</td></tr>"
            for _, r in open_pos.iterrows()) or "<tr><td colspan='5'>无持仓批次</td></tr>"
        content = f"<table><tr><th>策略</th><th>代码</th><th>股数</th><th>成本均价</th><th>首次买入</th></tr>{rows}</table>"

    body = f"""
<div class='card'><h3>📝 成交记录中心</h3>
<form class='filters' method='get'>
<input type='hidden' name='tab' value='{tab}'>
<select name='strategy'>{strat_opts}</select>
<select name='mode'>{mode_opts}</select>
<select name='action'>{action_opts}</select>
<input type='date' name='date' value='{date}'>
<button type='submit'>筛选</button></form>
<div style='margin:6px 0;font-size:13px'>{tab_links}</div></div>
{stats_html}
<div class='card'>{content}</div>"""
    return page("成交记录", body, "/trades")


@app.route("/trades/csv")
def trades_csv():
    strategy = request.args.get("strategy") or None
    mode = request.args.get("mode") or None
    df = trade_db.get_trades(strategy=strategy, mode=mode, limit=1000000)
    from flask import Response
    csv = df.to_csv(index=False)
    return Response(csv, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=trades.csv"})


# ═══════════════════════════════════════════════════════════════
# COMPARE + API
# ═══════════════════════════════════════════════════════════════

@app.route("/compare")
def compare():
    selected = request.args.getlist("s") or list(STRATEGY_META)[:4]
    mode = request.args.get("mode", "equal")
    eq = _equity_df(mode if mode in ("equal", "adaptive") else "equal")
    series = {}
    for k in selected:
        if k in eq.columns:
            series[LABELS.get(k, k)] = pd.Series(eq[k].values, index=pd.to_datetime(eq.index))
    chart = _equity_chart(series, f"策略对比 ({'等权' if mode=='equal' else '自适应'})") if series else ""

    checks = "".join(
        f"<label style='font-size:13px'><input type='checkbox' name='s' value='{k}' {'checked' if k in selected else ''}> {v['label']}</label>"
        for k, v in STRATEGY_META.items())
    body = f"""
<div class='card'><h3>策略对比</h3>
<form method='get' class='filters'>{checks}
<select name='mode'><option value='equal' {'selected' if mode=='equal' else ''}>等权</option>
<option value='adaptive' {'selected' if mode=='adaptive' else ''}>自适应</option></select>
<button type='submit'>对比</button></form>{chart}</div>"""
    return page("策略对比", body, "/compare")


@app.route("/api/summary")
def api_summary():
    state = load_state()
    strats = state.get("strategies", {})
    return jsonify({
        "meta": state.get("meta", {}),
        "latest_trade_date": trade_db.latest_date(),
        "strategies": {k: {"label": v["label"], "disabled": v.get("disabled", False),
                           "equal": {m: v["equal"].get(m) for m in
                                     ("total_return", "annual_return", "sharpe", "max_dd", "today_return", "final_equity")},
                           "adaptive": {m: v["adaptive"].get(m) for m in
                                        ("total_return", "annual_return", "sharpe", "max_dd", "today_return", "final_equity")}}
                       for k, v in strats.items() if "equal" in v},
    })


# ═══════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════

def _register_blueprints():
    from web.admin import bp as admin_bp
    from web.assistant import bp as assistant_bp
    from web.lab import bp as lab_bp
    from web.reports import bp as reports_bp
    from web.research import bp as research_bp
    app.register_blueprint(admin_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(lab_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(research_bp)


_register_blueprints()


def _get_port() -> int:
    import os
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DASH_PORT") and "=" in line:
                return int(line.split("=", 1)[1].strip().strip('"').strip("'"))
    return int(os.environ.get("DASH_PORT", "8600"))


if __name__ == "__main__":
    from services.scheduler import start_scheduler
    start_scheduler()
    app.run(host="127.0.0.1", port=_get_port(), debug=False)
