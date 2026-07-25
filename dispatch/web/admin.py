"""Admin blueprint — strategy management, scheduler, job center."""

from __future__ import annotations

from flask import Blueprint, jsonify, redirect, request

from core.strategies.registry import (REGISTRY, get_params, is_enabled, rescan,
                                      scan_strategies, set_enabled, set_params)

bp = Blueprint("admin", __name__)


# ────────────────────────── strategy management ──────────────────────────

def _param_input(key: str, pname: str, schema: dict, value) -> str:
    t = schema.get("type", "float")
    desc = schema.get("desc", "")
    step = "1" if t == "int" else "any"
    return (f"<td style='font-size:11px;color:#666'>{desc}</td>"
            f"<td><input name='{pname}' value='{value}' type='number' step='{step}' "
            f"min='{schema.get('min','')}' max='{schema.get('max','')}' style='width:90px'></td>")


@bp.route("/strategies")
def strategies_page():
    from web.app import page
    scan_strategies()
    flash = request.args.get("msg", "")
    flash_html = f"<div class='card' style='background:#e8f5e9;color:#2e7d32'>{flash}</div>" if flash else ""

    cards = ""
    for k, spec in sorted(REGISTRY.items(), key=lambda x: (x[1].category, x[0])):
        enabled = is_enabled(k)
        params = get_params(k)
        badge = "<span style='color:#2e7d32;font-weight:bold'>● 启用</span>" if enabled else "<span style='color:#999'>○ 停用</span>"
        ml_badge = f"<span style='background:#e3f2fd;color:#1565c0;padding:2px 6px;border-radius:4px;font-size:10px'>ML:{spec.ml_model_type}</span>" if spec.ml_model_type else ""
        param_rows = ""
        if spec.param_schema:
            for pname, schema in spec.param_schema.items():
                param_rows += f"<tr>{_param_input(k, pname, schema, params.get(pname, schema.get('default')))}</tr>"
        else:
            param_rows = "<tr><td colspan='2' style='color:#999;font-size:11px'>无可调参数</td></tr>"
        note = f"<div style='color:#e65100;font-size:11px;margin-top:4px'>⚠️ {spec.note}</div>" if spec.note else ""
        advice_btn = (f"<button formaction='/strategies/ai_advice/{k}' formmethod='post' style='background:#6a1b9a'>🤖 AI推荐参数</button>")
        cards += f"""
<div class='scard' style='min-width:340px;{'' if enabled else 'opacity:0.65'}'>
<form method='post' action='/strategies/save/{k}' style='margin:0'>
<h3>{spec.label} <small style='color:#666'>{k}</small> {badge}</h3>
<div style='color:#666;font-size:12px;margin:4px 0'>{spec.category} {ml_badge} | 再平衡 {spec.rebalance_days}日 | 持仓上限 {spec.max_positions}</div>
<div style='color:#888;font-size:11px;margin-bottom:6px'>{spec.desc}</div>{note}
<table style='margin:6px 0'>{param_rows}</table>
<div style='display:flex;gap:8px;margin-top:6px'>
<button type='submit' style='background:#2e7d32'>保存参数</button>
<button formaction='/strategies/toggle/{k}' formmethod='post' style='background:{'#c62828' if enabled else '#2e7d32'}'>{'停用' if enabled else '启用'}</button>
{advice_btn if spec.param_schema else ''}
</div></form>
<div id='advice_{k}' style='margin-top:8px'></div>
</div>"""

    body = f"""
{flash_html}
<div class='card'><h3>🎛️ 策略管理（自动检测自 core/strategies/）</h3>
<p style='color:#666;font-size:12px'>共 {len(REGISTRY)} 个策略。停用策略保留历史数据但不再参与每日模拟与邮件。
新增策略：将带 @register_strategy 装饰器的 .py 文件放入 core/strategies/ 对应目录，点击"重新扫描"。</p>
<form method='post' action='/strategies/rescan' style='display:inline'><button>🔄 重新扫描策略库</button></form></div>
<div class='grid'>{cards}</div>"""
    return page("策略管理", body)


@bp.route("/strategies/toggle/<key>", methods=["POST"])
def strategy_toggle(key: str):
    set_enabled(key, not is_enabled(key))
    return redirect(f"/strategies?msg={key} 已{'启用' if is_enabled(key) else '停用'}，下次模拟生效")


@bp.route("/strategies/save/<key>", methods=["POST"])
def strategy_save(key: str):
    spec = REGISTRY.get(key)
    if spec is None:
        return redirect("/strategies?msg=策略不存在")
    params = {}
    for pname, schema in spec.param_schema.items():
        raw = request.form.get(pname)
        if raw is None or raw == "":
            continue
        try:
            v = int(raw) if schema.get("type") == "int" else float(raw)
            if schema.get("min") is not None:
                v = max(type(v)(schema["min"]), v)
            if schema.get("max") is not None:
                v = min(type(v)(schema["max"]), v)
            params[pname] = v
        except ValueError:
            pass
    set_params(key, params)
    return redirect(f"/strategies?msg={key} 参数已保存，下次模拟生效")


@bp.route("/strategies/rescan", methods=["POST"])
def strategy_rescan():
    reg = rescan()
    return redirect(f"/strategies?msg=扫描完成，发现 {len(reg)} 个策略")


@bp.route("/strategies/ai_advice/<key>", methods=["POST"])
def strategy_ai_advice(key: str):
    from services import job_runner

    def work(job):
        from services.ai_advisor import generate_param_advice
        return generate_param_advice(key)

    job = job_runner.submit("ai_advice", f"AI参数建议 {key}", work)
    return redirect(f"/jobs/{job.id}")


# ────────────────────────── scheduler ──────────────────────────

@bp.route("/scheduler")
def scheduler_page():
    from services.scheduler import scheduler_status
    from web.app import page
    st = scheduler_status()
    job_rows = "".join(f"<tr><td>{j['name']}</td><td>{j['id']}</td><td>{j['next_run']}</td></tr>"
                       for j in st["jobs"]) or "<tr><td colspan='3'>调度器未运行</td></tr>"
    body = f"""
<div class='card'><h3>⏰ 调度器状态</h3>
<table>
<tr><th>运行中</th><td>{'🟢 是' if st['running'] else '🔴 否（web 服务启动时自动开启）'}</td></tr>
<tr><th>启动时间</th><td>{st['started_at']}</td></tr>
<tr><th>上次每日pipeline</th><td>{st['last_daily']} → {st['last_daily_result']}</td></tr>
<tr><th>上次周清理</th><td>{st['last_cleanup']}</td></tr>
<tr><th>今日已运行</th><td>{'是' if st['already_ran_today'] else '否'}</td></tr>
</table></div>
<div class='card'><h3>定时任务</h3>
<table><tr><th>名称</th><th>ID</th><th>下次运行</th></tr>{job_rows}</table>
<form method='post' action='/scheduler/run_daily' style='margin-top:10px'>
<button style='background:#e65100'>▶️ 立即运行每日pipeline（模拟+双邮件+微信）</button></form></div>"""
    return page("调度中心", body)


@bp.route("/scheduler/run_daily", methods=["POST"])
def scheduler_run_daily():
    from services import job_runner

    def work(job):
        from services.scheduler import daily_pipeline_job
        return daily_pipeline_job(force=True)

    job = job_runner.submit("daily_pipeline", "手动触发每日pipeline", work)
    return redirect(f"/jobs/{job.id}")


# ────────────────────────── jobs ──────────────────────────

@bp.route("/jobs")
def jobs_page():
    from services import job_runner
    from web.app import page
    rows = "".join(
        f"<tr><td><a href='/jobs/{j.id}'>{j.id}</a></td><td>{j.type}</td><td>{j.title}</td>"
        f"<td>{'🟢运行中' if j.status=='running' else ('✅完成' if j.status=='done' else ('❌失败' if j.status=='failed' else '⏳等待'))}</td>"
        f"<td>{j.created}</td><td>{j.finished or '-'}</td></tr>"
        for j in job_runner.list_jobs()) or "<tr><td colspan='6'>暂无任务</td></tr>"
    body = f"""<div class='card'><h3>🧵 后台任务中心</h3>
<table><tr><th>ID</th><th>类型</th><th>标题</th><th>状态</th><th>创建</th><th>完成</th></tr>{rows}</table></div>
<script>setTimeout(()=>location.reload(), 5000)</script>"""
    return page("任务中心", body)


@bp.route("/jobs/<job_id>")
def job_detail(job_id: str):
    from services import job_runner
    from web.app import page
    j = job_runner.get_job(job_id)
    if j is None:
        return page("任务不存在", "<div class='card'>任务不存在或已被清理</div>"), 404
    status_txt = {"running": "🟢 运行中", "done": "✅ 完成", "failed": "❌ 失败", "pending": "⏳ 等待"}.get(j.status, j.status)
    result_html = ""
    if j.status == "done" and isinstance(j.result, dict) and j.result.get("html"):
        result_html = f"<div class='card'><h3>结果</h3>{j.result['html']}</div>"
    elif j.status == "done" and j.result is not None:
        result_html = f"<div class='card'><h3>结果</h3><pre style='font-size:12px;white-space:pre-wrap'>{j.result}</pre></div>"
    err_html = f"<div class='card' style='background:#fce4ec'><h3>错误</h3><pre style='font-size:11px'>{j.error}</pre></div>" if j.error else ""
    log = "\n".join(j.log_lines[-120:]) or "(暂无日志)"
    auto = "<script>setTimeout(()=>location.reload(), 3000)</script>" if j.status in ("running", "pending") else ""
    body = f"""
<div class='card'><h3>任务 {j.id} — {j.title}</h3>
<p>类型: {j.type} | 状态: {status_txt} | 创建: {j.created} | 完成: {j.finished or '-'}</p></div>
{result_html}{err_html}
<div class='card'><h3>日志</h3><pre style='font-size:11px;max-height:400px;overflow:auto;background:#f8f9fa;padding:10px;border-radius:6px'>{log}</pre></div>
{auto}"""
    return page(f"任务 {j.id}", body)
