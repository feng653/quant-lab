"""
Round-trip analysis — FIFO matching of buys and sells into round trips.

Turns raw fills into meaningful trades: entry → exit, realized P&L, holding
days. Open (unclosed) positions are listed separately.
"""

from __future__ import annotations

from collections import deque

import pandas as pd

from services import trade_db


def compute_roundtrips(strategy: str | None = None, mode: str = "equal") -> tuple[pd.DataFrame, pd.DataFrame]:
    """FIFO match. Returns (closed_roundtrips_df, open_positions_df)."""
    tr = trade_db.get_trades(strategy=strategy, mode=mode, limit=1000000)
    if tr.empty:
        return pd.DataFrame(), pd.DataFrame()
    tr = tr.sort_values(["date", "id"])

    open_q: dict[tuple, deque] = {}
    closed: list[dict] = []

    for _, t in tr.iterrows():
        key = (t["strategy"], t["code"])
        q = open_q.setdefault(key, deque())
        if t["action"] == "buy":
            q.append({"date": t["date"], "shares": t["shares"], "price": t["price"],
                      "value": t["value"], "cost": t["commission"] + t["slippage_cost"]})
        else:
            remaining = t["shares"]
            sell_value_total, sell_cost_total = t["value"], t["commission"] + t["stamp_duty"] + t["slippage_cost"]
            while remaining > 0 and q:
                lot = q[0]
                take = min(remaining, lot["shares"])
                ratio = take / t["shares"]
                buy_val = lot["price"] * take
                sell_val = t["price"] * take
                pnl = sell_val - buy_val - lot["cost"] * (take / lot["shares"]) - sell_cost_total * ratio
                hold_days = (pd.Timestamp(t["date"]) - pd.Timestamp(lot["date"])).days
                closed.append({"strategy": t["strategy"], "code": t["code"],
                               "buy_date": lot["date"], "sell_date": t["date"],
                               "shares": int(take), "buy_price": lot["price"], "sell_price": t["price"],
                               "pnl": round(pnl, 2), "pnl_pct": round((sell_val / buy_val - 1) * 100, 2) if buy_val else 0,
                               "hold_days": hold_days})
                lot["shares"] -= take
                remaining -= take
                if lot["shares"] <= 0:
                    q.popleft()
            # sell without open lot (short leg artifacts) → ignore for round trips

    open_pos = [{"strategy": k[0], "code": k[1], "shares": int(sum(l["shares"] for l in q)),
                 "avg_price": round(sum(l["price"] * l["shares"] for l in q) / max(sum(l["shares"] for l in q), 1), 3),
                 "first_buy": min(l["date"] for l in q)}
                for k, q in open_q.items() if q]

    return pd.DataFrame(closed), pd.DataFrame(open_pos)


def summary_stats(strategy: str | None = None, mode: str = "equal") -> dict:
    tr = trade_db.get_trades(strategy=strategy, mode=mode, limit=1000000)
    if tr.empty:
        return {}
    closed, open_pos = compute_roundtrips(strategy, mode)
    buys = tr[tr["action"] == "buy"]
    sells = tr[tr["action"] == "sell"]
    out = {"n_trades": len(tr), "n_buys": len(buys), "n_sells": len(sells),
           "turnover": float(tr["value"].sum()),
           "total_cost": float((tr["commission"] + tr["stamp_duty"] + tr["slippage_cost"]).sum()),
           "n_open": len(open_pos)}
    if not closed.empty:
        wins = closed[closed["pnl"] > 0]
        out.update({"n_closed": len(closed),
                    "win_rate": round(len(wins) / len(closed) * 100, 1),
                    "avg_pnl": round(float(closed["pnl"].mean()), 2),
                    "avg_hold_days": round(float(closed["hold_days"].mean()), 1),
                    "realized_pnl": round(float(closed["pnl"].sum()), 2),
                    "best": round(float(closed["pnl"].max()), 2),
                    "worst": round(float(closed["pnl"].min()), 2)})
    return out


def group_by_date(mode: str = "equal") -> pd.DataFrame:
    tr = trade_db.get_trades(mode=mode, limit=1000000)
    if tr.empty:
        return pd.DataFrame()
    tr["buy_amt"] = tr.apply(lambda r: r["value"] if r["action"] == "buy" else 0, axis=1)
    tr["sell_amt"] = tr.apply(lambda r: r["value"] if r["action"] == "sell" else 0, axis=1)
    g = tr.groupby("date").agg(n=("id", "count"), buy_amt=("buy_amt", "sum"), sell_amt=("sell_amt", "sum"),
                               cost=("commission", "sum"))
    g["cost"] = tr.groupby("date").apply(lambda x: (x["commission"] + x["stamp_duty"] + x["slippage_cost"]).sum())
    return g.round(0).reset_index().sort_values("date", ascending=False)


def group_by_strategy(mode: str = "equal") -> pd.DataFrame:
    tr = trade_db.get_trades(mode=mode, limit=1000000)
    if tr.empty:
        return pd.DataFrame()
    g = tr.groupby("strategy").agg(n=("id", "count"), turnover=("value", "sum"))
    g["cost"] = tr.groupby("strategy").apply(lambda x: (x["commission"] + x["stamp_duty"] + x["slippage_cost"]).sum())
    g["n_codes"] = tr.groupby("strategy")["code"].nunique()
    return g.round(0).reset_index()


def group_by_code(strategy: str | None = None, mode: str = "equal", top: int = 50) -> pd.DataFrame:
    tr = trade_db.get_trades(strategy=strategy, mode=mode, limit=1000000)
    if tr.empty:
        return pd.DataFrame()
    g = tr.groupby("code").agg(n=("id", "count"), turnover=("value", "sum"))
    g["n_strats"] = tr.groupby("code")["strategy"].nunique()
    return g.round(0).reset_index().sort_values("turnover", ascending=False).head(top)
