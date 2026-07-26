"""Lab blueprint — data management, ML training, arbitrary-range backtests."""

from __future__ import annotations

from flask import Blueprint, redirect, request

from core.strategies.registry import REGISTRY, get_params, scan_strategies

bp = Blueprint("lab", __name__)


# ────────────────────────── data panel ──────────────────────────

def _data_status() -> dict:
    from services.data_service import load_pool, pool_file
    df = load_pool("csi500")
    if df.empty:
        return {"rows": 0}
    f = pool_file("csi500")
    return {"rows": len(df), "codes": df["code"].nunique(),
            "start": df["date"].min().strftime("%Y-%m-%d"),
            "end": df["date"].max().strftime("%Y-%m-%d"),
            "size_mb": round(f.stat().st_size / 1024 / 1024, 1) if f else 0}


@bp.route("/lab")
def lab_page():
    from web.ui.layout import page
    scan_strategies()
    ds = _data_status()

    ml_rows = ""
    for k, spec in REGISTRY.items():
        if not spec.ml_model_type:
            continue
        p = get_params(k)
        ml_rows += (f"<tr><td><b>{spec.label}</b></td><td>{spec.ml_model_type}</td>"
                    f"<td>每{p.get('retrain_every',21)}日</td>"
                    f"<td>{'top_k='+str(p['top_k']) if 'top_k' in p else 'top '+str(int(p.get('top_pct',0.1)*100))+'%'}</td>"
                    f"<td>{p.get('horizon',20)}日</td>"
                    f"<td><form method='post' action='/lab/train/{k}' style='display:inline'>"
                    f"<button style='padding:4px 12px;font-size:12px'>一键训练</button></form></td></tr>")

    strat_checks = "".join(
        f"<label style='font-size:13px'><input type='checkbox' name='s' value='{k}' checked> {s.label}</label>"
        for k, s in REGISTRY.items())

    body = f"""
<div class='card'><h3>💾 数据面板</h3>
<table>
<tr><th>股票数</th><td>{ds.get('codes','-')}</td><th>总行数</th><td>{ds.get('rows','-'):,}</td></tr>
<tr><th>数据范围</th><td>{ds.get('start','-')} ~ {ds.get('end','-')}</td><th>缓存大小</th><td>{ds.get('size_mb','-')} MB</td></tr>
</table>
<form method='post' action='/lab/update_data' style='display:inline'><button>📥 拉取最新数据</button></form>
<span style='color:#666;font-size:12px;margin-left:10px'>增量补齐到最近交易日（每日pipeline也会自动执行）</span></div>

<div class='card'><h3>🧠 训练面板（ML 策略）</h3>
<p style='color:#666;font-size:12px'>一键训练 = 对当前模拟窗口执行 walk-forward 重训（已缓存的重训点秒过，只训练缺失部分）。结果与日志见任务中心。</p>
<table><tr><th>策略</th><th>模型</th><th>重训</th><th>选股</th><th>标签</th><th>操作</th></tr>{ml_rows}</table></div>

<div class='card'><h3>⏪ 回测面板</h3>
<form method='post' action='/lab/backtest'>
<div class='filters'>{strat_checks}</div>
<div class='filters'>
起始日期 <input type='date' name='start' value='2024-01-02'> 
结束日期 <input type='date' name='end' value=''>
模式 <select name='mode'><option value='both'>等权+自适应</option><option value='equal'>仅等权</option></select>
<button type='submit'>🚀 开始回测</button></div>
<p style='color:#e65100;font-size:11px'>⚠️ 技术策略秒回；LGB/XGB 每年约 12 次重训（秒级）；LSTM/TF 每次重训约 40 秒，全历史需数十分钟，任务在后台执行可离开本页。</p>
</form></div>"""
    return page("实验室", body)


@bp.route("/lab/update_data", methods=["POST"])
def lab_update_data():
    from services import job_runner

    def work(job):
        from services.data_service import auto_update
        _, latest, added = auto_update("csi500")
        return f"数据已更新到 {latest}，新增 {added} 个交易日"

    job = job_runner.submit("data_update", "拉取最新数据", work)
    return redirect(f"/jobs/{job.id}")


@bp.route("/lab/train/<key>", methods=["POST"])
def lab_train(key: str):
    from services import job_runner

    def work(job):
        import pandas as pd
        from services.data_service import load_pool
        from services.signal_service import compute_factors, compute_factors_alpha13, generate_ml_signals
        from services.sim_runner import get_sim_start
        from core.strategies.registry import get_spec
        spec = get_spec(key)
        df = load_pool("csi500")
        pivot = df.pivot(index="date", columns="code", values="close")
        sim_start = get_sim_start()
        sim_dates = [d for d in pivot.index if d >= pd.Timestamp(sim_start)]
        factors = compute_factors_alpha13(df) if spec.feature_set == "alpha13" else compute_factors(pivot)
        sigs = generate_ml_signals(pivot, key, sim_dates, factors)
        latest = str(sim_dates[-1].date())
        buys = [s["code"] for s in sigs.get(latest, []) if s["action"] == "buy"]
        return {"html": f"<p>最新重训选股（{latest}）: <b>{', '.join(buys) or '无'}</b></p>"
                        f"<p style='color:#666'>信号天数: {len(sigs)}。详细日志见上方。</p>"}

    job = job_runner.submit("train", f"训练 {key}", work)
    return redirect(f"/jobs/{job.id}")


@bp.route("/lab/backtest", methods=["POST"])
def lab_backtest():
    from services import job_runner
    strategies = request.form.getlist("s")
    start = request.form.get("start", "2024-01-02")
    end = request.form.get("end") or None
    mode_choice = request.form.get("mode", "both")    # captured before bg thread
    if not strategies:
        return redirect("/lab")

    def work(job):
        from services.backtest_service import run_backtest
        bt = run_backtest(strategies, start, end)
        rows = ""
        for sn, e in bt["results"].items():
            modes = ("equal",) if mode_choice == "equal" else ("equal", "adaptive")
            for mode in modes:
                m = e[mode]
                rows += (f"<tr><td>{e['label']}</td><td>{'等权' if mode=='equal' else '自适应'}</td>"
                         f"<td>{m['total_return']:+.2f}%</td><td>{m['annual_return']:+.2f}%</td>"
                         f"<td>{m['sharpe']:+.3f}</td><td>{m['max_dd']:+.1f}%</td>"
                         f"<td>{m['costs']['total']:,.0f}</td><td>{m['n_trades']}</td></tr>")
        html = (f"<p>区间 {bt['start']} ~ {bt['end']}（{bt['n_days']} 交易日）| 基准中证500: <b>{bt['bench_ret']:+.2f}%</b></p>"
                f"<table><tr><th>策略</th><th>模式</th><th>累计%</th><th>年化%</th><th>Sharpe</th>"
                f"<th>MaxDD</th><th>成本(元)</th><th>成交笔数</th></tr>{rows}</table>")
        return {"html": html, "backtest": bt}

    job = job_runner.submit("backtest", f"回测 {len(strategies)} 策略 {start}~{end or '今'}", work)
    return redirect(f"/jobs/{job.id}")
