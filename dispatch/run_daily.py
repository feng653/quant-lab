"""
run_daily.py — single daily entry point.

One simulation run feeds both emails (recommendation + performance),
then pushes a short WeChat summary if PushPlus is configured.

Usage:  python dispatch/run_daily.py
Task Scheduler: daily 15:35 (after close).
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main(force: bool = False) -> None:
    from services.data_service import is_trading_day
    if not force and not is_trading_day():
        logger.info("Skip: not a trading day (use --force to override)")
        return

    t0 = time.time()
    logger.info("═══ 1/4 Simulation ═══")
    from services.sim_runner import run_simulation
    ctx = run_simulation()

    logger.info("═══ 2/4 Recommendation email ═══")
    from daily_recommend import build_recommend_html, save_mail
    from notify.email_qq import send_daily_report
    html_rec = build_recommend_html(ctx)
    p1 = save_mail(html_rec, "recommend")
    ok1 = send_daily_report(
        f"[量化推荐] {datetime.now().strftime('%Y-%m-%d')} 10策略操作建议 ({ctx['market']['label']})", html_rec)
    logger.info("Recommend: saved %s, email %s", p1, "OK" if ok1 else "FAIL")

    logger.info("═══ 3/4 Performance email ═══")
    from ai_commentary import generate_commentary
    from daily_performance import build_ai_context, build_performance_html
    ai_text = generate_commentary(build_ai_context(ctx))
    html_perf = build_performance_html(ctx, ai_text)
    p2 = save_mail(html_perf, "performance")
    ok2 = send_daily_report(
        f"[量化日报] {datetime.now().strftime('%Y-%m-%d')} 10策略双模式模拟 (起始{ctx['sim_start']})", html_perf)
    logger.info("Performance: saved %s, email %s", p2, "OK" if ok2 else "FAIL")

    logger.info("═══ 4/4 WeCom push ═══")
    from notify.wechat_wecom import build_daily_wecom, send_wecom_markdown
    send_wecom_markdown(build_daily_wecom(ctx))

    logger.info("═══ Done in %.1fs ═══", time.time() - t0)


if __name__ == "__main__":
    main(force="--force" in sys.argv)
