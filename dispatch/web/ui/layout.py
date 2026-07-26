"""
UI layout — page shell, nav, CSS, small HTML helpers.

Extracted verbatim from ``web/app.py`` so blueprints can import the page shell
without importing the app module. That circular dependency is why every
blueprint previously did a function-local ``from web.app import page``; they can
now import from here at module level.

Styling is unchanged from the original app.py.
"""

from __future__ import annotations

BASE_CSS = """
:root{--bg:#f0f2f5;--card:#fff;--ink:#1a1a2e;--sub:#666;--line:#e8e8e8;
--blue:#4472C4;--green:#2e7d32;--red:#c62828;--radius:10px;--shadow:0 2px 8px rgba(0,0,0,0.08)}
*{box-sizing:border-box}
body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;margin:0;background:var(--bg);color:var(--ink)}
nav{background:var(--ink);color:#fff;padding:12px 24px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
nav a{color:#cfd8dc;text-decoration:none;font-size:14px;padding:4px 6px;border-radius:6px}
nav a:hover{color:#fff;background:rgba(255,255,255,0.08)}
nav .brand{font-weight:bold;font-size:16px;color:#ffd54f;margin-right:8px}
.wrap{max-width:1280px;margin:20px auto;padding:0 16px}
.card{background:var(--card);border-radius:var(--radius);padding:16px;margin:12px 0;box-shadow:var(--shadow)}
.card h3{margin-top:0}
table{border-collapse:collapse;width:100%}
th{background:var(--blue);color:#fff;padding:8px 6px;font-size:12px}
td{padding:6px;text-align:center;border-bottom:1px solid var(--line);font-size:12px}
.green{color:var(--green);font-weight:bold}.red{color:var(--red);font-weight:bold}
.grid{display:flex;flex-wrap:wrap;gap:12px}
.scard{flex:1;min-width:200px;background:var(--card);border-radius:var(--radius);padding:14px;box-shadow:var(--shadow)}
.scard h3{margin:0 0 6px 0;font-size:15px}
.scard .big{font-size:22px;font-weight:bold}
.scard .sub{color:var(--sub);font-size:11px;line-height:1.7}
.navcard{flex:1;min-width:180px;max-width:240px;background:var(--card);border-radius:var(--radius);padding:18px;box-shadow:var(--shadow);text-align:center;text-decoration:none;color:var(--ink);transition:transform .15s}
.navcard:hover{transform:translateY(-3px);box-shadow:0 6px 16px rgba(0,0,0,0.12)}
.navcard .ico{font-size:30px}.navcard .t{font-weight:bold;margin:8px 0 4px}.navcard .d{color:var(--sub);font-size:11px;line-height:1.6}
form.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:8px 0}
select,input{padding:5px 8px;border:1px solid #ccc;border-radius:6px;font-size:13px}
button{padding:6px 16px;background:var(--blue);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px}
button:hover{filter:brightness(1.1)}
img{max-width:100%;border-radius:6px}
iframe.report{border:1px solid var(--line);border-radius:var(--radius);width:100%;height:75vh;background:#fff}
.badge-off{color:#999;background:#eee;border-radius:4px;padding:1px 6px;font-size:10px}
/* research pages */
.mono{font-family:Consolas,'Courier New',monospace;font-size:11px}
table.sortable th{cursor:pointer;user-select:none}
table.sortable th:hover{filter:brightness(1.15)}
table.lb td{white-space:nowrap}
table.lb tr:hover{background:#f5f8ff}
.pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;background:#eef2ff;color:#3949ab}
.dim{color:var(--sub)}
.right{text-align:right}
.kv{display:grid;grid-template-columns:150px 1fr;gap:4px 10px;font-size:12px}
.kv .k{color:var(--sub)}
.hm td{font-size:11px;padding:4px}
.warn{background:#fff8e1;border-left:3px solid #ffa000;padding:8px 12px;border-radius:6px;font-size:12px;margin:8px 0}
"""

NAV_ITEMS = [("/", "🏠 主页"), ("/overview", "📊 总览"), ("/strategies", "🎛️ 策略管理"),
             ("/research", "🔬 研究"), ("/lab", "🧪 实验室"), ("/assistant", "🤖 AI助手"),
             ("/trades", "📝 成交记录"), ("/compare", "📈 对比"), ("/reports", "📁 报告"),
             ("/jobs", "🧵 任务"), ("/scheduler", "⏰ 调度")]


def nav(active: str = "") -> str:
    links = "".join(f"<a href='{u}' style='{'color:#fff;background:rgba(255,255,255,0.12)' if u==active else ''}'>{t}</a>"
                    for u, t in NAV_ITEMS)
    return f"<nav><span class='brand'>📊 quant-lab</span>{links}</nav>"


def page(title: str, body: str, active: str = "") -> str:
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title} - quant-lab</title>"
            f"<style>{BASE_CSS}</style></head><body>{nav(active)}<div class='wrap'>{body}</div></body></html>")


# ───────────────────────── small helpers ─────────────────────────

def cls(v: float | None, invert: bool = False) -> str:
    """'green'/'red' by sign; invert for metrics where negative is good."""
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if f == 0:
        return ""
    good = f < 0 if invert else f > 0
    return "green" if good else "red"


def num(v, nd: int = 2, suffix: str = "", dash: str = "—") -> str:
    """Format a number, or a dash when missing."""
    if v is None or v == "":
        return f"<span class='dim'>{dash}</span>"
    try:
        return f"{float(v):,.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def signed(v, nd: int = 2, suffix: str = "%", invert: bool = False) -> str:
    """Number wrapped in a green/red span."""
    if v is None or v == "":
        return "<span class='dim'>—</span>"
    return f"<span class='{cls(v, invert)}'>{num(v, nd, suffix)}</span>"


def card(title: str, body: str, extra: str = "") -> str:
    head = f"<h3>{title}{extra}</h3>" if title else ""
    return f"<div class='card'>{head}{body}</div>"


def scard(title: str, big: str, sub: str = "") -> str:
    return (f"<div class='scard'><h3>{title}</h3><div class='big'>{big}</div>"
            f"<div class='sub'>{sub}</div></div>")


def table(headers: list[str], rows: list[list[str]], *,
          sortable: bool = False, css_class: str = "") -> str:
    """Static HTML table. sortable=True adds client-side column sorting."""
    klass = " ".join(x for x in (css_class, "sortable" if sortable else "") if x)
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    html = (f"<table class='{klass}'><thead><tr>{th}</tr></thead>"
            f"<tbody>{trs}</tbody></table>")
    return html + (SORT_JS if sortable else "")


SORT_JS = """
<script>
document.querySelectorAll('table.sortable').forEach(function(t){
  t.querySelectorAll('th').forEach(function(th,i){
    th.addEventListener('click',function(){
      var tb=t.tBodies[0], rows=Array.prototype.slice.call(tb.rows);
      var asc=!(th.dataset.asc==='1'); th.dataset.asc=asc?'1':'0';
      var val=function(td){var s=(td.innerText||'').replace(/[,%\\s]/g,'');
        var f=parseFloat(s); return isNaN(f)?(td.innerText||'').toLowerCase():f;};
      rows.sort(function(a,b){
        var x=val(a.cells[i]), y=val(b.cells[i]);
        // blanks always sink so incomplete rows never top the board
        var xb=(x===''||x==='—'), yb=(y===''||y==='—');
        if(xb&&!yb) return 1; if(yb&&!xb) return -1;
        if(typeof x==='number'&&typeof y==='number') return asc?x-y:y-x;
        return asc?String(x).localeCompare(String(y)):String(y).localeCompare(String(x));
      });
      rows.forEach(function(r){tb.appendChild(r);});
    });
  });
});
</script>
"""
