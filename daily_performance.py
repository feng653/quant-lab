"""
Daily Portfolio Performance — each strategy independently traded, tracked, reported.

10 strategies × 1,000,000 initial cash each × independently executed.
Daily chart comparison + risk metrics.
"""

import sys

sys.path.insert(0, ".")

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(exist_ok=True)
STATE_FILE = STATE_DIR / "strategy_state.json"
INITIAL_CASH = 1_000_000.0
COMMISSION = 0.001
SLIPPAGE = 0.001
STAMP_DUTY = 0.001
MAX_POSITIONS = 20
REBALANCE_DAYS = 30

STRATEGY_NAMES = [
    "ma_cross", "rsi_reversal", "bollinger_breakout", "macd_signal",
    "pairs_trading", "risk_parity",
]

STRATEGY_LABELS = {
    "ma_cross": ("MA Cross", "★10.4k", 0.61),
    "rsi_reversal": ("RSI Rev.", "★10.4k", -0.66),
    "bollinger_breakout": ("Bollinger", "★10.4k", 0.49),
    "macd_signal": ("MACD", "★10.4k", 0.85),
    "pairs_trading": ("Pairs Tr.", "★10.4k", -0.06),
    "risk_parity": ("Risk Par.", "★4.8k", 0.24),
}


def is_trading_day():
    try:
        import akshare as ak
        today = datetime.now().strftime("%Y%m%d")
        cal = ak.tool_trade_date_hist_sina()
        return today in set(cal["trade_date"].astype(str))
    except Exception:
        return datetime.now().weekday() < 5


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"strategies": {}, "updated": None}


def save_state(state):
    state["updated"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def init_strategy_state(state, pool, sname):
    """Initialize a strategy's state if not present."""
    key = f"{pool}_{sname}"
    if key not in state["strategies"]:
        state["strategies"][key] = {
            "cash": INITIAL_CASH,
            "positions": {},
            "dates": [],
            "equity": [],
            "returns": [],
            "total_return": 0.0,
            "annual_return": 0.0,
            "sharpe": 0.0,
            "max_dd": 0.0,
        }
    return state["strategies"][key]


def load_full_data(pool_name):
    """Load cached full data for a pool."""
    import hashlib
    from config.settings import config as cfg
    from data.akshare_fetcher import fetch_index_members

    codes = fetch_index_members(cfg.universe.all_pools[pool_name][0])
    code_hash = hashlib.md5("".join(sorted(codes)).encode()).hexdigest()[:8]
    cache_file = ROOT / "data" / "cache" / f"full_{pool_name}_{code_hash}.parquet"
    if not cache_file.exists():
        logger.error("No cache for %s", pool_name)
        return None
    return pd.read_parquet(cache_file)


def simulate_strategy(pivot, state, sname, sfunc, pool_name):
    """Simulate one strategy's independent trading from its last updated date."""
    key = f"{pool_name}_{sname}"
    st = init_strategy_state(state, pool_name, sname)

    all_dates = sorted(pivot.index)
    bt_dates = [d for d in all_dates if d >= pd.Timestamp("2024-01-01")]

    # Determine the start date for simulation
    if st["dates"]:
        last_date = pd.Timestamp(st["dates"][-1])
        sim_dates = [d for d in bt_dates if d > last_date][:1]  # only one new day at a time
    else:
        sim_dates = bt_dates
        last_date = bt_dates[0] - pd.Timedelta(days=1)

    if not sim_dates:
        return

    # Convert positions from dict format
    positions = {}
    for code_str, pos_dict in st["positions"].items():
        positions[code_str] = float(pos_dict)

    signals_all = sfunc(pivot)
    cash = st["cash"]

    daily_rets = []
    new_dates = []
    new_equity = []

    for sim_idx, dt in enumerate(sim_dates):
        d_str = dt.strftime("%Y-%m-%d")
        if dt not in pivot.index:
            continue

        prices = pivot.loc[dt].dropna()

        # Rebalance monthly
        day_idx = all_dates.index(dt)
        is_rb = day_idx % REBALANCE_DAYS == 0

        # Get signals from previous day
        prev_idx = all_dates.index(dt) - 1 if all_dates.index(dt) > 0 else 0
        prev_dt = all_dates[max(0, prev_idx)]
        prev_sigs = signals_all.get(prev_dt.strftime("%Y-%m-%d"), [])

        buy_sigs = [s for s in prev_sigs if s["action"] == "buy"]
        sell_sigs = [s for s in prev_sigs if s["action"] == "sell"]

        # Sell on sell signals
        for sig in sell_sigs:
            code = sig["code"]
            if code in positions and code in prices.index:
                sp = prices[code] * (1 - SLIPPAGE)
                cash += positions[code] * sp * (1 - COMMISSION - STAMP_DUTY)
                del positions[code]

        # Sell all on rebalance
        if is_rb:
            for code in list(positions.keys()):
                if code in prices.index:
                    sp = prices[code] * (1 - SLIPPAGE)
                    cash += positions[code] * sp * (1 - COMMISSION - STAMP_DUTY)
                del positions[code]

        # Buy on rebalance with buy signals
        if is_rb and buy_sigs:
            valid = [s for s in buy_sigs if s["code"] in prices.index and s["code"] not in positions]
            if valid:
                w = 1.0 / len(valid)
                for sig in valid:
                    code = sig["code"]
                    bp = prices[code] * (1 + SLIPPAGE)
                    shares = int(cash * w // bp // 100) * 100
                    if shares >= 100:
                        cost = shares * bp * (1 + COMMISSION)
                        if cost <= cash:
                            cash -= cost
                            positions[code] = shares

        # MTM
        mkt_value = cash + sum(positions[c] * (prices[c] if c in prices.index else 0) for c in positions)
        new_dates.append(d_str)
        new_equity.append(round(mkt_value, 2))

        if new_equity and len(new_equity) >= 2:
            daily_rets.append(float(new_equity[-1] / new_equity[-2] - 1))
        else:
            daily_rets.append(0.0)

    # Update state
    if new_dates:
        st["dates"].extend(new_dates)
        st["equity"].extend(new_equity)
        st["returns"].extend(daily_rets)
        st["cash"] = round(cash, 2)
        st["positions"] = {str(k): int(v) for k, v in positions.items()}

        # Compute cumulative metrics
        if len(st["equity"]) > 1:
            eq = pd.Series(st["equity"])
            rets_series = eq.pct_change().dropna()
            if len(rets_series) > 0:
                tr = eq.iloc[-1] / INITIAL_CASH - 1
                n_years = max(0.01, len(st["dates"]) / 252)
                ann_ret = (1 + tr) ** (1 / n_years) - 1
                ann_vol = float(rets_series.std() * np.sqrt(252))
                sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0
                peak = eq.cummax()
                if peak.iloc[-1] > 0:
                    mdd = float(((eq - peak) / peak).min())
                else:
                    mdd = 0.0
                st["total_return"] = round(tr * 100, 2)
                st["annual_return"] = round(ann_ret * 100, 2)
                st["sharpe"] = round(sharpe, 3)
                st["max_dd"] = round(mdd * 100, 2)


def build_html_email(state, equity_data, charts_html):
    """Build comprehensive HTML performance report."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%H:%M")

    # Per-strategy performance rows
    perf_rows = ""
    sorted_keys = sorted(state["strategies"].keys(), key=lambda k: state["strategies"][k].get("sharpe", -999), reverse=True)

    for key in sorted_keys:
        st = state["strategies"][key]
        _, sname = key.split("_", 1) if "_" in key else ("", key)
        label, stars, _ = STRATEGY_LABELS.get(sname, (sname, "", 0))
        ann = st.get("annual_return", 0)
        shp = st.get("sharpe", 0)
        dd = st.get("max_dd", 0)
        eq_arr = st.get("equity", [])
        today_ret = (eq_arr[-1] / eq_arr[-2] - 1) * 100 if len(eq_arr) >= 2 else 0
        total_ret = st.get("total_return", 0)
        positions_count = len(st.get("positions", {}))

        risk_emoji = "🟢" if shp > 0.8 else ("🟡" if shp > 0.3 else ("🔴" if shp > 0 else "⚠️"))
        ret_class = "green" if today_ret > 0 else "red"

        perf_rows += f"""<tr>
            <td>{risk_emoji} {label}</td><td>{stars}</td>
            <td class='{ret_class}'>{today_ret:+.2f}%</td>
            <td>{total_ret:+.1f}%</td><td>{ann:+.1f}%</td>
            <td>{shp:.3f}</td><td>{dd:+.1f}%</td>
            <td>{positions_count}</td></tr>"""

    # Portfolio metrics
    total_assets = sum(st.get("equity", [INITIAL_CASH])[-1] if st.get("equity") else INITIAL_CASH for st in state["strategies"].values())
    total_initial = len(state["strategies"]) * INITIAL_CASH
    combined_return = (total_assets / total_initial - 1) * 100 if total_initial > 0 else 0

    # Win rate
    all_rets = []
    for st in state["strategies"].values():
        all_rets.extend(st.get("returns", [])[-120:])
    win_rate = (sum(1 for r in all_rets if r > 0) / max(len(all_rets), 1)) * 100 if all_rets else 0

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{{font-family:'Segoe UI',sans-serif;margin:20px;background:#f0f2f5}}
h1{{color:#1a1a2e;border-bottom:3px solid #4472C4;padding-bottom:8px}}
h2{{color:#333;margin:16px 0 8px 0}}
.card{{background:#fff;border-radius:10px;padding:16px;margin:12px 0;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
table{{border-collapse:collapse;width:100%}}
th{{background:#4472C4;color:#fff;padding:10px 8px;text-align:center;font-size:12px}}
td{{padding:8px;text-align:center;border-bottom:1px solid #e8e8e8;font-size:12px}}
.green{{color:#2e7d32;font-weight:bold}}.red{{color:#c62828;font-weight:bold}}
.metrics{{display:flex;gap:16px;flex-wrap:wrap;margin:8px 0}}
.metric-card{{flex:1;min-width:120px;background:#f8f9fa;border-radius:8px;padding:12px;text-align:center}}
.metric-value{{font-size:22px;font-weight:bold;color:#1a1a2e}}
.metric-label{{font-size:11px;color:#666;margin-top:4px}}
.footer{{color:#999;font-size:11px;margin-top:24px;border-top:1px solid #eee;padding-top:12px}}
</style></head><body>
<h1>📊 量化组合日报 — 各策略独立表现</h1>
<p style='color:#666'>日期: {today_str} | 生成时间: {now_str} | 每个策略独立1,000,000元初始资金</p>

<div class="card"><h2>💰 综合概览</h2>
<div class="metrics">
    <div class="metric-card"><div class="metric-value">{total_assets:,.0f}</div><div class="metric-label">10策略总资产</div></div>
    <div class="metric-card"><div class="metric-value" style="color:{'#2e7d32' if combined_return>=0 else '#c62828'}">{combined_return:+.2f}%</div><div class="metric-label">组合加权收益</div></div>
    <div class="metric-card"><div class="metric-value">{len(state['strategies'])}</div><div class="metric-label">独立策略数</div></div>
    <div class="metric-card"><div class="metric-value">{win_rate:.1f}%</div><div class="metric-label">日胜率(近120日)</div></div>
</div></div>

<div class="card"><h2>📈 各策略独立表现</h2>
<table><tr><th>策略</th><th>来源</th><th>今日%</th><th>累计%</th><th>年化%</th><th>Sharpe</th><th>MaxDD</th><th>持仓</th></tr>
{perf_rows}</table></div>

<div class="card"><h2>📉 净值走势图 (近60日)</h2>{charts_html}</div>

<div class="card"><h2>📝 文字总结</h2>
<p style='color:#444;font-size:13px;line-height:1.8'>
今日{len(sorted_keys)}个策略独立运行。{'整体表现稳健' if combined_return >=0 else '部分策略出现回撤'}。
其中{'、'.join([STRATEGY_LABELS.get(k.split('_',1)[-1],(k,'',''))[0] for k in sorted_keys[:3] if state['strategies'][k].get('sharpe',0)>0.5])} 等策略表现突出。
每策略1,000,000独立账户、独立交易、独立统计，不受其他策略干扰。
</p></div>

<div class="card"><h2>⚠️ 风险提示</h2><p style='color:#666;font-size:11px;line-height:1.6'>
⛔ 本报告由量化模型自动生成，不构成投资建议。历史表现不代表未来收益。各策略独立运行，回测结果基于2024-2026年数据。投资有风险，入市需谨慎。
</p></div>
<p class="footer">Generated by quant-strategy-verification | {today_str} {now_str}</p>
</body></html>"""


def main():
    if not is_trading_day():
        logger.info("Not a trading day, skipping.")
        return

    state = load_state()
    pool = "csi500"

    logger.info("Loading data for %s...", pool)
    df = load_full_data(pool)
    if df is None:
        logger.error("No data available.")
        return

    pivot = df.pivot(index="date", columns="code", values="close")
    logger.info("Pivot: %s, latest: %s", pivot.shape, pivot.index[-1].date())

    from run_complete import (signals_ma_cross, signals_rsi, signals_bollinger,
                               signals_macd, signals_pairs_trading, signals_risk_parity)

    signal_funcs = {
        "ma_cross": signals_ma_cross, "rsi_reversal": signals_rsi,
        "bollinger_breakout": signals_bollinger, "macd_signal": signals_macd,
        "pairs_trading": signals_pairs_trading, "risk_parity": signals_risk_parity,
    }

    logger.info("Simulating 6 strategies independently...")
    for sname, sfunc in signal_funcs.items():
        simulate_strategy(pivot, state, sname, sfunc, pool)

    save_state(state)

    # Build equity data for charts
    equity_data = {}
    for key in state["strategies"]:
        st = state["strategies"][key]
        if st.get("dates") and st.get("equity"):
            sname = key.split("_", 1)[-1] if "_" in key else key
            label, _, _ = STRATEGY_LABELS.get(sname, (sname, "", 0))
            eq = pd.Series(st["equity"][-60:], index=pd.to_datetime(st["dates"][-60:]))
            equity_data[label] = eq

    from execution.charts import equity_curve_chart, drawdown_chart
    charts_html = ""
    if equity_data:
        charts_html += equity_curve_chart(equity_data, "各策略独立净值对比 (近60交易日)")
        charts_html += drawdown_chart(equity_data, "各策略回撤曲线 (近60交易日)")

    html_body = build_html_email(state, equity_data, charts_html)

    from execution.notify import send_daily_report
    today_str = datetime.now().strftime("%Y-%m-%d")
    success = send_daily_report(f"[量化日报] {today_str} 策略独立表现", html_body)
    if success:
        logger.info("Performance email sent.")
    else:
        logger.error("Failed to send.")

    (ROOT / "reports" / "daily_performance.html").write_text(html_body, encoding="utf-8")
    logger.info("Report saved.")


if __name__ == "__main__":
    main()
