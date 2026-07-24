"""
Daily Stock Recommendation Email — runs all strategies, finds consensus picks,
highlights top performers, flags high-risk signals.

Schedule: 15:30 daily via Windows Task Scheduler
"""

import sys

sys.path.insert(0, ".")

import logging
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

import numpy as np
import pandas as pd

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "cache"
CACHE.mkdir(exist_ok=True)

# Strategy star ratings and risk flags
STRATEGY_META = {
    "ma_cross": ("MA Cross", "★10.4k", 0.61, "yellow", "趋势跟踪, 信号稀少质量高"),
    "macd_signal": ("MACD", "★10.4k", 0.85, "yellow", "趋势+动量, 三重确认"),
    "bollinger_breakout": ("Bollinger", "★10.4k", 0.49, "red", "波动率突破, 换手极高"),
    "rsi_reversal": ("RSI Rev.", "★10.4k", -0.66, "warn", "均值回归, 牛市逆势"),
    "pairs_trading": ("Pairs", "★10.4k", -0.06, "warn", "统计套利, 需做空能力"),
    "risk_parity": ("Risk Par.", "★4.8k", 0.24, "green", "低波动, 回撤控制最优"),
}

ML_META = {
    "alpha158_lgb_wf": ("LGB WF", "★46.6k", 1.41, "green", "Walk-Forward, 每季重训, 排名第1"),
    "alpha158_xgb_wf": ("XGB WF", "★46.6k", 1.38, "green", "Walk-Forward, XGBoost, 排名第2"),
}

TOP_STRATEGY_NAMES = ["alpha158_lgb_wf", "alpha158_xgb_wf", "macd_signal", "ma_cross"]

ALL_META = {**ML_META, **STRATEGY_META}

RISK_LEVELS = {"green": "🟢低风险", "yellow": "🟡中风险", "red": "🔴高风险", "warn": "⚠️逆势"}


def is_trading_day():
    try:
        import akshare as ak
        today = datetime.now().strftime("%Y%m%d")
        cal = ak.tool_trade_date_hist_sina()
        return today in set(cal["trade_date"].astype(str))
    except Exception:
        dt = datetime.now()
        return dt.weekday() < 5


def load_or_fetch_today_data(pool_name):
    """Load cached full data. Only try to download new data on trading days if cache is stale."""
    from config.settings import config as cfg
    from data.akshare_fetcher import fetch_index_members

    codes = fetch_index_members(cfg.universe.all_pools[pool_name][0])
    code_hash = hashlib.md5("".join(sorted(codes)).encode()).hexdigest()[:8]
    cache_file = CACHE / f"full_{pool_name}_{code_hash}.parquet"

    if not cache_file.exists():
        logger.error("No cache for %s. Run run_complete.py first.", pool_name)
        return pd.DataFrame()

    df = pd.read_parquet(cache_file)
    latest = pd.to_datetime(df["date"]).max().strftime("%Y-%m-%d")

    if not is_trading_day():
        return df  # skip download on non-trading days

    if latest >= datetime.now().strftime("%Y-%m-%d"):
        return df  # already up to date

    # Try to download today's data with timeout
    logger.info("Fetching today's data (%s)...", datetime.now().strftime("%Y-%m-%d"))
    try:
        import akshare as ak
        frames = []
        for sym in codes[:50]:  # only top 50 to check availability
            try:
                r = ak.stock_zh_a_daily(symbol=f"sh{sym}" if sym.startswith("6") else f"sz{sym}",
                                          start_date=datetime.now().strftime("%Y%m%d"),
                                          end_date=datetime.now().strftime("%Y%m%d"), adjust="qfq")
                if r is not None and not r.empty:
                    frames.append(r.assign(code=sym))
            except Exception:
                pass
        if frames:
            new = pd.concat(frames, ignore_index=True)
            new["date"] = pd.to_datetime(new["date"])
            from data.processor import clean_ohlcv, compute_returns
            new = clean_ohlcv(new)
            new = compute_returns(new)
            df = pd.concat([df, new], ignore_index=True)
            df.to_parquet(cache_file, index=False)
    except Exception as e:
        logger.warning("Data fetch failed (API may not be ready): %s", e)
    return df


def generate_consensus_signals():
    """Generate signals from all strategies for the latest available trading date."""
    from run_complete import (signals_ma_cross, signals_rsi, signals_bollinger,
                               signals_macd, signals_pairs_trading, signals_risk_parity,
                               compute_factors, prepare_ml_xy, train_lgb, train_xgb)

    all_results: dict[str, dict] = {}

    for pool in ["csi500"]:
        df = load_or_fetch_today_data(pool)
        if df.empty:
            continue
        pivot = df.pivot(index="date", columns="code", values="close")
        latest_date = pivot.index[-1]  # last available trading date
        latest_str = latest_date.strftime("%Y-%m-%d")

        classic_funcs = {
            "ma_cross": signals_ma_cross, "rsi_reversal": signals_rsi,
            "bollinger_breakout": signals_bollinger, "macd_signal": signals_macd,
            "pairs_trading": signals_pairs_trading, "risk_parity": signals_risk_parity,
        }
        for sname, sfunc in classic_funcs.items():
            sigs = sfunc(pivot)
            today_sigs = [s for s in sigs.get(latest_str, []) if s["action"] == "buy"]
            all_results[sname] = {"codes": [s["code"] for s in today_sigs], "pool": pool}

        # ML walk-forward: train on all data before latest, predict for latest
        try:
            factors = compute_factors(pivot)
            if not factors.empty and len(factors.columns) > 2:
                X, y = prepare_ml_xy(factors, pivot)
                if not X.empty and len(X) > 100:
                    mask_train = X.index.get_level_values("date") < latest_date
                    x_tr = X.droplevel("date").loc[mask_train]
                    y_tr = y.loc[mask_train]
                    # Get today's factors
                    if latest_date in factors.index.get_level_values("date"):
                        today_f = factors.loc[latest_date]
                        if not today_f.empty:
                            # Train + predict with LGB
                            p_lgb = train_lgb(x_tr, y_tr, today_f)
                            top_n = max(1, int(len(p_lgb) * 0.1))
                            all_results["alpha158_lgb_wf"] = {"codes": p_lgb.nlargest(top_n).index.tolist(), "pool": pool}
                            # Train + predict with XGB
                            p_xgb = train_xgb(x_tr, y_tr, today_f)
                            all_results["alpha158_xgb_wf"] = {"codes": p_xgb.nlargest(top_n).index.tolist(), "pool": pool}
        except Exception as e:
            logger.warning("ML predict failed: %s", e)

    # Compute consensus
    consensus = {}
    for r in all_results.values():
        for code in r.get("codes", []):
            consensus[code] = consensus.get(code, 0) + 1

    top_consensus = {}
    for sname in TOP_STRATEGY_NAMES:
        if sname in all_results:
            for code in all_results[sname].get("codes", []):
                top_consensus[code] = top_consensus.get(code, 0) + 1

    return all_results, consensus, top_consensus


def build_recommend_email(all_results, consensus, top_consensus):
    """Build comprehensive HTML recommendation email."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%H:%M")

    # Market summary
    market_html = "<p style='color:#666'>市场数据加载中... (如AKShare不可用则跳过)</p>"

    # Consensus picks (stocks recommended by 2+ top strategies)
    consensus_top = [(c, n) for c, n in top_consensus.items() if n >= 2]
    consensus_top.sort(key=lambda x: -x[1])
    consensus_rows = ""
    for code, count in consensus_top[:15]:
        strategy_count = consensus.get(code, 0)
        risk = "🟢" if count >= 3 else ("🟡" if count >= 2 else "🔴")
        consensus_rows += f"<tr><td style='font-weight:bold;font-family:monospace'>{code}</td><td>{count}/4</td><td>{strategy_count}/8</td><td>{risk}</td></tr>"

    if not consensus_rows:
        consensus_rows = "<tr><td colspan='4' style='color:#999'>今日无共识推荐</td></tr>"

    # Individual strategy recommendations
    strategy_sections = ""
    for sname in sorted(all_results.keys(), key=lambda k: ALL_META.get(k, ("", "", 0, "", ""))[2], reverse=True):
        r = all_results[sname]
        codes = r.get("codes", [])
        if not codes:
            continue
        display_name, stars, sharpe, risk, desc = ALL_META.get(sname, (sname, "", 0, "green", ""))
        risk_emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴", "warn": "⚠️"}.get(risk, "⚪")
        code_list = ", ".join(codes[:15])
        strategy_sections += f"""<tr>
            <td style='font-weight:bold'>{display_name} {stars}</td>
            <td>{risk_emoji} {RISK_LEVELS.get(risk,'')}</td>
            <td style='font-family:monospace;font-size:11px;text-align:left;max-width:400px;word-break:break-all'>{code_list}</td>
            <td style='font-size:10px;color:#666;text-align:left'>{desc}</td></tr>"""

    body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{{font-family:'Segoe UI',sans-serif;margin:20px;background:#f0f2f5}}
h1{{color:#1a1a2e;border-bottom:3px solid #4472C4;padding-bottom:8px}}
h2{{color:#333;margin:16px 0 8px 0}}
.card{{background:#fff;border-radius:10px;padding:16px;margin:12px 0;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
table{{border-collapse:collapse;width:100%}}
th{{background:#4472C4;color:#fff;padding:10px 8px;text-align:center;font-size:12px}}
td{{padding:8px;text-align:center;border-bottom:1px solid #e8e8e8;font-size:12px}}
.green{{color:#2e7d32;font-weight:bold}}.red{{color:#c62828;font-weight:bold}}
.yellow{{color:#e65100;font-weight:bold}}
.warn{{color:#6a1b9a;font-weight:bold}}
.footer{{color:#999;font-size:11px;margin-top:24px;border-top:1px solid #eee;padding-top:12px}}
</style></head><body>
<h1>📊 量化策略每日推荐</h1>
<p style='color:#666'>日期: {today_str} | 生成时间: {now_str}</p>

<div class="card"><h2>📈 市场概览</h2>{market_html}</div>

<div class="card"><h2>⭐ 共识推荐 (Top 4 策略: LGB WF + XGB WF + MACD + MA Cross)</h2>
<p style='color:#666;font-size:12px'>被 ≥2 个顶级策略共同选中的股票，共识度越高可靠性越强</p>
<table><tr><th>股票代码</th><th>Top4共识</th><th>全8策略</th><th>风险</th></tr>{consensus_rows}</table></div>

<div class="card"><h2>🏆 各策略今日推荐</h2>
<p style='color:#666;font-size:12px'>按历史Sharpe降序排列。风险标志基于全数据回测的Sharpe和最大回撤。</p>
<table><tr><th>策略</th><th>风险标志</th><th>今日推荐股票</th><th>策略说明</th></tr>{strategy_sections}</table></div>

<div class="card"><h2>⚠️ 风险提示</h2>
<p style='color:#666;font-size:12px;line-height:1.8'>
• <b>LGB WF / XGB WF</b>: Walk-Forward ML策略，基于过去5年数据训练，每季度重新训练。Sharpe 1.4+，回测表现最优。<br>
• <b>MACD / MA Cross</b>: 经典趋势跟踪策略，在2024-2026牛市环境中表现优异。震荡市可能回撤。<br>
• <b>Bollinger</b>: 信号密度极高(31K+/年)，实际交易成本会严重侵蚀收益。<br>
• <b>RSI / Pairs Trading</b>: 历史Sharpe为负，在牛市中属于逆势策略，仅供研究参考。<br>
• <b>Risk Parity</b>: 低波动资产配置策略，最大回撤仅10.5%，适合防御性配置。<br><br>
⛔ <b>免责声明</b>: 本报告由量化模型自动生成，不构成投资建议。历史回测表现不代表未来收益。投资有风险，入市需谨慎。
</p></div>

<p class="footer">Generated by quant-strategy-verification | {today_str} {now_str}</p>
</body></html>"""
    return body


def main():
    if not is_trading_day():
        logger.info("Not a trading day, skipping.")
        return

    logger.info("Generating daily recommendation...")
    all_results, consensus, top_consensus = generate_consensus_signals()

    html_body = build_recommend_email(all_results, consensus, top_consensus)

    from execution.notify import send_daily_report
    today_str = datetime.now().strftime("%Y-%m-%d")
    success = send_daily_report(f"[量化推荐] {today_str} 每日股票推荐", html_body)
    if success:
        logger.info("Recommendation email sent.")
    else:
        logger.error("Failed to send recommendation email.")

    # Save local copy
    (ROOT / "reports" / "daily_recommend.html").write_text(html_body, encoding="utf-8")


if __name__ == "__main__":
    main()
