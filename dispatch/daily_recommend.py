"""
Daily Stock Recommendation Email — runs all strategies, finds consensus picks,
highlights top performers, dynamic risk assessment from recent performance.

Schedule: 15:30 daily via Windows Task Scheduler
"""

import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))

import logging, time, hashlib
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__); logger.setLevel(logging.INFO)

import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "cache"; CACHE.mkdir(exist_ok=True)

TOP_STRATEGY_NAMES = ["alpha158_lgb_wf", "alpha158_xgb_wf", "macd_signal", "ma_cross"]

LABELS = {
    "ma_cross": ("MA Cross", "★10.4k", 0.61), "rsi_reversal": ("RSI Rev.", "★10.4k", -0.66),
    "bollinger_breakout": ("Bollinger", "★10.4k", 0.49), "macd_signal": ("MACD", "★10.4k", 0.85),
    "pairs_trading": ("Pairs Tr.", "★10.4k", -0.06), "risk_parity": ("Risk Par.", "★4.8k", 0.24),
    "alpha158_lgb_wf": ("LGB WF", "★46.6k", 1.41), "alpha158_xgb_wf": ("XGB WF", "★46.6k", 1.38),
    "lstm_rank": ("LSTM", "★46.6k", -0.36), "transformer_rank": ("TF", "★46.6k", 0.0),
}

DESC = {
    "ma_cross": "趋势跟踪, 信号稀少质量高", "rsi_reversal": "均值回归, 牛市逆势",
    "bollinger_breakout": "波动率突破, 换手极高", "macd_signal": "趋势+动量, 三重确认",
    "pairs_trading": "统计套利, 需做空能力", "risk_parity": "低波动, 回撤控制最优",
    "alpha158_lgb_wf": "Walk-Forward, 每季重训, 排名第1", "alpha158_xgb_wf": "Walk-Forward, XGBoost, 排名第2",
    "lstm_rank": "深度排序, 训练中", "transformer_rank": "Transformer, 待训练",
}


def is_trading_day():
    try:
        import akshare as ak; today = datetime.now().strftime("%Y%m%d")
        return today in set(ak.tool_trade_date_hist_sina()["trade_date"].astype(str))
    except Exception:
        return datetime.now().weekday() < 5


def load_data(pool_name):
    from config.settings import config as cfg
    from data.fetcher_akshare import fetch_index_members
    codes = fetch_index_members(cfg.universe.all_pools[pool_name][0])
    f = CACHE / f"full_{pool_name}_{hashlib.md5(''.join(sorted(codes)).encode()).hexdigest()[:8]}.parquet"
    if not f.exists(): return pd.DataFrame()
    df = pd.read_parquet(f)
    if is_trading_day():
        latest = pd.to_datetime(df["date"]).max().strftime("%Y-%m-%d")
        if latest < datetime.now().strftime("%Y-%m-%d"):
            try:
                import akshare as ak
                frames = []
                for sym in codes[:50]:
                    try:
                        r = ak.stock_zh_a_daily(symbol=f"sh{sym}" if sym.startswith("6") else f"sz{sym}", start_date=datetime.now().strftime("%Y%m%d"), end_date=datetime.now().strftime("%Y%m%d"), adjust="qfq")
                        if r is not None and not r.empty: frames.append(r.assign(code=sym))
                    except Exception: pass
                if frames:
                    new = pd.concat(frames, ignore_index=True); new["date"] = pd.to_datetime(new["date"])
                    from data.processor import clean_ohlcv, compute_returns
                    new = clean_ohlcv(new); new = compute_returns(new)
                    df = pd.concat([df, new], ignore_index=True); df.to_parquet(f, index=False)
            except Exception as e: logger.warning("Data fetch skipped: %s", e)
    return df


def generate_signals():
    from run_backtest import (signals_ma_cross, signals_rsi, signals_bollinger, signals_macd, signals_pairs_trading, signals_risk_parity, compute_factors, prepare_ml_xy, train_lgb, train_xgb)
    all_results = {}
    for pool in ["csi500"]:
        df = load_data(pool)
        if df.empty: continue
        pivot = df.pivot(index="date", columns="code", values="close")
        latest_str = pivot.index[-1].strftime("%Y-%m-%d")
        funcs = {"ma_cross":signals_ma_cross,"rsi_reversal":signals_rsi,"bollinger_breakout":signals_bollinger,"macd_signal":signals_macd,"pairs_trading":signals_pairs_trading,"risk_parity":signals_risk_parity}
        for sn, sf in funcs.items():
            sigs = sf(pivot)
            all_results[sn] = {"codes": [s["code"] for s in sigs.get(latest_str, []) if s["action"] == "buy"], "pool": pool, "latest_date": latest_str}
        try:
            factors = compute_factors(pivot)
            if not factors.empty and len(factors.columns)>2:
                X, y = prepare_ml_xy(factors, pivot)
                if not X.empty and len(X)>100:
                    mask = X.index.get_level_values("date") < pivot.index[-1]
                    if mask.sum()>50:
                        x_tr = X.droplevel("date").loc[mask]; y_tr = y.loc[mask]
                        if pivot.index[-1] in factors.index.get_level_values("date"):
                            tf = factors.loc[pivot.index[-1]]
                            if not tf.empty:
                                p_lgb = train_lgb(x_tr, y_tr, tf)
                                all_results["alpha158_lgb_wf"] = {"codes": p_lgb.nlargest(max(1,int(len(p_lgb)*0.1))).index.tolist(), "pool": pool, "latest_date": latest_str}
                                p_xgb = train_xgb(x_tr, y_tr, tf)
                                all_results["alpha158_xgb_wf"] = {"codes": p_xgb.nlargest(max(1,int(len(p_xgb)*0.1))).index.tolist(), "pool": pool, "latest_date": latest_str}
        except Exception as e: logger.warning("ML skip: %s", e)
    consensus, top_cons = {}, {}
    for sn, r in all_results.items():
        for c in r.get("codes",[]): consensus[c]=consensus.get(c,0)+1
        if sn in TOP_STRATEGY_NAMES:
            for c in r.get("codes",[]): top_cons[c]=top_cons.get(c,0)+1
    return all_results, consensus, top_cons


def build_email(all_results, consensus, top_cons):
    today = datetime.now().strftime("%Y-%m-%d"); now = datetime.now().strftime("%H:%M")
    latest_date = next((r.get("latest_date", today) for r in all_results.values() if r.get("latest_date")), today)

    # Dynamic risk from performance state (using return_2m)
    from daily_performance import load_state as load_perf, LABELS as PF_LABELS
    ps = load_perf()
    strat_risk = {}
    for k, st in ps.get("strategies",{}).items():
        sn = k.split("_",1)[-1]
        r2m = st.get("return_2m", 0)
        if r2m > 5:
            strat_risk[sn] = f"🟢强势(近2月 +{r2m:.1f}%)"
        elif r2m > 0:
            strat_risk[sn] = f"🟡稳健(近2月 +{r2m:.1f}%)"
        elif r2m > -5:
            strat_risk[sn] = f"🟠回调(近2月 {r2m:.1f}%)"
        else:
            strat_risk[sn] = f"🔴弱势(近2月 {r2m:.1f}%)"
    # Fill missing strategies from backtest Sharpe
    for sn, (lb,star,sh) in PF_LABELS.items():
        if sn not in strat_risk:
            if sh>=1.0: r=f"🟢低风险(回测Sharpe {sh:.2f})"
            elif sh>0.3: r=f"🟡中风险(回测Sharpe {sh:.2f})"
            elif sh>0: r=f"🔴高风险(回测Sharpe {sh:.2f})"
            else: r=f"⚠️警告(回测Sharpe {sh:.2f})"
            strat_risk[sn]=r

    # Consensus rows
    ct = [(c,n) for c,n in top_cons.items() if n>=2]; ct.sort(key=lambda x:-x[1])
    crs = "".join(f"<tr><td style='font-weight:bold;font-family:monospace'>{c}</td><td>{n}/4</td><td>{consensus.get(c,0)}/8</td><td>{'🟢' if n>=3 else ('🟡' if n>=2 else '🔴')}</td></tr>" for c,n in ct[:15])
    if not crs: crs = "<tr><td colspan='4' style='color:#999'>今日无共识推荐</td></tr>"

    # Strategy rows with dynamic risk
    srs = ""
    for sn in sorted(all_results,key=lambda k:LABELS.get(k,("","",0))[2],reverse=True):
        r=all_results[sn]; codes=r.get("codes",[])
        if not codes: continue
        lb,star,sh=LABELS.get(sn,(sn,"",0));         dsk = strat_risk.get(sn, "⚪"); desc = DESC.get(sn, ""); cl = ", ".join(codes[:15])
        srs += f"<tr><td style='font-weight:bold'>{lb} {star}</td><td style='font-size:11px'>{dsk}</td><td style='font-family:monospace;font-size:11px;text-align:left;max-width:400px;word-break:break-all'>{cl}</td><td style='font-size:10px;color:#666;text-align:left'>{desc}</td></tr>"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{font-family:'Segoe UI',sans-serif;margin:20px;background:#f0f2f5}}
h1{{color:#1a1a2e;border-bottom:3px solid #4472C4;padding-bottom:8px}}
h2{{color:#333;margin:16px 0 8px 0}}
.card{{background:#fff;border-radius:10px;padding:16px;margin:12px 0;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
table{{border-collapse:collapse;width:100%}}
th{{background:#4472C4;color:#fff;padding:10px 8px;text-align:center;font-size:12px}}
td{{padding:8px;text-align:center;border-bottom:1px solid #e8e8e8;font-size:12px}}
.footer{{color:#999;font-size:11px;margin-top:24px;border-top:1px solid #eee;padding-top:12px}}
</style></head><body>
<h1>📊 量化策略每日推荐</h1>
<p style='color:#666'>日期: {today} | 生成: {now} | 数据日: {latest_date}</p>
<div class="card"><h2>📈 市场概览</h2><p style='color:#666'>基于最新数据日期 {latest_date} 的{len(all_results)}个策略信号。风险评估来源于近2个月真实表现，非静态回测数据。</p></div>
<div class="card"><h2>⭐ 共识推荐 (Top 4: LGB WF + XGB WF + MACD + MA Cross)</h2>
<p style='color:#666;font-size:12px'>被 ≥2 个顶级策略共同选中</p>
<table><tr><th>代码</th><th>Top4</th><th>全8</th><th>风险</th></tr>{crs}</table></div>
<div class="card"><h2>🏆 各策略今日推荐 (动态风险评估)</h2>
<p style='color:#666;font-size:12px'>风险基于近2月绩效: 🟢强势(收益>5%) 🟡稳健(>0) 🟠回调(-5~0) 🔴弱势(<-5%)</p>
<table><tr><th>策略</th><th>风险</th><th>推荐</th><th>说明</th></tr>{srs}</table></div>
<div class="card"><h2>⚠️ 风险提示</h2><p style='color:#666;font-size:12px;line-height:1.8'>
⛔ 量化模型自动生成，不构成投资建议。历史表现不代表未来收益。动态风险评估基于近2个月真实交易记录。</p></div>
<p class="footer">Generated by quant-strategy-verification | {today} {now}</p></body></html>"""


def save_mail(html, prefix):
    t = datetime.now(); month_dir = ROOT / "mail" / t.strftime("%Y%m"); month_dir.mkdir(parents=True, exist_ok=True)
    fn = month_dir / f"{prefix}_{t.strftime('%Y%m%d')}.html"
    # Remove same-day duplicates
    for old in month_dir.glob(f"{prefix}_{t.strftime('%Y%m%d')}*.html"):
        if old != fn: old.unlink()
    fn.write_text(html, encoding="utf-8")
    return fn


def main():
    if not is_trading_day(): logger.info("Skip: not trading day"); return
    logger.info("Generating recommendation...")
    ar, cn, tc = generate_signals()
    html = build_email(ar, cn, tc)
    from execution.notify import send_daily_report
    ok = send_daily_report(f"[量化推荐] {datetime.now().strftime('%Y-%m-%d')} 股票推荐", html)
    logger.info("Email: %s", "OK" if ok else "FAIL")
    p = save_mail(html, "recommend"); logger.info("Saved: %s", p)


if __name__ == "__main__":
    main()
