from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app import create_app
from app.services.telegram_dispatcher import (
    send_morning_briefings,
    send_second_briefings,
    send_breaking_news,
)
from app.services.news_dispatcher import send_daily_news
from app.services.news_digest_service import prepare_digest_articles
from app.services.telegram_dedup import purge_old_dispatch_logs

app = create_app()


def build_midday_brief() -> str:
    return """
📍 Midday Brief

Le marché reste en observation sur les zones clés de liquidité.
Les indices US gardent une structure réactive, tandis que la crypto
reste sensible aux impulsions momentum et au flux macro.

Points à surveiller :
- maintien ou rejet sur les niveaux intraday
- réaction des actifs leaders
- volume sur cassure ou fausse sortie
- confirmation de tendance avant nouvelle exposition
""".strip()


def build_evening_brief() -> str:
    return """
🌙 Evening Brief

La session se termine sur des niveaux à surveiller pour demain.
Le but est de conserver une lecture claire, sans surtrader,
et de préparer les scénarios pour la prochaine fenêtre active.

Checklist :
- noter les zones défendues
- identifier les faux breakouts
- préparer les actifs leaders
- protéger les gains existants
""".strip()


def job_morning_brief():
    with app.app_context():
        print(f"[{datetime.now()}] Morning brief...")
        print(send_morning_briefings())


def job_midday_brief():
    with app.app_context():
        print(f"[{datetime.now()}] Midday brief...")
        print(
            send_second_briefings(
                second_brief_content=build_midday_brief(),
                title="Midday Brief",
                slot="midday",
            )
        )


def job_evening_brief():
    with app.app_context():
        print(f"[{datetime.now()}] Evening brief...")
        print(
            send_second_briefings(
                second_brief_content=build_evening_brief(),
                title="Evening Brief",
                slot="evening",
            )
        )


def job_daily_news_morning():
    with app.app_context():
        print(f"[{datetime.now()}] Daily news morning...")
        print(send_daily_news(slot="morning"))


def job_daily_news_evening():
    with app.app_context():
        print(f"[{datetime.now()}] Daily news evening...")
        print(send_daily_news(slot="evening"))


def job_breaking_news():
    with app.app_context():
        print(f"[{datetime.now()}] Breaking news check...")

        articles = prepare_digest_articles(limit=1, max_age_hours=6)

        if not articles:
            print("Aucune breaking news disponible.")
            return

        article = articles[0]
        print(f"Breaking news candidate: {article.get('title')}")
        print(send_breaking_news(article))


def job_cleanup_dispatch_logs():
    with app.app_context():
        deleted = purge_old_dispatch_logs(days=30)
        print(f"[{datetime.now()}] Cleanup dispatch logs: {deleted} supprimés")


def run_scheduler():
    scheduler = BlockingScheduler(timezone="Europe/Paris")

    scheduler.add_job(
        job_morning_brief,
        CronTrigger(hour=8, minute=0),
        id="morning_brief",
        replace_existing=True,
    )

    scheduler.add_job(
        job_daily_news_morning,
        CronTrigger(hour=9, minute=0),
        id="daily_news_morning",
        replace_existing=True,
    )

    scheduler.add_job(
        job_breaking_news,
        CronTrigger(minute="*/10"),
        id="breaking_news",
        replace_existing=True,
    )

    scheduler.add_job(
        job_midday_brief,
        CronTrigger(hour=13, minute=0),
        id="midday_brief",
        replace_existing=True,
    )

    scheduler.add_job(
        job_daily_news_evening,
        CronTrigger(hour=17, minute=30),
        id="daily_news_evening",
        replace_existing=True,
    )

    scheduler.add_job(
        job_evening_brief,
        CronTrigger(hour=18, minute=30),
        id="evening_brief",
        replace_existing=True,
    )

    scheduler.add_job(
        job_cleanup_dispatch_logs,
        CronTrigger(hour=3, minute=15),
        id="cleanup_dispatch_logs",
        replace_existing=True,
    )

    print("Scheduler lancé.")
    scheduler.start()


if __name__ == "__main__":
    run_scheduler()