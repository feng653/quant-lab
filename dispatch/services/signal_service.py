"""
Signal service — registry-driven orchestration for all strategies.

Signal strategies live in core/strategies/ (auto-discovered via registry).
This module keeps only the shared ML infrastructure:
  - factor computation (basic8 for LGB/XGB/LSTM/TF, alpha13 for AM GBR)
  - model training (tree models, sequence models, GBR)
  - walk-forward retrain scheduling with disk cache

All per-strategy knobs (retrain_every, top_pct/top_k, horizon, train_window,
model hyperparams) come from the registry spec merged with user overrides.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from core.strategies.registry import REGISTRY, get_params, get_spec, scan_strategies

logger = logging.getLogger(__name__)

_SIGNAL_CACHE_DIR = Path(__file__).resolve().parent.parent / "state" / "signals_cache"
_SIGNAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def strategy_meta() -> dict:
    """{key: {label, cat, desc}} for all registered strategies."""
    scan_strategies()
    return {k: {"label": s.label, "cat": s.category, "desc": s.desc}
            for k, s in REGISTRY.items()}


# ═══════════════════════════════════════════════════════════════
# FACTORS
# ═══════════════════════════════════════════════════════════════

def compute_factors(pivot: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    """basic8 factors per stock (top_n most complete) → index [date, code]."""
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


def compute_factors_alpha13(df: pd.DataFrame) -> pd.DataFrame:
    """alpha13 feature set (AlphaMaster GBR), all stocks → index [date, code].

    Columns: ret_1d ret_5d ret_10d ret_20d volume_ratio turn_ratio
             close_div_ma5 close_div_ma20 volatility_5d volatility_20d
             hl_ratio hl_ratio_5d pctChg
    """
    d = df.sort_values(["code", "date"]).copy()
    frames = []
    for code, g in d.groupby("code"):
        g = g.set_index("date").sort_index()
        close, vol = g["close"], g["volume"]
        turn = g["turnover"] if "turnover" in g.columns else pd.Series(0.0, index=g.index)
        ret1 = close.pct_change()
        out = pd.DataFrame({
            "ret_1d": ret1,
            "ret_5d": close.pct_change(5),
            "ret_10d": close.pct_change(10),
            "ret_20d": close.pct_change(20),
            "volume_ratio": vol / vol.rolling(20).mean(),
            "turn_ratio": turn / turn.rolling(20).mean().replace(0, np.nan),
            "close_div_ma5": close / close.rolling(5).mean() - 1,
            "close_div_ma20": close / close.rolling(20).mean() - 1,
            "volatility_5d": ret1.rolling(5).std(),
            "volatility_20d": ret1.rolling(20).std(),
            "hl_ratio": (g["high"] - g["low"]) / close,
            "pctChg": ret1,
        })
        out["hl_ratio_5d"] = out["hl_ratio"].rolling(5).mean()
        out = out[["ret_1d", "ret_5d", "ret_10d", "ret_20d", "volume_ratio", "turn_ratio",
                   "close_div_ma5", "close_div_ma20", "volatility_5d", "volatility_20d",
                   "hl_ratio", "hl_ratio_5d", "pctChg"]]
        out = out.clip(-0.5, 0.5).fillna(0.0)
        out["code"] = code
        frames.append(out.reset_index())
    if not frames:
        return pd.DataFrame()
    fct = pd.concat(frames, ignore_index=True)
    fct["date"] = pd.to_datetime(fct["date"])
    return fct.set_index(["date", "code"])


def prepare_ml_xy(factors: pd.DataFrame, pivot: pd.DataFrame, horizon: int = 20):
    """X, y, and label-end dates (for walk-forward leakage filtering)."""
    if factors.empty:
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")
    X_list = []
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
# MODEL TRAINING (param-driven)
# ═══════════════════════════════════════════════════════════════

def train_lgb(X_train, y_train, X_test, params: dict):
    from lightgbm import LGBMRegressor
    y_c = y_train.clip(-0.5, 0.5)
    model = LGBMRegressor(n_estimators=int(params.get("n_estimators", 150)),
                          learning_rate=float(params.get("learning_rate", 0.05)),
                          num_leaves=31, max_depth=int(params.get("max_depth", 6)),
                          subsample=0.8, colsample_bytree=0.8, reg_alpha=1.0, reg_lambda=1.0,
                          random_state=42, verbose=-1, n_jobs=-1)
    model.fit(X_train, y_c)
    return pd.Series(model.predict(X_test), index=X_test.index)


def train_xgb(X_train, y_train, X_test, params: dict):
    from xgboost import XGBRegressor
    y_c = y_train.clip(-0.5, 0.5)
    model = XGBRegressor(n_estimators=int(params.get("n_estimators", 150)),
                         learning_rate=float(params.get("learning_rate", 0.05)),
                         max_depth=int(params.get("max_depth", 6)),
                         subsample=0.8, colsample_bytree=0.8, reg_alpha=1.0, reg_lambda=1.0,
                         random_state=42)
    model.fit(X_train, y_c)
    return pd.Series(model.predict(X_test), index=X_test.index)


def train_gbr(X_train, y_train, X_test, params: dict):
    """sklearn GradientBoostingRegressor — AlphaMaster migration."""
    from sklearn.ensemble import GradientBoostingRegressor
    y_c = y_train.clip(-0.1, 0.1)
    model = GradientBoostingRegressor(
        n_estimators=int(params.get("n_estimators", 40)),
        max_depth=int(params.get("max_depth", 3)),
        learning_rate=float(params.get("learning_rate", 0.05)),
        subsample=float(params.get("subsample", 0.6)),
        min_samples_leaf=40, random_state=42)
    model.fit(X_train, y_c)
    return pd.Series(model.predict(X_test), index=X_test.index)


# ── sequence models ──

SEQ_LEN_DEFAULT = 10


def _build_sequences(factors: pd.DataFrame, sample_index: pd.MultiIndex, seq_len: int):
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


def _make_net(model_type: str, n_feat: int, params: dict):
    import torch
    import torch.nn as nn
    hidden = int(params.get("hidden", params.get("d_model", 48)))

    class LSTMNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(n_feat, hidden, num_layers=2, batch_first=True, dropout=0.1)
            self.head = nn.Sequential(nn.Linear(hidden, 24), nn.ReLU(), nn.Dropout(0.2), nn.Linear(24, 1))

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1]).squeeze(-1)

    class TFNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.proj = nn.Linear(n_feat, hidden)
            enc_layer = nn.TransformerEncoderLayer(d_model=hidden, nhead=4, dim_feedforward=hidden * 2,
                                                   dropout=0.1, batch_first=True)
            self.encoder = nn.TransformerEncoder(enc_layer, num_layers=2)
            self.head = nn.Sequential(nn.Linear(hidden, 24), nn.ReLU(), nn.Dropout(0.2), nn.Linear(24, 1))

        def forward(self, x):
            h = self.encoder(self.proj(x))
            return self.head(h.mean(dim=1)).squeeze(-1)

    return LSTMNet() if model_type == "lstm" else TFNet()


def train_sequence_model(model_type: str, factors: pd.DataFrame, X_train: pd.DataFrame,
                         y_train: pd.Series, X_test: pd.DataFrame, params: dict,
                         pred_date=None) -> pd.Series:
    import torch

    torch.manual_seed(42)
    np.random.seed(42)
    seq_len = int(params.get("seq_len", SEQ_LEN_DEFAULT))
    epochs = int(params.get("epochs", 25))
    lr = float(params.get("lr", 1e-3))

    Xtr, valid_tr = _build_sequences(factors, X_train.index, seq_len)
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
    Xte, _ = _build_sequences(factors, test_index, seq_len)
    if len(Xte) == 0:
        return pd.Series(0.0, index=X_test.index)

    MAX_TRAIN = int(params.get("max_train", 80_000))
    if len(Xtr) > MAX_TRAIN:
        sel = np.random.choice(len(Xtr), MAX_TRAIN, replace=False)
        Xtr, ytr = Xtr[sel], ytr[sel]

    model = _make_net(model_type, Xtr.shape[2], params)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
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
# WALK-FORWARD ORCHESTRATION (registry/param-driven)
# ═══════════════════════════════════════════════════════════════

def _params_hash(params: dict) -> str:
    return hashlib.md5(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:8]


def _ml_top_codes_at_retrains(pivot: pd.DataFrame, strategy: str,
                              sim_dates: list[pd.Timestamp], factors: pd.DataFrame) -> dict[str, list[str]]:
    """Top-pick codes at every retrain date, with disk cache (invalidated on param change)."""
    spec = get_spec(strategy)
    params = get_params(strategy)
    model_type = spec.ml_model_type
    retrain_every = int(params.get("retrain_every", 21))
    horizon = int(params.get("horizon", 20))
    train_window = int(params.get("train_window", 0))
    top_k = params.get("top_k")
    top_pct = float(params.get("top_pct", 0.1))
    phash = _params_hash({"m": model_type, **params})

    cache_file = _SIGNAL_CACHE_DIR / f"ml_{strategy}.json"
    cached: dict = {"params_hash": None, "retrains": {}}
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
        except Exception:
            pass
    if cached.get("params_hash") != phash:
        logger.info("%s params changed, invalidating ML signal cache", strategy)
        cached = {"params_hash": phash, "retrains": {}}
    retrains: dict[str, list[str]] = cached.get("retrains", {})

    rt_positions = list(range(0, len(sim_dates), retrain_every))
    needed = [sim_dates[p] for p in rt_positions]
    missing = [d for d in needed if str(d.date()) not in retrains]
    if not missing:
        return {str(d.date()): retrains[str(d.date())] for d in needed}

    X, y, fd = prepare_ml_xy(factors, pivot, horizon=horizon)
    if X.empty:
        return {str(d.date()): retrains.get(str(d.date()), []) for d in needed}
    factor_dates = sorted(set(factors.index.get_level_values("date")))
    sample_dates = X.index.get_level_values("date")

    for rt_date in missing:
        train_mask = fd <= rt_date
        X_tr, y_tr = X.loc[train_mask], y.loc[train_mask]
        if train_window > 0:
            win_start_idx = max(0, len([d for d in factor_dates if d <= rt_date]) - train_window)
            win_start = factor_dates[win_start_idx]
            tw_mask = X_tr.index.get_level_values("date") >= win_start
            X_tr, y_tr = X_tr[tw_mask], y_tr[tw_mask]
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
                preds = train_lgb(X_tr, y_tr, tf, params)
            elif model_type == "xgb":
                preds = train_xgb(X_tr, y_tr, tf, params)
            elif model_type == "gbr":
                preds = train_gbr(X_tr, y_tr, tf, params)
            else:
                preds = train_sequence_model(model_type, factors, X_tr, y_tr, tf, params, pred_date=pred_date)
        except Exception as e:
            logger.error("%s training failed @%s: %s", strategy, rt_date.date(), e)
            retrains[str(rt_date.date())] = []
            continue
        if preds.empty or preds.abs().max() == 0:
            retrains[str(rt_date.date())] = []
            continue
        n_top = int(top_k) if top_k else max(1, int(len(preds) * top_pct))
        top = preds.nlargest(min(n_top, len(preds)))
        retrains[str(rt_date.date())] = list(top.index)

    cached = {"params_hash": phash, "retrains": retrains}
    cache_file.write_text(json.dumps(cached, ensure_ascii=False))
    return {str(d.date()): retrains.get(str(d.date()), []) for d in needed}


def generate_ml_signals(pivot: pd.DataFrame, strategy: str, sim_dates: list[pd.Timestamp],
                        factors: pd.DataFrame | None = None) -> dict:
    """Walk-forward ML signals: hold top picks between retrain dates."""
    if not sim_dates:
        return {}
    spec = get_spec(strategy)
    if spec is None:
        return {}
    if factors is None:
        factors = compute_factors(pivot)
    if factors.empty:
        return {}

    params = get_params(strategy)
    retrain_every = int(params.get("retrain_every", 21))
    rt_map = _ml_top_codes_at_retrains(pivot, strategy, sim_dates, factors)
    rt_positions = list(range(0, len(sim_dates), retrain_every))

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
                         strategies: list[str] | None = None,
                         df: pd.DataFrame | None = None) -> dict[str, dict]:
    """Registry-driven: {strategy: {date_str: [signals]}} for the sim window.

    Signal strategies: spec.signal_func(pivot, params) with _sim_start injected.
    ML strategies: walk-forward with per-strategy params and feature set.
    """
    scan_strategies()
    strategies = strategies or list(REGISTRY.keys())
    sim_dates = [d for d in pivot.index if d >= pd.Timestamp(sim_start)]
    out: dict[str, dict] = {}

    factors_cache: dict[str, pd.DataFrame] = {}

    for sn in strategies:
        spec = REGISTRY.get(sn)
        if spec is None:
            logger.warning("Unknown strategy %s, skipped", sn)
            continue
        params = get_params(sn)
        if spec.signal_func is not None:
            logger.info("Signals: %s", sn)
            try:
                out[sn] = spec.signal_func(pivot, {**params, "_sim_start": sim_start})
            except Exception as e:
                logger.error("Signal generation failed for %s: %s", sn, e)
                out[sn] = {}
        elif spec.ml_model_type:
            try:
                if spec.feature_set == "alpha13":
                    if "alpha13" not in factors_cache:
                        if df is None:
                            raise ValueError("alpha13 feature set requires full OHLCV df")
                        logger.info("Computing alpha13 factors...")
                        factors_cache["alpha13"] = compute_factors_alpha13(df)
                    factors = factors_cache["alpha13"]
                else:
                    if "basic8" not in factors_cache:
                        logger.info("Computing basic8 factors...")
                        factors_cache["basic8"] = compute_factors(pivot)
                    factors = factors_cache["basic8"]
                out[sn] = generate_ml_signals(pivot, sn, sim_dates, factors)
            except Exception as e:
                logger.error("ML signals failed for %s: %s", sn, e)
                out[sn] = {}
    return out


def latest_signals_for_date(all_sigs: dict[str, dict], date_str: str) -> dict[str, list]:
    return {sn: [s for s in sigs.get(date_str, [])] for sn, sigs in all_sigs.items()}
