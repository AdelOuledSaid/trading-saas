from flask import Blueprint, render_template, request
from app.services.economic_calendar_service import EconomicCalendarService

economic_calendar_bp = Blueprint("economic_calendar", __name__)


@economic_calendar_bp.route("/marches/economic-calendar")
def economic_calendar():
    period = (request.args.get("period", "today") or "today").strip().lower()
    q = (request.args.get("q", "") or "").strip()
    country = (request.args.get("country", "") or "").strip()
    importance = (request.args.get("importance", "") or "").strip().lower()
    impact_only = (request.args.get("impact_only", "0") or "0").strip()

    valid_periods = {"yesterday", "today", "tomorrow", "this_week", "next_week"}
    valid_importance = {"low", "medium", "high"}

    if period not in valid_periods:
        period = "today"

    if importance not in valid_importance:
        importance = ""

    if impact_only == "1" and not importance:
        importance = "high"

    events, fallback_mode = EconomicCalendarService.fetch_events(
        period=period,
        country=country or None,
        importance=importance or None,
        search_query=q or None,
    )

    total_events = len(events)
    high_impact_count = sum(1 for e in events if e.get("impact") == "high")
    medium_impact_count = sum(1 for e in events if e.get("impact") == "medium")
    low_impact_count = sum(1 for e in events if e.get("impact") == "low")

    for event in events:
        impact = event.get("impact", "low")
        currency = event.get("currency", "")

        volatility_score = 35

        if impact == "high":
            volatility_score = 90
        elif impact == "medium":
            volatility_score = 65

        if currency == "USD":
            volatility_score += 8
        elif currency in {"EUR", "JPY", "GBP"}:
            volatility_score += 4

        event["volatility_score"] = min(volatility_score, 99)

    impact_order = {"high": 0, "medium": 1, "low": 2}

    events = sorted(
        events,
        key=lambda e: (
            impact_order.get(e.get("impact", "low"), 3),
            e.get("date_obj") is None,
            e.get("date_obj"),
        ),
    )

    market_bias = "Neutral"

    if any(e.get("currency") == "USD" and e.get("impact") == "high" for e in events):
        market_bias = "USD / Gold / Nasdaq Focus"
    elif any(e.get("currency") == "EUR" and e.get("impact") == "high" for e in events):
        market_bias = "EUR Volatility Watch"
    elif any(e.get("currency") == "JPY" and e.get("impact") == "high" for e in events):
        market_bias = "JPY Risk Session"

    top_event = events[0] if events else None

    return render_template(
        "marche/economic_calendar.html",
        events=events,
        active_period=period,
        q=q,
        country=country,
        importance=importance,
        impact_only=impact_only,
        total_events=total_events,
        high_impact_count=high_impact_count,
        medium_impact_count=medium_impact_count,
        low_impact_count=low_impact_count,
        market_bias=market_bias,
        fallback_mode=fallback_mode,
        top_event=top_event,
    )