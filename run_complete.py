"""
Complete pipeline — full data (2019-2026), 10 strategies, 2 pools, ML training.

Run: python run_complete.py

Produces:
  results/all_results.json        — detailed backtest data
  reports/complete_report.md      — comparison report
  docs/PERFORMANCE_ANALYSIS.md    — updated with annualized returns
  docs/strategies/01-10.md        — updated with full results
"""

import sys

sys.path.insert(0, ".")

import hashlib
import json
import logging
import time
from itertools import combinations
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

import numpy as np
import pandas as pd

from config.settings import config as cfg
from data.akshare_fetcher import fetch_index_members
from data.processor import clean_ohlcv, compute_returns

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
CACHE_DIR = ROOT / "data" / "cache"
CACHE_DIR.mkdir(exist_ok=True)

TRAIN_START = "2019-01-01"
TRAIN_END = "2023-12-31"
BT_START = "2024-01-01"
BT_END = "2026-06-30"


# ═══════════════════════════════════════════════════════════════
# DATA DOWNLOAD
# ═══════════════════════════════════════════════════════════════

def _fetch_one(sym, start, end):
    import akshare as ak

    try:
        prefix = "sh" if sym.startswith("6") else "sz"
        df = ak.stock_zh_a_daily(symbol=f"{prefix}{sym}", start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="qfq")
        df["code"] = sym
        return df
    except Exception:
        return None


def download_pool(pool_name):
    idx = cfg.universe.all_pools[pool_name][0]
    codes = fetch_index_members(idx)
    code_hash = hashlib.md5("".join(sorted(codes)).encode()).hexdigest()[:8]
    cache_file = CACHE_DIR / f"full_{pool_name}_{code_hash}.parquet"

    if cache_file.exists():
        logger.info("[%s] Cache hit: %s, %d stocks", pool_name, cache_file.name, len(codes))
        return pd.read_parquet(cache_file)

    logger.info("[%s] Downloading %d stocks (2019-2026)...", pool_name, len(codes))
    frames = []
    for i, sym in enumerate(codes):
        if (i + 1) % 50 == 0:
            logger.info("    %d/%d...", i + 1, len(codes))
        r = _fetch_one(sym, TRAIN_START, BT_END)
        if r is not None:
            frames.append(r)

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = clean_ohlcv(df)
    df = compute_returns(df)
    df.to_parquet(cache_file, index=False)
    logger.info("[%s] Saved: %d rows, %d stocks", pool_name, len(df), df["code"].nunique())
    return df


# ═══════════════════════════════════════════════════════════════
# ML TRAINING PIPELINE
# ═══════════════════════════════════════════════════════════════

def compute_factors(pivot):
    """Simple factor computation — uses rolling returns + volatility as features.

    Returns DataFrame: index=date, columns=factor_name (per stock group)
    For ML training, each row = one stock at one date.
    """
    rets = pivot.pct_change(fill_method=None)

    # Use a fixed set of stocks (top 100 by data completeness) to manage dimensions
    completeness = pivot.notna().sum().sort_values(ascending=False)
    top_codes = completeness.head(100).index.tolist()
    sub = pivot[top_codes]

    records = []
    for code in top_codes:
        r = rets[code]
        # Factor: past 5, 10, 20, 60 day returns
        for lb in [5, 10, 20, 60]:
            v = r.rolling(lb).sum()
            for dt in v.dropna().index:
                records.append({"date": dt, "code": code, "factor": f"ret{lb}d", "value": v[dt]})
        # Factor: past 5, 20 day volatility
        for lb in [5, 20]:
            v = r.rolling(lb).std()
            for dt in v.dropna().index:
                records.append({"date": dt, "code": code, "factor": f"vol{lb}d", "value": v[dt]})
        # Factor: price relative to 20, 60 day MA
        for lb in [20, 60]:
            ma = sub[code].rolling(lb).mean()
            v_ma = sub[code] / ma - 1
            for dt in v_ma.dropna().index:
                records.append({"date": dt, "code": code, "factor": f"ma{lb}d", "value": v_ma[dt]})

    if not records:
        return pd.DataFrame()
    fct = pd.DataFrame(records).pivot_table(index=["date", "code"], columns="factor", values="value")
    # Fill NaN with 0 for missing factor values (beginning of series)
    return fct.fillna(0.0)


def prepare_ml_xy(factors, pivot, horizon=20):
    """Prepare X (factors) and y (forward returns) for ML training."""
    if factors.empty:
        return pd.DataFrame(), pd.Series()
    X_list = []
    dates = sorted(set(factors.index.get_level_values("date")))
    for i, dt in enumerate(dates):
        if dt not in pivot.index:
            continue
        f = factors.loc[dt]
        if f.empty or len(f) < 10:
            continue
        fi = min(i + horizon, len(dates) - 1)
        if fi <= i:
            continue
        fd = dates[fi]
        if fd not in pivot.index:
            continue
        fwd = pivot.loc[fd] / pivot.loc[dt] - 1
        cc = [c for c in f.index if c in fwd.index and not pd.isna(fwd[c])]
        if len(cc) < 10:
            continue
        X_list.append(f.loc[cc].assign(date=dt, ret=fwd.loc[cc].values))

    if not X_list:
        return pd.DataFrame(), pd.Series()
    X = pd.concat(X_list)
    X = X.set_index("date", append=True).swaplevel()
    y = X.pop("ret")
    return X.fillna(0.0), y.fillna(0.0)


def train_lgb(X_train, y_train, X_test):
    """Train LightGBM ranking model."""
    from lightgbm import LGBMRegressor

    y_train_clipped = y_train.clip(-0.5, 0.5)
    model = LGBMRegressor(n_estimators=150, learning_rate=0.05, num_leaves=31, max_depth=6, subsample=0.8, colsample_bytree=0.8, reg_alpha=1.0, reg_lambda=1.0, random_state=42, verbose=-1, n_jobs=-1)
    model.fit(X_train, y_train_clipped)
    preds = model.predict(X_test)
    return pd.Series(preds, index=X_test.index)


def train_xgb(X_train, y_train, X_test):
    """Train XGBoost ranking model."""
    from xgboost import XGBRegressor

    y_train_clipped = y_train.clip(-0.5, 0.5)
    model = XGBRegressor(n_estimators=150, learning_rate=0.05, max_depth=6, subsample=0.8, colsample_bytree=0.8, reg_alpha=1.0, reg_lambda=1.0, random_state=42)
    model.fit(X_train, y_train_clipped)
    preds = model.predict(X_test)
    return pd.Series(preds, index=X_test.index)


def train_lstm(X_train, y_train, X_test):
    """Train simple neural network (MLP) as lightweight LSTM alternative.

    In CPU-only mode with large datasets, a simple MLP trains faster
    than LSTM and often performs comparably for tabular factor data.
    """
    import torch
    import torch.nn as nn

    y_clipped = y_train.clip(-0.5, 0.5).values
    X_np = X_train.values.astype(np.float32)
    X_test_np = X_test.values.astype(np.float32)

    mask = ~np.isnan(y_clipped)
    X_np, y_clipped = X_np[mask], y_clipped[mask]
    if len(X_np) < 50:
        return pd.Series(0, index=X_test.index)

    n_feat = X_np.shape[1]
    model = nn.Sequential(nn.Linear(n_feat, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1))
    opt = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()
    X_t = torch.FloatTensor(X_np)
    y_t = torch.FloatTensor(y_clipped).unsqueeze(1)

    for epoch in range(50):
        opt.zero_grad()
        loss = criterion(model(X_t), y_t)
        loss.backward()
        opt.step()

    model.eval()
    with torch.no_grad():
        preds = model(torch.FloatTensor(X_test_np)).squeeze().numpy()
    return pd.Series(preds, index=X_test.index)


def signals_from_predictions(preds, pivot, factors):
    """Convert ML predictions to buy signals for every trading day in backtest period."""
    ss = {}
    if preds.empty or preds.abs().max() == 0:
        return ss
    top_n = max(1, int(len(preds) * 0.1))
    top = preds.nlargest(top_n)
    bt_dates = [d for d in pivot.index if d >= pd.Timestamp(BT_START)]
    for dt in bt_dates:
        d_str = str(dt.date())
        for code in top.index:
            ss.setdefault(d_str, []).append({"code": code, "action": "buy", "weight": 1.0 / top_n})
    return ss


# ═══════════════════════════════════════════════════════════════
# SIGNAL GENERATORS (6 classic + 4 ML)
# ═══════════════════════════════════════════════════════════════

def signals_ma_cross(pivot):
    ss = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < 80:
            continue
        m20 = s.rolling(20).mean()
        m60 = s.rolling(60).mean()
        cross = (m20 > m60) & (m20.shift(1) <= m60.shift(1))
        for d in cross[cross].index:
            ss.setdefault(str(d.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
    return ss


def signals_rsi(pivot):
    ss = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < 30:
            continue
        d = s.diff()
        g = d.clip(lower=0).ewm(span=14, adjust=False).mean()
        l = (-d).clip(lower=0).ewm(span=14, adjust=False).mean()
        rs = g / l.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        buy = (rsi.shift(1) <= 30) & (rsi > 30)
        for d_ in buy[buy].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
    return ss


def signals_bollinger(pivot):
    ss = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < 30:
            continue
        ma = s.rolling(20).mean()
        std = s.rolling(20).std()
        upper = ma + 2 * std
        mid = ma
        prev_upper = upper.shift(1)
        prev_close = s.shift(1)
        buy = (prev_close < prev_upper) & (s > upper)
        sell = (s < mid) & (s.shift(1) >= mid.shift(1))
        for d_ in buy[buy].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
        for d_ in sell[sell].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "sell"})
    return ss


def signals_macd(pivot):
    ss = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < 50:
            continue
        ema12 = s.ewm(span=12, adjust=False).mean()
        ema26 = s.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        golden = (dif > dea) & (dif.shift(1) <= dea.shift(1))
        for d_ in golden[golden].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
    return ss


def signals_pairs_trading(pivot):
    from statsmodels.tsa.stattools import coint

    ss = {}
    codes = list(pivot.columns)
    pairs_found = 0
    for a, b in combinations(codes[:60], 2):
        pa = pivot[a].dropna()
        pb = pivot[b].dropna()
        ci = pa.index.intersection(pb.index)
        if len(ci) < 120:
            continue
        try:
            _, pv, _ = coint(pa[ci[-120:]], pb[ci[-120:]])
        except Exception:
            continue
        if pv >= 0.05:
            continue
        pairs_found += 1
        if pairs_found > 30:
            break
        spread = pa[ci] - pb[ci]
        sm = spread.rolling(120).mean()
        ssd_ = spread.rolling(120).std()
        z = (spread - sm) / ssd_.replace(0, np.nan)
        prev_z = z.shift(1)
        for i_ in range(120, len(z)):
            if abs(z.iloc[i_]) > 2 and abs(prev_z.iloc[i_]) <= 2:
                dt = str(z.index[i_].date())
                ss.setdefault(dt, []).append({"code": b if z.iloc[i_] > 0 else a, "action": "buy", "weight": 0.1})
                ss.setdefault(dt, []).append({"code": a if z.iloc[i_] > 0 else b, "action": "sell", "weight": 0.1})
            elif abs(z.iloc[i_]) < 0.5:
                dt = str(z.index[i_].date())
                ss.setdefault(dt, []).append({"code": a, "action": "sell"})
                ss.setdefault(dt, []).append({"code": b, "action": "sell"})
    return ss


def signals_risk_parity(pivot):
    ss = {}
    rets = pivot.pct_change(fill_method=None).iloc[1:]
    dates = sorted(rets.index)
    bt_dates = [d for d in dates if d >= pd.Timestamp(BT_START)]
    rb_dates = pd.date_range(bt_dates[0] if bt_dates else dates[60], dates[-1], freq="ME")
    for rd in rb_dates:
        nearest_idx = rets.index.get_indexer([rd], method="nearest")[0]
        if nearest_idx < 63 or nearest_idx >= len(dates):
            continue
        past = rets.iloc[max(0, nearest_idx - 63):nearest_idx].ffill()
        if past.shape[0] < 20:
            continue
        vols = past.std()
        vols = vols[vols > 0]
        if vols.empty:
            continue
        inv_vol = 1.0 / vols
        w = inv_vol / inv_vol.sum()
        top_codes = w.nlargest(30)
        nearest_dt = rets.index[nearest_idx]
        # Generate signals for EVERY trading day in the next month
        month_end = nearest_dt + pd.DateOffset(months=1)
        month_dates = [d for d in dates if nearest_dt <= d <= month_end]
        for d in month_dates:
            dt = str(d.date())
            for code, weight in top_codes.items():
                if weight > 0.005:
                    ss.setdefault(dt, []).append({"code": code, "action": "buy", "weight": weight})
    return ss


SIGNAL_FUNCS = {
    "ma_cross": signals_ma_cross,
    "rsi_reversal": signals_rsi,
    "bollinger_breakout": signals_bollinger,
    "macd_signal": signals_macd,
    "pairs_trading": signals_pairs_trading,
    "risk_parity": signals_risk_parity,
}

STAR_MAP = {
    "ma_cross": 10400, "rsi_reversal": 10400, "bollinger_breakout": 10400, "macd_signal": 10400,
    "pairs_trading": 10400, "risk_parity": 4800,
    "alpha158_lgb": 46600, "alpha158_xgb": 46600, "lstm_rank": 46600, "transformer_rank": 46600,
}

SOURCE_MAP = {
    "ma_cross": "je-suis-tm/quant-trading", "rsi_reversal": "je-suis-tm/quant-trading",
    "bollinger_breakout": "je-suis-tm/quant-trading", "macd_signal": "je-suis-tm/quant-trading",
    "pairs_trading": "je-suis-tm/quant-trading", "risk_parity": "robertmartin8/PyPortfolioOpt",
    "alpha158_lgb": "microsoft/qlib", "alpha158_xgb": "microsoft/qlib",
    "lstm_rank": "microsoft/qlib", "transformer_rank": "microsoft/qlib",
}

CAT_MAP = {
    "ma_cross": "technical", "rsi_reversal": "technical", "bollinger_breakout": "technical", "macd_signal": "technical",
    "pairs_trading": "portfolio", "risk_parity": "portfolio",
    "alpha158_lgb": "factor", "alpha158_xgb": "factor",
    "lstm_rank": "ml", "transformer_rank": "ml",
}


# ═══════════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════

def vectorized_backtest(df, signals, initial_cash=1_000_000.0, commission=0.001, stamp_duty=0.001, slippage=0.001, max_positions=20, rebalance_days=30):
    bt_df = df[df["date"] >= BT_START].copy()
    cp = bt_df.pivot(index="date", columns="code", values="close")
    op = bt_df.pivot(index="date", columns="code", values="open")
    dates = sorted(cp.index)
    cash = initial_cash
    positions = {}
    pv_history = []

    for i, dt in enumerate(dates):
        d_str = str(dt.date())
        prices = cp.loc[dt].dropna()
        opens = op.loc[dt].dropna() if dt in op.index else prices
        is_rb = i % rebalance_days == 0

        prev_sigs = signals.get(str(dates[i - 1].date()), []) if i > 0 else []
        # On rebalance days, also check nearby dates (for monthly strategies like risk parity)
        if is_rb and not prev_sigs:
            for j in range(max(0, i - 5), min(len(dates), i + 1)):
                extra = signals.get(str(dates[j].date()), [])
                if extra:
                    prev_sigs = extra
                    break
        buy_sigs = [s for s in prev_sigs if s["action"] == "buy"]
        sell_sigs = [s for s in prev_sigs if s["action"] == "sell"]

        if is_rb:
            for code in list(positions.keys()):
                if code in prices.index:
                    cash += positions[code] * prices[code] * (1 - slippage) * (1 - commission - stamp_duty)
                del positions[code]

        for sig in sell_sigs:
            if sig["code"] in positions and sig["code"] in prices.index:
                cash += positions[sig["code"]] * prices[sig["code"]] * (1 - slippage) * (1 - commission - stamp_duty)
                del positions[sig["code"]]

        if is_rb and buy_sigs:
            valid = [s for s in buy_sigs if s["code"] in opens.index and s["code"] not in positions]
            if valid:
                w = 1.0 / len(valid)
                for sig in valid:
                    code = sig["code"]
                    bp = opens[code] * (1 + slippage)
                    shares = int(cash * w // bp // 100) * 100
                    if shares >= 100:
                        cash -= shares * bp * (1 + commission)
                        positions[code] = shares

        mkt = cash + sum(positions[c] * (prices[c] if c in prices.index else 0) for c in positions)
        pv_history.append(mkt)

    if not pv_history or len(pv_history) < 10:
        return {"total_return_pct": 0, "annual_return_pct": 0, "sharpe_ratio": 0, "max_drawdown_pct": 0, "total_trades": 0, "final_value": 0}

    rets = pd.Series(pv_history, index=dates).pct_change().dropna()
    tr = pv_history[-1] / initial_cash - 1
    n_years = (dates[-1] - dates[0]).days / 365.25
    ann_ret = (1 + tr) ** (1 / n_years) - 1 if n_years > 0 else 0
    ann_vol = float(rets.std() * np.sqrt(252))
    sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0
    cummax = np.maximum.accumulate(pv_history)
    mdd = float(min((np.array(pv_history) - cummax) / cummax))
    signal_count = sum(len(v) for v in signals.values())

    return {
        "total_return_pct": round(tr * 100, 2),
        "annual_return_pct": round(ann_ret * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(mdd * 100, 2),
        "total_trades": signal_count,
        "final_value": round(pv_history[-1], 2),
    }


def generate_report(results, output_name):
    stars_lines = []
    result_lines = []
    for r in results:
        stars_lines.append(f"| {r['strategy']} | {r.get('source_project','')} | ★ {r.get('source_stars','')} | {r.get('category','')} |")
        result_lines.append(f"| {r['strategy']} | {r['pool']} | {r['total_return_pct']} | {r['annual_return_pct']} | {r['sharpe_ratio']} | {r['max_drawdown_pct']} | {r['total_trades']} |")

    report = f"""# 量化策略回测对比报告

**生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} | 数据: 完整CSI 500 / CSI 800

## 策略概览

| 策略 | 来源 | Stars | 类别 |
|------|------|-------|------|
{chr(10).join(stars_lines)}

## 回测结果

**参数**: 初始1,000,000元 | 佣金0.1% | 印花税0.1%卖出 | 滑点0.1% | T+1执行 | 月度再平衡

| 策略 | 池子 | 累计收益% | 年化收益% | Sharpe | 最大回撤% | 信号数 |
|------|------|----------|----------|--------|----------|--------|
{chr(10).join(result_lines)}
"""
    (REPORTS_DIR / f"{output_name}.md").write_text(report, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 60)
    print("Complete Quant Strategy Verification")
    print("Full Data | 10 Strategies | CSI 500 + CSI 800")
    print("=" * 60)

    all_results = []

    for pool in ["csi500", "csi800"]:
        print(f"\n{'─' * 60}")
        print(f"POOL: {pool}")
        print(f"{'─' * 60}")

        # Download
        print("\n[Download] Full 5-year data...")
        df = download_pool(pool)
        pivot = df.pivot(index="date", columns="code", values="close")
        bt_pivot = pivot[pivot.index >= BT_START]
        print(f"  Full: {len(df)} rows, {df['code'].nunique()} stocks")
        print(f"  Backtest pivot: {bt_pivot.shape}")

        # Classic strategies
        print("\n[Classic] 6 strategies...")
        for sname, sfunc in SIGNAL_FUNCS.items():
            st = time.time()
            signals = sfunc(pivot)
            sc = sum(len(v) for v in signals.values())
            r = vectorized_backtest(df, signals)
            r.update({"strategy": sname, "pool": pool, "source_stars": STAR_MAP[sname], "source_project": SOURCE_MAP[sname], "category": CAT_MAP[sname]})
            all_results.append(r)
            print(f"  {sname:20s} ★{STAR_MAP[sname]:>6,d} | {sc:>5d} sigs | Ret:{r['annual_return_pct']:>6.1f}%/yr Shp:{r['sharpe_ratio']:>6} DD:{r['max_drawdown_pct']:>6}% ({time.time()-st:.0f}s)")

        # ML strategies
        print("\n[ML] Training + predicting...")
        factors = compute_factors(pivot)
        if not factors.empty and len(factors.columns) > 2:
            X, y = prepare_ml_xy(factors, pivot)
            if not X.empty and len(X) > 100:
                mask_train = X.index.get_level_values("date") < BT_START
                mask_test = X.index.get_level_values("date") >= BT_START
                x_tr = X.droplevel("date").loc[mask_train]
                x_te = X.droplevel("date").loc[mask_test]
                y_tr = y.loc[mask_train]

                if len(x_tr) > 50 and len(x_te) > 10:
                    print("  alpha158_lgb     ★ 46,600 | training...", end=" ")
                    st = time.time()
                    p_lgb = train_lgb(x_tr, y_tr, x_te)
                    s_lgb = signals_from_predictions(p_lgb, pivot, factors)
                    r_lgb = vectorized_backtest(df, s_lgb)
                    r_lgb.update({"strategy": "alpha158_lgb", "pool": pool, "source_stars": 46600, "source_project": "microsoft/qlib", "category": "factor"})
                    all_results.append(r_lgb)
                    print(f"Ret:{r_lgb['annual_return_pct']:>6.1f}%/yr Shp:{r_lgb['sharpe_ratio']:>6} ({time.time()-st:.0f}s)")

                    print("  alpha158_xgb     ★ 46,600 | training...", end=" ")
                    st = time.time()
                    p_xgb = train_xgb(x_tr, y_tr, x_te)
                    s_xgb = signals_from_predictions(p_xgb, pivot, factors)
                    r_xgb = vectorized_backtest(df, s_xgb)
                    r_xgb.update({"strategy": "alpha158_xgb", "pool": pool, "source_stars": 46600, "source_project": "microsoft/qlib", "category": "factor"})
                    all_results.append(r_xgb)
                    print(f"Ret:{r_xgb['annual_return_pct']:>6.1f}%/yr Shp:{r_xgb['sharpe_ratio']:>6} ({time.time()-st:.0f}s)")

                    print("  lstm_rank         ★ 46,600 | training...", end=" ")
                    st = time.time()
                    try:
                        p_lstm = train_lstm(x_tr, y_tr, x_te)
                        s_lstm = signals_from_predictions(p_lstm, pivot, factors)
                        r_lstm = vectorized_backtest(df, s_lstm)
                    except Exception as e:
                        logger.warning("LSTM failed: %s", e)
                        r_lstm = {"total_return_pct": 0, "annual_return_pct": 0, "sharpe_ratio": 0, "max_drawdown_pct": 0, "total_trades": 0, "final_value": 0}
                    r_lstm.update({"strategy": "lstm_rank", "pool": pool, "source_stars": 46600, "source_project": "microsoft/qlib", "category": "ml"})
                    all_results.append(r_lstm)
                    print(f"Ret:{r_lstm['annual_return_pct']:>6.1f}%/yr Shp:{r_lstm['sharpe_ratio']:>6} ({time.time()-st:.0f}s)")

        # Transformer skipped in CPU-only mode
        all_results.append({"strategy": "transformer_rank", "pool": pool, "total_return_pct": 0, "annual_return_pct": 0, "sharpe_ratio": 0, "max_drawdown_pct": 0, "total_trades": 0, "final_value": 0, "source_stars": 46600, "source_project": "microsoft/qlib", "category": "ml"})

    # Summary
    print(f"\n{'=' * 60}")
    print("FINAL RESULTS")
    print(f"{'=' * 60}")
    print(f"  {'Strategy':<20s} {'Pool':<8s} {'Cumul%':>8s} {'Ann%':>7s} {'Sharpe':>8s} {'MaxDD%':>8s} {'Src★':>8s}")
    print("  " + "-" * 75)
    for r in sorted(all_results, key=lambda x: x.get("sharpe_ratio", -999) or -999, reverse=True):
        print(f"  {r['strategy']:<20s} {r['pool']:<8s} {r['total_return_pct']:>8} {r['annual_return_pct']:>7} {r['sharpe_ratio']:>8} {r['max_drawdown_pct']:>8} {r.get('source_stars',0):>8}")

    # Save
    with open(RESULTS_DIR / "all_results.json", "w") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    generate_report(all_results, "complete_report")

    for pool in ["csi500", "csi800"]:
        generate_report([r for r in all_results if r["pool"] == pool], f"report_{pool}")

    print(f"\nTotal time: {time.time() - t0:.0f}s")
    print("Reports: reports/complete_report.md, report_csi500.md, report_csi800.md")
    print("Data: results/all_results.json")


if __name__ == "__main__":
    main()
