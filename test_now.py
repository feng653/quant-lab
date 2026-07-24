"""Force-run both daily scripts with today's data, save to mail/ folder."""

import sys
sys.path.insert(0, ".")

import logging
logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIL = ROOT / "mail"
MAIL.mkdir(exist_ok=True)

# ── Run Recommend ──
print("=" * 60)
print("1/2: Generating Recommendation Email...")
print("=" * 60)

from daily_recommend import generate_consensus_signals, build_recommend_email

all_results, consensus, top_consensus = generate_consensus_signals()
html_rec = build_recommend_email(all_results, consensus, top_consensus)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
path_rec = MAIL / f"recommend_{ts}.html"
path_rec.write_text(html_rec, encoding="utf-8")
print(f"  Saved: {path_rec} ({len(html_rec)} chars)")
print(f"  Strategies: {[(k, len(v['codes'])) for k,v in sorted(all_results.items()) if v.get('codes')]}")
if top_consensus:
    tc = dict(sorted(top_consensus.items(), key=lambda x: -x[1])[:8])
    print(f"  Top Consensus: {tc}")

# ── Run Performance ──
print("\n" + "=" * 60)
print("2/2: Generating Performance Email...")
print("=" * 60)

from daily_performance import load_state, load_full_data, simulate_strategy, save_state, build_html_email

state = load_state()
pool = "csi500"
df = load_full_data(pool)
pivot = df.pivot(index="date", columns="code", values="close")
print(f"  Data: {pivot.shape}, latest: {pivot.index[-1].date()}")

from run_complete import (signals_ma_cross, signals_rsi, signals_bollinger,
                           signals_macd, signals_pairs_trading, signals_risk_parity)

funcs = {
    "ma_cross": signals_ma_cross, "rsi_reversal": signals_rsi,
    "bollinger_breakout": signals_bollinger, "macd_signal": signals_macd,
    "pairs_trading": signals_pairs_trading, "risk_parity": signals_risk_parity,
}

for sname, sfunc in funcs.items():
    simulate_strategy(pivot, state, sname, sfunc, pool)

save_state(state)

# Build charts
equity_data = {}
STRATEGY_LABELS = {
    "ma_cross": ("MA Cross", "★10.4k", 0.61),
    "rsi_reversal": ("RSI Rev.", "★10.4k", -0.66),
    "bollinger_breakout": ("Bollinger", "★10.4k", 0.49),
    "macd_signal": ("MACD", "★10.4k", 0.85),
    "pairs_trading": ("Pairs Tr.", "★10.4k", -0.06),
    "risk_parity": ("Risk Par.", "★4.8k", 0.24),
}

import pandas as pd
for key in state["strategies"]:
    st = state["strategies"][key]
    if st.get("dates") and st.get("equity") and len(st["equity"]) >= 2:
        sname = key.split("_", 1)[-1] if "_" in key else key
        label, _, _ = STRATEGY_LABELS.get(sname, (sname, "", 0))
        eq = pd.Series(st["equity"][-60:], index=pd.to_datetime(st["dates"][-60:]))
        equity_data[label] = eq

from execution.charts import equity_curve_chart, drawdown_chart
charts_html = ""
if equity_data:
    charts_html += equity_curve_chart(equity_data, "各策略独立净值对比 (近60交易日)")
    charts_html += drawdown_chart(equity_data, "各策略回撤曲线 (近60交易日)")

html_perf = build_html_email(state, equity_data, charts_html)

ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
path_perf = MAIL / f"performance_{ts2}.html"
path_perf.write_text(html_perf, encoding="utf-8")
print(f"  Saved: {path_perf} ({len(html_perf)} chars)")

# Print summary
print("\n" + "=" * 60)
print("All Strategies Performance Summary:")
print("=" * 60)
print(f"  {'Strategy':<20s} {'Ann%':>7s} {'Sharpe':>8s} {'MaxDD':>8s} {'Equity':>12s} {'Pos':>5s}")
print("  " + "-" * 60)
for key in sorted(state["strategies"].keys(), key=lambda k: state["strategies"][k].get("sharpe", -999), reverse=True):
    st = state["strategies"][key]
    sname = key.split("_", 1)[-1]
    label, _, _ = STRATEGY_LABELS.get(sname, (sname, "", 0))
    ann = st.get("annual_return", 0)
    shp = st.get("sharpe", 0)
    dd = st.get("max_dd", 0)
    eq = st.get("equity", [0])
    pos = len(st.get("positions", {}))
    print(f"  {label:<20s} {ann:>6.1f}% {shp:>8.3f} {dd:>7.1f}% {eq[-1]:>10,.0f} {pos:>5}")

# Save combined state report
state_report = {
    "generated": datetime.now().isoformat(),
    "strategies": {}
}
for key, st in state["strategies"].items():
    sname = key.split("_", 1)[-1]
    label, stars, _ = STRATEGY_LABELS.get(sname, (sname, "", 0))
    state_report["strategies"][label] = {
        "name": label, "stars": stars,
        "annual_return": st.get("annual_return", 0),
        "total_return": st.get("total_return", 0),
        "sharpe": st.get("sharpe", 0),
        "max_dd": st.get("max_dd", 0),
        "equity_latest": st.get("equity", [0])[-1] if st.get("equity") else 0,
        "positions_count": len(st.get("positions", {})),
        "trading_days": len(st.get("dates", [])),
    }

(MAIL / f"state_{ts}.json").write_text(json.dumps(state_report, ensure_ascii=False, indent=2))

print(f"\nFiles saved to: {MAIL}")
print("Done.")
