"""Force-run both daily scripts, save to mail/YYYYMM/, send emails."""
import sys; sys.path.insert(0, ".")
import logging; logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__); logger.setLevel(logging.INFO)

from datetime import datetime
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent

def save_mail(html, prefix):
    t = datetime.now(); md = ROOT / "mail" / t.strftime("%Y%m"); md.mkdir(parents=True, exist_ok=True)
    fn = md / f"{prefix}_{t.strftime('%Y%m%d')}.html"
    for old in md.glob(f"{prefix}_{t.strftime('%Y%m%d')}*.html"):
        if old != fn: old.unlink()
    fn.write_text(html, encoding="utf-8")
    return fn

# ── 1. Recommend ──
print("=" * 60); print("1/2: Recommendation Email"); print("=" * 60)
from daily_recommend import generate_signals, build_email
ar, cn, tc = generate_signals()
html_rec = build_email(ar, cn, tc)
p = save_mail(html_rec, "recommend")
print(f"  Saved: {p} ({len(html_rec)} chars)")

from notify.email_qq import send_daily_report
ok1 = send_daily_report(f"[量化推荐] {datetime.now().strftime('%Y-%m-%d')} 股票推荐", html_rec)
print(f"  Email: {'OK' if ok1 else 'FAIL'}")

# ── 2. Performance ──
print("\n" + "=" * 60); print("2/2: Performance Email (10 strategies)"); print("=" * 60)
from daily_performance import load_state, load_data, simulate, merge_ml, save_state, build_html, LABELS
state = load_state(); pool = "csi500"
df = load_data(pool)
pivot = df.pivot(index="date", columns="code", values="close")
print(f"  Data: {pivot.shape}, latest: {pivot.index[-1].date()}")

from run_backtest import signals_ma_cross, signals_rsi, signals_bollinger, signals_macd, signals_pairs_trading, signals_risk_parity
funcs = {"ma_cross":signals_ma_cross,"rsi_reversal":signals_rsi,"bollinger_breakout":signals_bollinger,"macd_signal":signals_macd,"pairs_trading":signals_pairs_trading,"risk_parity":signals_risk_parity}
for sn, sf in funcs.items(): simulate(pivot, state, sn, sf, pool)
merge_ml(state, pool); save_state(state)

eq_data = {}
for k in state["strategies"]:
    st = state["strategies"][k]; sn = k.split("_",1)[-1]
    lb, _, _ = LABELS.get(sn, (sn, "", 0))
    eq_arr = st.get("equity", []); dt_arr = st.get("dates", [])
    if eq_arr and dt_arr and len(eq_arr) >= 2 and len(dt_arr) >= 2:
        try:
            n = min(60, min(len(eq_arr), len(dt_arr)))
            eq_data[lb] = pd.Series(eq_arr[-n:], index=pd.to_datetime(dt_arr[-n:]))
        except Exception:
            pass

from charts.generator import strategy_grid_charts
charts = strategy_grid_charts(eq_data) if eq_data else ""
html_perf = build_html(state, charts)
p2 = save_mail(html_perf, "performance")
print(f"  Saved: {p2} ({len(html_perf)} chars)")

ok2 = send_daily_report(f"[量化日报] {datetime.now().strftime('%Y-%m-%d')} 10策略独立表现", html_perf)
print(f"  Email: {'OK' if ok2 else 'FAIL'}")

# Summary
print("\n" + "=" * 60); print("All Strategies:"); print("=" * 60)
print(f"  {'Strategy':<15s} {'Ann%':>7s} {'Sharpe':>8s} {'MaxDD':>8s} {'Equity':>12s} {'Pos':>5s}")
print("  " + "-" * 57)
for k in sorted(state["strategies"], key=lambda k: state["strategies"][k].get("sharpe", -999), reverse=True):
    st = state["strategies"][k]; sn = k.split("_",1)[-1]
    lb, _, _ = LABELS.get(sn, (sn, "", 0))
    eq = st.get("equity", [0])
    print(f"  {lb:<15s} {st.get('annual_return',0):>6.1f}% {st.get('sharpe',0):>8.3f} {st.get('max_dd',0):>7.1f}% {eq[-1]:>10,.0f} {len(st.get('positions',{})):>5}")
