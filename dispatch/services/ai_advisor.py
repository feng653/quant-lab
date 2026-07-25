"""
AI parameter advisor — DeepSeek-recommended strategy params.

For a strategy: feeds its description, param schema, and recent simulated
performance to DeepSeek, asks for a JSON param recommendation + rationale.
Output is validated against the schema (types + min/max clamp) before being
applicable. Advice is cached in dispatch/state/ai_param_advice.json.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from core.strategies.registry import REGISTRY, get_params, get_spec, set_params

logger = logging.getLogger(__name__)

ADVICE_FILE = Path(__file__).resolve().parent.parent / "state" / "ai_param_advice.json"


def _load_cache() -> dict:
    if ADVICE_FILE.exists():
        try:
            return json.loads(ADVICE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(c: dict) -> None:
    ADVICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADVICE_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cached_advice(key: str) -> dict | None:
    return _load_cache().get(key)


def _validate_params(key: str, raw: dict) -> dict:
    """Clamp AI-returned params into schema types and ranges. Unknown keys dropped."""
    spec = get_spec(key)
    if spec is None:
        return {}
    out = {}
    for pname, schema in spec.param_schema.items():
        if pname not in raw:
            continue
        try:
            v = raw[pname]
            v = int(v) if schema.get("type") == "int" else float(v)
        except (TypeError, ValueError):
            continue
        if schema.get("min") is not None:
            v = max(type(v)(schema["min"]), v)
        if schema.get("max") is not None:
            v = min(type(v)(schema["max"]), v)
        out[pname] = v
    return out


def generate_param_advice(key: str) -> dict:
    """Call DeepSeek for a param recommendation. Returns {params, rationale, current}."""
    spec = get_spec(key)
    if spec is None:
        raise ValueError(f"未知策略 {key}")

    # recent performance context
    perf_txt = "暂无模拟表现数据"
    try:
        from services.sim_runner import load_state
        st = load_state().get("strategies", {}).get(key)
        if st and "equal" in st:
            e = st["equal"]
            perf_txt = (f"近期模拟(等权): 累计{e.get('total_return',0):+.2f}%, Sharpe {e.get('sharpe',0):+.3f}, "
                        f"MaxDD {e.get('max_dd',0):+.1f}%, 波动率 {e.get('volatility',0):.1f}%, "
                        f"成本 {e.get('costs',{}).get('total',0):,.0f}元")
    except Exception:
        pass

    schema_txt = "\n".join(
        f"  {p}: type={s.get('type')}, default={s.get('default')}, range=[{s.get('min')},{s.get('max')}], {s.get('desc','')}"
        for p, s in spec.param_schema.items())
    current = get_params(key)

    prompt = f"""你是量化策略调参专家。有一个A股日线交易策略需要优化参数。

策略: {spec.label} ({key})
类别: {spec.category}
说明: {spec.desc}
执行: 每{spec.rebalance_days}个交易日再平衡, 持仓上限{spec.max_positions}只

当前参数: {json.dumps(current)}
{perf_txt}

可调参数schema:
{schema_txt}

请给出推荐参数组合。要求:
1. 只输出一个JSON对象, 格式: {{"params": {{"参数名": 值}}, "rationale": "150字以内的中文理由"}}
2. 参数值必须在schema的range内, 类型正确
3. 考虑A股特征(T+1, 涨跌停, 高波动)和当前熊市高波动环境
4. 不要输出JSON以外的任何内容"""

    from ai_commentary import _get_api_key, _load_env
    import os
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    env = _load_env()
    base = (env.get("LLM_BASE_URL") or os.environ.get("LLM_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
    model = env.get("LLM_MODEL") or os.environ.get("LLM_MODEL") or "deepseek-v4-flash"

    import requests
    r = requests.post(f"{base}/chat/completions",
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                      json={"model": model, "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 500, "temperature": 0.3},
                      timeout=60)
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"].strip()

    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError(f"AI 返回非JSON: {text[:200]}")
    data = json.loads(m.group(0))
    params = _validate_params(key, data.get("params", {}))
    if not params:
        raise RuntimeError("AI 未返回有效参数")
    result = {"params": params, "rationale": data.get("rationale", ""),
              "current": current, "key": key}
    cache = _load_cache()
    from datetime import datetime
    result["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cache[key] = result
    _save_cache(cache)
    return result


def apply_advice(key: str) -> dict:
    """Apply cached advice to strategy config."""
    advice = get_cached_advice(key)
    if not advice:
        raise RuntimeError("无缓存建议, 请先生成")
    set_params(key, advice["params"])
    return advice["params"]
