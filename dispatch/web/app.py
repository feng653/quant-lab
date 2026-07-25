"""
Web dashboard — browse every simulated operation and strategy curve any time.

  python dispatch/web/app.py   →   http://localhost:8600

Port: 8600 by default (8080 conflicts with qBittorrent). Override with
DASH_PORT in .env or environment, or `--port N` CLI argument.

Pages:
  /                     overview: market, strategy cards, comparison chart, latest trades
  /strategy/<name>      one strategy: dual-mode equity + drawdown, metrics, positions, trades
  /trades               full trade records, filter by date/strategy/mode/action
  /compare              multi-strategy normalized equity comparison
  /api/summary          JSON summary (for external tools)

Read-only over dispatch/state/trades.db + strategy_state.json. No heavy compute.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from flask import Flask, jsonify, request

from charts.generator import fig_to_base64
from services import trade_db
from services.signal_service import STRATEGY_META
from services.sim_runner import load_state
from services.market_service import classify_market

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

app = Flask(__name__)

LABELS = {k: v["label"] for k, v in STRATEGY_META.items()}
COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
          "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

BASE_CSS = """
body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;margin:0;background:#f0f2f5}
nav{background:#1a1a2e;color:#fff;padding:12px 24px;display:flex;gap:20px;align-items:center}
nav a{color:#cfd8dc;text-decoration:none;font-size:14px}nav a:hover{color:#fff}
nav .brand{font-weight:bold;font-size:16px;color:#ffd54f}
.wrap{max-width:1200px;margin:20px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:16px;margin:12px 0;box-shadow:0 2px 8px rgba(0,0,0,0.08)}
table{border-collapse:collapse;width:100%}
th{background:#4472C4;color:#fff;padding:8px 6px;font-size:12px}
td{padding:6px;text-align:center;border-bottom:1px solid #eee;font-size:12px}
.green{color:#2e7d32;font-weight:bold}.red{color:#c62828;font-weight:bold}
.grid{display:flex;flex-wrap:wrap;gap:12px}
.scard{flex:1;min-width:200px;background:#fff;border-radius:10px;padding:14px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}
.scard h3{margin:0 0 6px 0;font-size:15px}
.scard .big{font-size:22px;font-weight:bold}
.scard .sub{color:#666;font-size:11px;line-height:1.7}
form.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:8px 0}
select,input{padding:5px 8px;border:1px solid #ccc;border-radius:6px;font-size:13px}
button{padding:6px 16px;background:#4472C4;color:#fff;border:none;border-radius:6px;cursor:pointer}
img{max-width:100%;border-radius:6px}
"""


def nav() -> str:
    return ("<nav><span class='brand'>📊 quant-lab 模拟盘</span>"
            "<a href='/'>总览</a><a href='/trades'>成交记录</a><a href='/compare'>策略对比</a>"
            "<a href='/api/summary'>API</a></nav>")


def page(title: str, body: str) -> str:
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title><style>{BASE_CSS}</style></head><body>{nav()}<div class='wrap'>{body}</div></body></html>"


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


# ────────────────────────── overview ──────────────────────────

@app.route("/")
def overview():
    state = load_state()
    strats = state.get("strategies", {})
    meta = state.get("meta", {})
    market = classify_market()

    cards = ""
    keys = sorted(strats, key=lambda k: strats[k]["equal"]["sharpe"], reverse=True)
    for k in keys:
        e = strats[k]["equal"]
        ret = e["total_return"]
        cls = "green" if ret > 0 else "red"
        cards += (f"<div class='scard'><h3><a href='/strategy/{k}'>{strats[k]['label']}</a></h3>"
                  f"<div class='big {cls}'>{ret:+.2f}%</div>"
                  f"<div class='sub'>Sharpe {e['sharpe']:.3f} | MaxDD {e['max_dd']:+.1f}%<br>"
                  f"今日 {e['today_return']:+.2f}% | 持仓 {len(e['positions'])}<br>"
                  f"自适应 {strats[k]['adaptive']['total_return']:+.2f}%</div></div>")

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

    bench_ret = strats[keys[0]]["equal"]["bench_ret"] if keys else 0
    body = f"""
<div class='card'><b>模拟起始:</b> {meta.get('simulation_start','-')} &nbsp;|&nbsp;
<b>数据截止:</b> {latest} &nbsp;|&nbsp; <b>市场:</b> <span style='color:{market['color']}'>{market['label']}</span>
(中证500近20日 {market['ret_20d']:+.2f}% | 同期基准 {bench_ret:+.2f}%) &nbsp;|&nbsp;
<b>更新:</b> {meta.get('updated','-')[:16]}</div>
<div class='grid'>{cards}</div>
<div class='card'>{chart}</div>
<div class='card'><h3>最近交易日成交 ({latest}, 等权模式) — <a href='/trades'>全部记录</a></h3>
<table><tr><th>日期</th><th>策略</th><th>代码</th><th>方向</th><th>股数</th><th>价格</th><th>金额</th></tr>{tr_rows}</table></div>"""
    return page("总览", body)


# ────────────────────────── single strategy ──────────────────────────

@app.route("/strategy/<name>")
def strategy_detail(name: str):
    state = load_state()
    strats = state.get("strategies", {})
    if name not in strats:
        return page("未找到", f"<div class='card'>策略 {name} 不存在</div>"), 404
    s = strats[name]

    series = {}
    for mode, cn in (("equal", "等权"), ("adaptive", "自适应")):
        e = s[mode]
        series[cn] = pd.Series(e["equity"], index=pd.to_datetime(e["dates"]))
    chart = _equity_chart(series, f"{s['label']} 净值 (双模式)", normalize=True)

    mrows = ""
    for mode, cn in (("equal", "等权"), ("adaptive", "自适应")):
        e = s[mode]
        mrows += (f"<tr><td>{cn}</td><td class='{'green' if e['total_return']>0 else 'red'}'>{e['total_return']:+.2f}%</td>"
                  f"<td>{e['annual_return']:+.2f}%</td><td>{e['sharpe']:.3f}</td><td>{e['max_dd']:+.1f}%</td>"
                  f"<td>{e['volatility']:.1f}%</td><td>{e['win_rate']:.1f}%</td><td>{e['costs']['total']:,.0f}</td></tr>")

    pos = s["equal"]["positions"]
    pos_rows = "".join(f"<tr><td style='font-family:monospace'>{c}</td><td>{v}</td></tr>"
                       for c, v in pos.items()) or "<tr><td colspan='2'>空仓</td></tr>"

    tr = trade_db.get_trades(strategy=name, limit=2000)
    tr = tr.sort_values("date", ascending=False)
    tr_rows = "".join(
        f"<tr style='background:{'#e8f5e9' if t['action']=='buy' else '#fce4ec'}'>"
        f"<td>{t['date']}</td><td>{t['mode']}</td><td style='font-family:monospace'>{t['code']}</td>"
        f"<td>{'买入' if t['action']=='buy' else '卖出'}</td><td>{int(t['shares'])}</td>"
        f"<td>{t['price']:.2f}</td><td>{t['value']:,.0f}</td>"
        f"<td>{t['commission']+t['stamp_duty']+t['slippage_cost']:,.1f}</td></tr>"
        for _, t in tr.head(300).iterrows()) or "<tr><td colspan='8'>无成交</td></tr>"

    body = f"""
<div class='card'><h2>{s['label']} <small style='color:#666'>{s['desc']}</small></h2>{chart}</div>
<div class='card'><h3>指标对比</h3>
<table><tr><th>模式</th><th>累计%</th><th>年化%</th><th>Sharpe</th><th>MaxDD</th><th>波动率</th><th>日胜率</th><th>总成本(元)</th></tr>{mrows}</table></div>
<div class='grid'>
<div class='scard' style='max-width:320px'><h3>当前持仓 (等权, {len(pos)})</h3>
<table><tr><th>代码</th><th>股数</th></tr>{pos_rows}</table></div>
<div class='scard' style='flex:3'><h3>成交记录 (最近300条, 全部见 <a href='/trades?strategy={name}'>筛选</a>)</h3>
<table><tr><th>日期</th><th>模式</th><th>代码</th><th>方向</th><th>股数</th><th>价格</th><th>金额</th><th>成本</th></tr>{tr_rows}</table></div>
</div>"""
    return page(s["label"], body)


# ────────────────────────── trades browser ──────────────────────────

@app.route("/trades")
def trades():
    strategy = request.args.get("strategy", "")
    mode = request.args.get("mode", "")
    date = request.args.get("date", "")
    action = request.args.get("action", "")

    df = trade_db.get_trades(strategy=strategy or None, mode=mode or None,
                             date=date or None, limit=100000)
    if action:
        df = df[df["action"] == action]
    df = df.sort_values(["date", "id"], ascending=[False, True]).head(500)

    strat_opts = "<option value=''>全部策略</option>" + "".join(
        f"<option value='{k}' {'selected' if k==strategy else ''}>{v['label']}</option>"
        for k, v in STRATEGY_META.items())
    mode_opts = "".join(f"<option value='{m}' {'selected' if m==mode else ''}>{c}</option>"
                        for m, c in (("", "全部模式"), ("equal", "等权"), ("adaptive", "自适应")))
    action_opts = "".join(f"<option value='{a}' {'selected' if a==action else ''}>{c}</option>"
                          for a, c in (("", "全部方向"), ("buy", "买入"), ("sell", "卖出")))

    rows = "".join(
        f"<tr style='background:{'#e8f5e9' if t['action']=='buy' else '#fce4ec'}'>"
        f"<td>{t['date']}</td><td>{LABELS.get(t['strategy'], t['strategy'])}</td><td>{t['mode']}</td>"
        f"<td style='font-family:monospace'>{t['code']}</td><td>{'买入' if t['action']=='buy' else '卖出'}</td>"
        f"<td>{int(t['shares'])}</td><td>{t['price']:.2f}</td><td>{t['value']:,.0f}</td>"
        f"<td>{t['commission']+t['stamp_duty']+t['slippage_cost']:,.1f}</td></tr>"
        for _, t in df.iterrows()) or "<tr><td colspan='9'>无记录</td></tr>"

    total = trade_db.get_trades(limit=1000000)
    body = f"""
<div class='card'><h3>成交记录浏览 (共 {len(total)} 条, 显示最近 500 条筛选结果)</h3>
<form class='filters' method='get'>
<select name='strategy'>{strat_opts}</select>
<select name='mode'>{mode_opts}</select>
<select name='action'>{action_opts}</select>
<input type='date' name='date' value='{date}'>
<button type='submit'>筛选</button>
</form>
<table><tr><th>日期</th><th>策略</th><th>模式</th><th>代码</th><th>方向</th><th>股数</th><th>价格</th><th>金额</th><th>成本</th></tr>
{rows}</table></div>"""
    return page("成交记录", body)


# ────────────────────────── compare ──────────────────────────

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
    return page("策略对比", body)


# ────────────────────────── API ──────────────────────────

@app.route("/api/summary")
def api_summary():
    state = load_state()
    strats = state.get("strategies", {})
    return jsonify({
        "meta": state.get("meta", {}),
        "latest_trade_date": trade_db.latest_date(),
        "strategies": {k: {"label": v["label"],
                           "equal": {m: v["equal"][m] for m in
                                     ("total_return", "annual_return", "sharpe", "max_dd", "today_return", "final_equity")},
                           "adaptive": {m: v["adaptive"][m] for m in
                                        ("total_return", "annual_return", "sharpe", "max_dd", "today_return", "final_equity")}}
                       for k, v in strats.items()},
    })


def _get_port() -> int:
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DASH_PORT") and "=" in line:
                return int(line.split("=", 1)[1].strip().strip('"').strip("'"))
    import os
    return int(os.environ.get("DASH_PORT", "8600"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=_get_port(), debug=False)
