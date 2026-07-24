"""
Daily Recommendation Email (rebuilt) — every strategy's operations, fully detailed.

For each of the 10 strategies: current simulated holdings, today's buy signals
with suggested position sizing (adaptive volatility-based), and explicit sell
signals. Plus market regime, cross-strategy consensus picks, and a performance
strip so recommendations can be weighed against live simulated track records.

Schedule: 15:30 daily via Task Scheduler (or via run_daily.py).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ROOT = Path(__file__).resolve().parent

TARGET_VOL = 0.15
MIN_EXPOSURE, MAX_EXPOSURE = 0.3, 1.0


def _latest_prices(pivot: pd.DataFrame) -> pd.Series:
    return pivot.iloc[-1].dropna()


def _current_exposure(pivot: pd.DataFrame) -> float:
    """Adaptive exposure from pool 20d volatility (same rule as sim_engine)."""
    rets = pivot.pct_change(fill_method=None)
    pool_ret = rets.mean(axis=1)
    v = float(pool_ret.rolling(20).std().iloc[-1] * np.sqrt(252))
    if not np.isfinite(v) or v <= 0:
        return 1.0
    return float(np.clip(TARGET_VOL / v, MIN_EXPOSURE, MAX_EXPOSURE))


def _stock_vol(pivot: pd.DataFrame, code: str) -> float:
    r = pivot[code].pct_change(fill_method=None).dropna()
    if len(r) < 20:
        return 0.2
    return float(r.iloc[-20:].std() * np.sqrt(252))


def build_recommend_html(ctx: dict) -> str:
    state = ctx["state"]; market = ctx["market"]; pivot = ctx["pivot"]
    signals = ctx["signals"]; latest = ctx["latest_date"]
    today = datetime.now().strftime("%Y-%m-%d"); now = datetime.now().strftime("%H:%M")

    prices = _latest_prices(pivot)
    exposure = _current_exposure(pivot)

    keys = sorted(state["strategies"], key=lambda k: state["strategies"][k]["equal"]["sharpe"], reverse=True)
    labels = {k: state["strategies"][k]["label"] for k in keys}

    # per-strategy signal snapshot at latest date
    strat_buys: dict[str, list[str]] = {}
    strat_sells: dict[str, list[str]] = {}
    for k in keys:
        sigs = signals.get(k, {}).get(latest, [])
        strat_buys[k] = [s["code"] for s in sigs if s["action"] == "buy" and s["code"] in prices.index]
        strat_sells[k] = [s["code"] for s in sigs if s["action"] == "sell" and s["code"] in prices.index]

    # ── consensus (buy signals from >=2 strategies) ──
    votes: dict[str, list[str]] = {}
    for k in keys:
        for c in strat_buys[k]:
            votes.setdefault(c, []).append(labels[k])
    consensus = sorted(votes.items(), key=lambda x: -len(x[1]))
    cons_rows = ""
    for c, who in consensus[:20]:
        if len(who) < 2:
            continue
        px = prices.get(c, 0)
        cons_rows += (f"<tr><td style='font-weight:bold;font-family:monospace'>{c}</td>"
                      f"<td>{len(who)}</td><td style='font-size:11px;text-align:left'>{', '.join(who)}</td>"
                      f"<td>{px:.2f}</td><td>{'🟢强共识' if len(who)>=3 else '🟡共识'}</td></tr>")
    if not cons_rows:
        cons_rows = "<tr><td colspan='5' style='color:#999'>今日无跨策略共识买入标的</td></tr>"

    # ── per-strategy operation detail ──
    strat_blocks = ""
    for k in keys:
        e = state["strategies"][k]["equal"]; ad = state["strategies"][k]["adaptive"]
        lb = labels[k]
        buys, sells = strat_buys[k], strat_sells[k]
        holdings = e["positions"]

        # suggested sizing: strategy equity × adaptive exposure / N buys
        equity = ad["final_equity"]
        buy_rows = ""
        if buys:
            per_amt = equity * exposure / len(buys)
            for c in buys[:20]:
                px = float(prices[c])
                sh = int(per_amt // px // 100) * 100
                vol = _stock_vol(pivot, c)
                buy_rows += (f"<tr><td style='font-family:monospace'>{c}</td><td>{px:.2f}</td>"
                             f"<td>{sh if sh>=100 else '—(资金不足)'}</td><td>{sh*px:,.0f}</td>"
                             f"<td>{vol*100:.0f}%</td></tr>")
        else:
            buy_rows = "<tr><td colspan='5' style='color:#999'>无新买入信号</td></tr>"

        sell_txt = ", ".join(f"<span style='font-family:monospace'>{c}</span>" for c in sells[:15]) or "<span style='color:#999'>无</span>"
        hold_txt = ", ".join(f"<span style='font-family:monospace'>{c}</span>×{v}" for c, v in list(holdings.items())[:12]) or "<span style='color:#999'>空仓</span>"
        if len(holdings) > 12:
            hold_txt += f" ... 等{len(holdings)}只"

        em = "🟢" if e["sharpe"] > 0.5 else ("🟡" if e["sharpe"] > 0 else "🔴")
        perf = (f"{em} 累计 <b class='{'green' if e['total_return']>0 else 'red'}'>{e['total_return']:+.2f}%</b> "
                f"(基准 {e['bench_ret']:+.2f}%) | Sharpe {e['sharpe']:.3f} | MaxDD {e['max_dd']:+.1f}%")
        strat_blocks += f"""
<div style='border:1px solid #e0e0e0;border-radius:8px;margin:10px 0;overflow:hidden'>
<div style='background:#f5f7fa;padding:10px 14px;font-size:13px'><b>{lb}</b>
<span style='color:#666;font-size:11px;margin-left:10px'>{state['strategies'][k]['desc']}</span>
<span style='float:right;font-size:11px'>{perf}</span></div>
<div style='padding:10px 14px'>
<div style='font-size:12px;margin:4px 0'><b>📥 买入建议</b> (共{len(buys)}只, 自适应仓位系数 {exposure:.2f}x, 单只约 {equity*exposure/max(len(buys),1):,.0f} 元):</div>
<table style='margin:4px 0'><tr><th>代码</th><th>最新价</th><th>建议股数</th><th>建议金额(元)</th><th>个股波动</th></tr>{buy_rows}</table>
<div style='font-size:12px;margin:6px 0'><b>📤 卖出信号</b>: {sell_txt}</div>
<div style='font-size:12px;margin:6px 0'><b>💼 当前模拟持仓</b> ({len(holdings)}只): {hold_txt}</div>
</div></div>"""

    # ── performance strip ──
    strip_rows = "".join(
        f"<tr><td style='text-align:left'>{labels[k]}</td>"
        f"<td class='{'green' if state['strategies'][k]['equal']['total_return']>0 else 'red'}'>{state['strategies'][k]['equal']['total_return']:+.2f}%</td>"
        f"<td>{state['strategies'][k]['equal']['sharpe']:.3f}</td>"
        f"<td class='{'green' if state['strategies'][k]['adaptive']['total_return']>0 else 'red'}'>{state['strategies'][k]['adaptive']['total_return']:+.2f}%</td>"
        f"<td>{len(strat_buys[k])}</td><td>{len(strat_sells[k])}</td><td>{len(state['strategies'][k]['equal']['positions'])}</td></tr>"
        for k in keys)

    regime_strats = ", ".join(labels[s] for s in market.get("strategies", []) if s in labels)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{font-family:'Segoe UI','Microsoft YaHei',sans-serif;margin:20px;background:#f0f2f5}}
h1{{color:#1a1a2e;border-bottom:3px solid #4472C4;padding-bottom:8px}}
h2{{color:#333;margin:16px 0 8px 0}}
.card{{background:#fff;border-radius:10px;padding:16px;margin:12px 0;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
table{{border-collapse:collapse;width:100%}}
th{{background:#4472C4;color:#fff;padding:8px 6px;text-align:center;font-size:11px}}
td{{padding:6px;text-align:center;border-bottom:1px solid #e8e8e8;font-size:12px}}
.green{{color:#2e7d32;font-weight:bold}}.red{{color:#c62828;font-weight:bold}}
.hdr{{background:#1a1a2e;color:#fff;border-radius:10px;padding:14px 18px;margin:12px 0;font-size:13px;line-height:1.9}}
.hdr b{{color:#ffd54f}}
.footer{{color:#999;font-size:11px;margin-top:24px;border-top:1px solid #eee;padding-top:12px}}
</style></head><body>
<h1>📈 量化策略每日操作建议 — 10策略全览</h1>
<div class="hdr">
数据日期: <b>{latest}</b> (收盘后生成 {now}) | 建议执行时间: <b>下一交易日</b><br>
模拟起始: <b>{ctx['sim_start']}</b> | 已运行 <b>{ctx['n_days']}</b> 个交易日 | 市场环境: <b>{market['label']}</b>
(中证500 近20日 {market['ret_20d']:+.2f}% | 波动率 {market['vol_20d']}%)<br>
当前自适应仓位系数: <b>{exposure:.2f}x</b> — {"⚠️ 高波动环境, 建议降低总仓位" if exposure < 0.8 else "正常仓位区间"} | 当前环境适配策略: <b>{regime_strats or '-'}</b>
</div>

<div class="card"><h2>⭐ 跨策略共识推荐 (≥2策略同时买入)</h2>
<table><tr><th>代码</th><th>策略数</th><th>推荐策略</th><th>最新价</th><th>共识强度</th></tr>{cons_rows}</table></div>

<div class="card"><h2>📋 策略速览 (按模拟Sharpe排序)</h2>
<table><tr><th>策略</th><th>等权累计%</th><th>Sharpe</th><th>自适应累计%</th><th>今日买入信号</th><th>今日卖出信号</th><th>当前持仓</th></tr>
{strip_rows}</table></div>

<div class="card"><h2>🎯 各策略操作明细 (建议股数按自适应波动率仓位计算)</h2>
<p style='color:#666;font-size:12px'>建议金额 = 策略模拟净值 × 仓位系数 {exposure:.2f} ÷ 买入信号数。不足100股标记为资金不足。
策略表现数据来自同一模拟系统 (起始 {ctx['sim_start']}), 与每日表现邮件同源。</p>
{strat_blocks}</div>

<div class="card"><h2>⚠️ 风险提示</h2><p style='color:#666;font-size:11px;line-height:1.8'>
⛔ 量化模型自动生成, 全部为模拟信号, 不构成投资建议。建议股数基于模拟账户净值计算, 仅供参考。
历史表现不代表未来收益。市场有风险, 投资需谨慎。</p></div>
<p class="footer">Generated by quant-lab | dispatch/daily_recommend.py | {today} {now}</p></body></html>"""


def save_mail(html: str, prefix: str = "recommend") -> Path:
    t = datetime.now()
    md = ROOT / "mail" / t.strftime("%Y%m")
    md.mkdir(parents=True, exist_ok=True)
    fn = md / f"{prefix}_{t.strftime('%Y%m%d')}.html"
    for old in md.glob(f"{prefix}_{t.strftime('%Y%m%d')}*.html"):
        if old != fn:
            old.unlink()
    fn.write_text(html, encoding="utf-8")
    return fn


def main():
    from services.data_service import is_trading_day
    if not is_trading_day():
        logger.info("Skip: not trading day")
        return
    from services.sim_runner import run_simulation
    ctx = run_simulation()
    html = build_recommend_html(ctx)
    from notify.email_qq import send_daily_report
    ok = send_daily_report(f"[量化推荐] {datetime.now().strftime('%Y-%m-%d')} 10策略操作建议 ({ctx['market']['label']})", html)
    logger.info("Email: %s", "OK" if ok else "FAIL")
    p = save_mail(html)
    logger.info("Saved: %s", p)


if __name__ == "__main__":
    main()
