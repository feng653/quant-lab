"""Assistant blueprint — natural-language data & task management chat."""

from __future__ import annotations

from flask import Blueprint, redirect, request

bp = Blueprint("assistant", __name__)


@bp.route("/assistant", methods=["GET", "POST"])
def assistant_page():
    from services import ai_assistant
    from web.app import page

    if request.method == "POST":
        if request.form.get("clear"):
            ai_assistant.clear_history()
            return redirect("/assistant")
        msg = request.form.get("msg", "")
        if msg.strip():
            ai_assistant.chat(msg)
        return redirect("/assistant")

    history = ai_assistant.get_history()
    bubbles = ""
    for h in reversed(history[-20:]):
        if h["role"] == "user":
            bubbles += (f"<div style='text-align:right;margin:8px 0'><span style='background:#4472C4;color:#fff;"
                        f"padding:8px 12px;border-radius:12px;display:inline-block;max-width:70%;text-align:left'>"
                        f"{h['text']}</span></div>")
        else:
            text = h["text"].replace("\n", "<br>")
            bubbles += (f"<div style='margin:8px 0'><span style='background:#fff;border:1px solid #e0e0e0;"
                        f"padding:8px 12px;border-radius:12px;display:inline-block;max-width:75%;text-align:left;font-size:13px'>"
                        f"🤖 {text}</span></div>")
    if not bubbles:
        bubbles = ("<div style='color:#999;text-align:center;padding:30px'>"
                   "试试：「拉取最新数据」「查看数据状态」「MACD最近成交」「现在跑每日任务」</div>")

    body = f"""
<div class='card'><h3>🤖 AI 数据管理助手</h3>
<p style='color:#666;font-size:12px'>自然语言管理数据与任务。动作经 DeepSeek 意图识别后在白名单内执行，不会执行任意代码。</p>
<div style='max-height:55vh;overflow-y:auto;padding:8px;background:#f8f9fa;border-radius:8px'>{bubbles}</div>
<form method='post' style='display:flex;gap:8px;margin-top:10px'>
<input name='msg' placeholder='输入指令，如：拉取最新数据 / 查看MACD的成交记录 / 数据有缺失吗' style='flex:1;padding:8px 12px' autocomplete='off'>
<button type='submit'>发送</button>
<button type='submit' name='clear' value='1' style='background:#999'>清空</button>
</form></div>"""
    return page("AI助手", body, "/assistant")
