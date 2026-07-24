"""
Unified signal service — all 10 strategies, one interface.

Technical strategies (6): event-driven signals on the full price pivot.
ML strategies (4): walk-forward — train on data strictly before each retrain
date, predict top-10 stocks, hold until next retrain. LSTM/Transformer are
real sequence models (PyTorch), not MLP placeholders.

Strategy logic is identical to research/run_backtest.py; execution semantics
(position sizing, costs) live in sim_engine, not here.
"""

from __future__ import annotations

import logging
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent / "state" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

TOP_PCT = 0.1          # ML: buy top 10% of ranked stocks (of ~100 → 10 names)
RETRAIN_EVERY = 21     # trading days between ML retraining
HORIZON = 20           # forward-return horizon for ML labels
SEQ_LEN = 10           # sequence length for LSTM/Transformer

STRATEGY_META = {
    "ma_cross":           {"label": "MA Cross",   "cat": "technical", "desc": "趋势跟踪, 信号稀少质量高"},
    "rsi_reversal":       {"label": "RSI Rev.",   "cat": "technical", "desc": "均值回归, 牛市逆势"},
    "bollinger_breakout": {"label": "Bollinger",  "cat": "technical", "desc": "波动率突破, 换手极高"},
    "macd_signal":        {"label": "MACD",       "cat": "technical", "desc": "趋势+动量, 三重确认"},
    "pairs_trading":      {"label": "Pairs Tr.",  "cat": "portfolio", "desc": "统计套利, 需做空能力"},
    "risk_parity":        {"label": "Risk Par.",  "cat": "portfolio", "desc": "低波动, 回撤控制最优"},
    "alpha158_lgb_wf":    {"label": "LGB WF",     "cat": "ml",        "desc": "Walk-Forward, 每月重训"},
    "alpha158_xgb_wf":    {"label": "XGB WF",     "cat": "ml",        "desc": "Walk-Forward, XGBoost"},
    "lstm_rank":          {"label": "LSTM",       "cat": "ml",        "desc": "LSTM序列排序, 每月重训"},
    "transformer_rank":   {"label": "TF",         "cat": "ml",        "desc": "Transformer序列排序"},
}
ALL_STRATEGIES = list(STRATEGY_META)


# ═══════════════════════════════════════════════════════════════
# TECHNICAL SIGNALS (6) — identical logic to research backtest
# ═══════════════════════════════════════════════════════════════

def signals_ma_cross(pivot: pd.DataFrame) -> dict:
    ss: dict[str, list] = {}
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


def signals_rsi(pivot: pd.DataFrame) -> dict:
    ss: dict[str, list] = {}
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


def signals_bollinger(pivot: pd.DataFrame) -> dict:
    ss: dict[str, list] = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < 30:
            continue
        ma = s.rolling(20).mean()
        std = s.rolling(20).std()
        upper = ma + 2 * std
        buy = (s.shift(1) < upper.shift(1)) & (s > upper)
        sell = (s < ma) & (s.shift(1) >= ma.shift(1))
        for d_ in buy[buy].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
        for d_ in sell[sell].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "sell"})
    return ss


def signals_macd(pivot: pd.DataFrame) -> dict:
    ss: dict[str, list] = {}
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


def signals_pairs_trading(pivot: pd.DataFrame) -> dict:
    from statsmodels.tsa.stattools import coint
    ss: dict[str, list] = {}
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


def signals_risk_parity(pivot: pd.DataFrame, sim_start: str) -> dict:
    ss: dict[str, list] = {}
    rets = pivot.pct_change(fill_method=None).iloc[1:]
    dates = sorted(rets.index)
    bt_dates = [d for d in dates if d >= pd.Timestamp(sim_start)]
    if not bt_dates:
        return ss
    rb_dates = pd.date_range(bt_dates[0], dates[-1], freq="ME")
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
        month_end = nearest_dt + pd.DateOffset(months=1)
        month_dates = [d for d in dates if nearest_dt <= d <= month_end]
        for d in month_dates:
            dt = str(d.date())
            for code, weight in top_codes.items():
                if weight > 0.005:
                    ss.setdefault(dt, []).append({"code": code, "action": "buy", "weight": weight})
    return ss


TECH_FUNCS = {
    "ma_cross": signals_ma_cross,
    "rsi_reversal": signals_rsi,
    "bollinger_breakout": signals_bollinger,
    "macd_signal": signals_macd,
    "pairs_trading": signals_pairs_trading,
}


# ═══════════════════════════════════════════════════════════════
# FACTORS & ML LABELS
# ═══════════════════════════════════════════════════════════════

def compute_factors(pivot: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    """8 factors per stock (top_n most complete) → index [date, code]."""
    rets = pivot.pct_change(fill_method=None)
    completeness = pivot.notna().sum().sort_values(ascending=False)
    top_codes = completeness.head(top_n).index.tolist()
    sub = pivot[top_codes]

    records = []
    for code in top_codes:
        r = rets[code]
        for lb in [5, 10, 20, 60]:
            v = r.rolling(lb).sum()
            for dt in v.dropna().index:
                records.append({"date": dt, "code": code, "factor": f"ret{lb}d", "value": v[dt]})
        for lb in [5, 20]:
            v = r.rolling(lb).std()
            for dt in v.dropna().index:
                records.append({"date": dt, "code": code, "factor": f"vol{lb}d", "value": v[dt]})
        for lb in [20, 60]:
            ma = sub[code].rolling(lb).mean()
            v_ma = sub[code] / ma - 1
            for dt in v_ma.dropna().index:
                records.append({"date": dt, "code": code, "factor": f"ma{lb}d", "value": v_ma[dt]})
    if not records:
        return pd.DataFrame()
    fct = pd.DataFrame(records).pivot_table(index=["date", "code"], columns="factor", values="value")
    return fct.fillna(0.0)


def prepare_ml_xy(factors: pd.DataFrame, pivot: pd.DataFrame, horizon: int = HORIZON):
    """X, y, and label-end dates (for walk-forward leakage filtering)."""
    if factors.empty:
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")
    X_list, fd_list = [], []
    dates = sorted(set(factors.index.get_level_values("date")))
    dpos = {d: i for i, d in enumerate(dates)}
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
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")
    X = pd.concat(X_list)
    X = X.set_index("date", append=True).swaplevel()
    y = X.pop("ret")
    sample_dates = X.index.get_level_values("date")
    fd_s = pd.Series([dates[min(dpos[d] + horizon, len(dates) - 1)] for d in sample_dates], index=X.index)
    return X.fillna(0.0), y.fillna(0.0), fd_s


# ═══════════════════════════════════════════════════════════════
# TREE MODELS (LGB / XGB)
# ═══════════════════════════════════════════════════════════════

def train_lgb(X_train, y_train, X_test):
    from lightgbm import LGBMRegressor
    y_c = y_train.clip(-0.5, 0.5)
    model = LGBMRegressor(n_estimators=150, learning_rate=0.05, num_leaves=31, max_depth=6,
                          subsample=0.8, colsample_bytree=0.8, reg_alpha=1.0, reg_lambda=1.0,
                          random_state=42, verbose=-1, n_jobs=-1)
    model.fit(X_train, y_c)
    return pd.Series(model.predict(X_test), index=X_test.index)


def train_xgb(X_train, y_train, X_test):
    from xgboost import XGBRegressor
    y_c = y_train.clip(-0.5, 0.5)
    model = XGBRegressor(n_estimators=150, learning_rate=0.05, max_depth=6, subsample=0.8,
                         colsample_bytree=0.8, reg_alpha=1.0, reg_lambda=1.0, random_state=42)
    model.fit(X_train, y_c)
    return pd.Series(model.predict(X_test), index=X_test.index)


# ═══════════════════════════════════════════════════════════════
# DEEP SEQUENCE MODELS (LSTM / Transformer) — real implementations
# ═══════════════════════════════════════════════════════════════

def _build_sequences(factors: pd.DataFrame, sample_index: pd.MultiIndex, seq_len: int = SEQ_LEN):
    """For each (date, code) in sample_index, build [seq_len, n_feat] factor sequence.

    Fast path: per-code numpy blocks + date→row dicts; missing window rows → zeros.
    """
    fdates = sorted(set(factors.index.get_level_values("date")))
    fpos = {d: i for i, d in enumerate(fdates)}
    n_feat = len(factors.columns)
    by_code: dict = {}
    for c, g in factors.groupby(level="code"):
        g = g.droplevel("code")
        by_code[c] = (g.values.astype(np.float32), {d: i for i, d in enumerate(g.index)})

    seqs, valid = [], []
    for dt, code in sample_index:
        blk = by_code.get(code)
        if blk is None or dt not in fpos or fpos[dt] < seq_len - 1:
            valid.append(False)
            continue
        arr, rpos = blk
        rows = np.zeros((seq_len, n_feat), dtype=np.float32)
        for j, wd in enumerate(fdates[fpos[dt] - seq_len + 1: fpos[dt] + 1]):
            ri = rpos.get(wd)
            if ri is not None:
                rows[j] = arr[ri]
        seqs.append(rows)
        valid.append(True)
    if not seqs:
        return np.empty((0, seq_len, n_feat), dtype=np.float32), valid
    return np.stack(seqs), valid


def _make_net(model_type: str, n_feat: int):
    import torch
    import torch.nn as nn

    class LSTMNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(n_feat, 48, num_layers=2, batch_first=True, dropout=0.1)
            self.head = nn.Sequential(nn.Linear(48, 24), nn.ReLU(), nn.Dropout(0.2), nn.Linear(24, 1))

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1]).squeeze(-1)

    class TFNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.proj = nn.Linear(n_feat, 48)
            enc_layer = nn.TransformerEncoderLayer(d_model=48, nhead=4, dim_feedforward=96,
                                                   dropout=0.1, batch_first=True)
            self.encoder = nn.TransformerEncoder(enc_layer, num_layers=2)
            self.head = nn.Sequential(nn.Linear(48, 24), nn.ReLU(), nn.Dropout(0.2), nn.Linear(24, 1))

        def forward(self, x):
            h = self.encoder(self.proj(x))
            return self.head(h.mean(dim=1)).squeeze(-1)

    return LSTMNet() if model_type == "lstm" else TFNet()


def train_sequence_model(model_type: str, factors: pd.DataFrame, X_train: pd.DataFrame,
                         y_train: pd.Series, X_test: pd.DataFrame, pred_date=None,
                         epochs: int = 25) -> pd.Series:
    """Train LSTM/Transformer on factor sequences; return predictions for X_test.

    X_test may be a plain cross-section (index=code) — then pred_date is used
    as the sequence anchor date for every row.
    """
    import torch

    torch.manual_seed(42)
    np.random.seed(42)

    Xtr, valid_tr = _build_sequences(factors, X_train.index)
    ytr = np.clip(y_train.values[np.array(valid_tr, dtype=bool)].astype(np.float32), -0.5, 0.5)
    if len(Xtr) < 200:
        logger.warning("%s: only %d sequence samples, returning zeros", model_type, len(Xtr))
        return pd.Series(0.0, index=X_test.index)

    test_index = X_test.index
    if not isinstance(test_index, pd.MultiIndex):
        if pred_date is None:
            pred_date = max(factors.index.get_level_values("date"))
        test_index = pd.MultiIndex.from_tuples([(pred_date, c) for c in X_test.index],
                                               names=["date", "code"])
    Xte, _ = _build_sequences(factors, test_index)
    if len(Xte) == 0:
        return pd.Series(0.0, index=X_test.index)

    # Subsample to keep CPU training time bounded (~80k sequences max)
    MAX_TRAIN = 80_000
    if len(Xtr) > MAX_TRAIN:
        sel = np.random.choice(len(Xtr), MAX_TRAIN, replace=False)
        Xtr, ytr = Xtr[sel], ytr[sel]

    model = _make_net(model_type, Xtr.shape[2])
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    loss_fn = torch.nn.HuberLoss(delta=0.1)

    Xt = torch.FloatTensor(Xtr)
    yt = torch.FloatTensor(ytr)
    n = len(Xt)
    bs = 1024
    model.train()
    for ep in range(epochs):
        perm = torch.randperm(n)
        for i in range(0, n, bs):
            idx = perm[i:i + bs]
            opt.zero_grad()
            loss = loss_fn(model(Xt[idx]), yt[idx])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        sched.step()
        if (ep + 1) % 10 == 0:
            logger.info("  %s epoch %d/%d loss=%.5f", model_type, ep + 1, epochs, loss.item())

    model.eval()
    with torch.no_grad():
        preds = model(torch.FloatTensor(Xte)).numpy()
    return pd.Series(preds, index=X_test.index)


# ═══════════════════════════════════════════════════════════════
# WALK-FORWARD ORCHESTRATION
# ═══════════════════════════════════════════════════════════════

def _retrain_dates(sim_dates: list[pd.Timestamp]) -> list[int]:
    """Positions in sim_dates where ML models (re)train: start + every RETRAIN_EVERY."""
    return list(range(0, len(sim_dates), RETRAIN_EVERY))


_SIGNAL_CACHE_DIR = Path(__file__).resolve().parent.parent / "state" / "signals_cache"
_SIGNAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _ml_top_codes_at_retrains(pivot: pd.DataFrame, strategy: str,
                              sim_dates: list[pd.Timestamp], factors: pd.DataFrame) -> dict[str, list[str]]:
    """Top-pick codes at every retrain date, with disk cache.

    A retrain at date D trains only on samples with label-end <= D, so cached
    retrains never change when new data arrives — only newly crossed retrain
    dates trigger actual training.
    """
    import json
    cache_file = _SIGNAL_CACHE_DIR / f"ml_{strategy}.json"
    cached: dict = {"retrains": {}}
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
        except Exception:
            cached = {"retrains": {}}
    retrains: dict[str, list[str]] = cached.get("retrains", {})

    rt_positions = _retrain_dates(sim_dates)
    needed = [sim_dates[p] for p in rt_positions]
    missing = [d for d in needed if str(d.date()) not in retrains]
    if not missing:
        return {str(d.date()): retrains[str(d.date())] for d in needed}

    model_type = {"alpha158_lgb_wf": "lgb", "alpha158_xgb_wf": "xgb",
                  "lstm_rank": "lstm", "transformer_rank": "transformer"}[strategy]
    X, y, fd = prepare_ml_xy(factors, pivot)
    if X.empty:
        return {str(d.date()): retrains.get(str(d.date()), []) for d in needed}
    factor_dates = sorted(set(factors.index.get_level_values("date")))

    for rt_date in missing:
        train_mask = fd <= rt_date
        X_tr, y_tr = X.loc[train_mask], y.loc[train_mask]
        avail = [d for d in factor_dates if d <= rt_date]
        if not avail or len(X_tr) < 200:
            retrains[str(rt_date.date())] = []
            continue
        pred_date = avail[-1]
        tf = factors.loc[pred_date]
        if tf.empty:
            retrains[str(rt_date.date())] = []
            continue

        logger.info("%s retrain @%s: %d train samples, predicting %d stocks",
                    strategy, rt_date.date(), len(X_tr), len(tf))
        try:
            if model_type == "lgb":
                preds = train_lgb(X_tr, y_tr, tf)
            elif model_type == "xgb":
                preds = train_xgb(X_tr, y_tr, tf)
            else:
                preds = train_sequence_model(model_type, factors, X_tr, y_tr, tf, pred_date=pred_date)
        except Exception as e:
            logger.error("%s training failed @%s: %s", strategy, rt_date.date(), e)
            retrains[str(rt_date.date())] = []
            continue
        if preds.empty or preds.abs().max() == 0:
            retrains[str(rt_date.date())] = []
            continue
        top = preds.nlargest(max(1, int(len(preds) * TOP_PCT)))
        retrains[str(rt_date.date())] = list(top.index)

    cache_file.write_text(json.dumps({"retrains": retrains}, ensure_ascii=False))
    return {str(d.date()): retrains.get(str(d.date()), []) for d in needed}


def generate_ml_signals(pivot: pd.DataFrame, strategy: str, sim_dates: list[pd.Timestamp],
                        factors: pd.DataFrame | None = None) -> dict:
    """Walk-forward ML signals: hold top-10% picks between retrain dates."""
    if not sim_dates:
        return {}
    if factors is None:
        logger.info("Computing factors for ML strategies...")
        factors = compute_factors(pivot)
    if factors.empty:
        return {}

    rt_map = _ml_top_codes_at_retrains(pivot, strategy, sim_dates, factors)
    rt_positions = _retrain_dates(sim_dates)

    ss: dict[str, list] = {}
    for k, pos in enumerate(rt_positions):
        rt_date = sim_dates[pos]
        codes = rt_map.get(str(rt_date.date()), [])
        if not codes:
            continue
        end_pos = rt_positions[k + 1] if k + 1 < len(rt_positions) else len(sim_dates)
        for d in sim_dates[pos:end_pos]:
            d_str = str(d.date())
            for code in codes:
                ss.setdefault(d_str, []).append({"code": code, "action": "buy", "weight": 1.0 / len(codes)})
    return ss


def generate_all_signals(pivot: pd.DataFrame, sim_start: str,
                         strategies: list[str] | None = None) -> dict[str, dict]:
    """All strategies → {strategy: {date_str: [signals]}} for the sim window.

    Technical signals are computed once on the full pivot (fast, no lookahead
    by construction — each signal uses only data up to its date).
    ML signals use walk-forward retraining inside [sim_start, end].
    """
    strategies = strategies or ALL_STRATEGIES
    sim_dates = [d for d in pivot.index if d >= pd.Timestamp(sim_start)]
    out: dict[str, dict] = {}

    for sn in strategies:
        if sn in TECH_FUNCS:
            logger.info("Signals: %s", sn)
            out[sn] = TECH_FUNCS[sn](pivot)
        elif sn == "risk_parity":
            logger.info("Signals: %s", sn)
            out[sn] = signals_risk_parity(pivot, sim_start)

    ml_strats = [s for s in strategies if STRATEGY_META[s]["cat"] == "ml"]
    if ml_strats:
        factors = compute_factors(pivot)
        for sn in ml_strats:
            try:
                out[sn] = generate_ml_signals(pivot, sn, sim_dates, factors)
            except Exception as e:
                logger.error("ML signals failed for %s: %s", sn, e)
                out[sn] = {}
    return out


def latest_signals_for_date(all_sigs: dict[str, dict], date_str: str) -> dict[str, list]:
    """{strategy: [buy codes]} snapshot at a date — used by the recommendation email."""
    return {sn: [s for s in sigs.get(date_str, [])] for sn, sigs in all_sigs.items()}
