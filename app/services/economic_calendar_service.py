import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import requests
from dotenv import load_dotenv

load_dotenv()


class EconomicCalendarService:

    TE_URL = "https://api.tradingeconomics.com/calendar"

    # Données fallback enrichies avec vrais événements récurrents
    KNOWN_EVENTS = [
        # Format: (currency, event_name, impact, typical_hour, day_offset, category)
        ("USD", "Core CPI YoY",          "high",   8,  0, "inflation"),
        ("EUR", "ECB Rate Decision",      "high",  12,  0, "rates"),
        ("GBP", "CPI YoY",               "high",  14,  0, "inflation"),
        ("USD", "Initial Jobless Claims", "medium", 8,  1, "employment"),
        ("JPY", "BoJ Policy Rate",        "high",   2,  1, "rates"),
        ("USD", "PPI MoM",               "medium", 8,  2, "inflation"),
        ("EUR", "German ZEW",            "medium", 9,  2, "sentiment"),
        ("USD", "Retail Sales MoM",      "high",   8,  3, "consumption"),
        ("GBP", "BoE Rate Decision",     "high",  11,  3, "rates"),
        ("USD", "Michigan Consumer",     "medium", 14, 4, "sentiment"),
        ("EUR", "EU CPI Flash",          "high",   9,  4, "inflation"),
        ("USD", "NFP",                   "high",   8,  5, "employment"),
        ("CAD", "Employment Change",     "high",   8,  5, "employment"),
        ("USD", "FOMC Minutes",          "high",  18,  5, "rates"),
        ("AUD", "RBA Rate Decision",     "medium",  3, 1, "rates"),
    ]

    ASSET_MAP = {
        "USD": ["Gold / Nasdaq", "DXY", "XAUUSD"],
        "EUR": ["EURUSD", "EUR Pairs"],
        "GBP": ["GBPUSD", "GBP Pairs"],
        "JPY": ["USDJPY", "JPY Pairs"],
        "CAD": ["USDCAD", "Oil"],
        "AUD": ["AUDUSD", "AUD Pairs"],
    }

    @staticmethod
    def _safe(value, default="-"):
        if value is None:
            return default
        v = str(value).strip()
        return v if v else default

    @staticmethod
    def _parse_date(date_str):
        if not date_str:
            return None
        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str[:19], fmt)
            except:
                continue
        return None

    @staticmethod
    def get_date_range(period):
        today = datetime.utcnow().date()
        if period == "yesterday":
            d = today - timedelta(days=1)
            return d.isoformat(), d.isoformat()
        if period == "tomorrow":
            d = today + timedelta(days=1)
            return d.isoformat(), d.isoformat()
        if period == "this_week":
            start = today - timedelta(days=today.weekday())
            return start.isoformat(), (start + timedelta(days=6)).isoformat()
        if period == "next_week":
            start = today + timedelta(days=7 - today.weekday())
            return start.isoformat(), (start + timedelta(days=6)).isoformat()
        return today.isoformat(), today.isoformat()

    @classmethod
    def _normalize_te(cls, item):
        dt = cls._parse_date(item.get("Date"))
        impact_map = {1: "low", 2: "medium", 3: "high"}
        currency = cls._safe(item.get("Currency"))
        return {
            "date_obj": dt,
            "date_display": dt.strftime("%d %b %Y • %H:%M") if dt else "-",
            "country": cls._safe(item.get("Country")),
            "currency": currency,
            "event": cls._safe(item.get("Event")),
            "actual": cls._safe(item.get("Actual")),
            "forecast": cls._safe(item.get("Forecast")),
            "previous": cls._safe(item.get("Previous")),
            "impact": impact_map.get(item.get("Importance"), "low"),
            "assets": cls.ASSET_MAP.get(currency, []),
            "category": "",
        }

    @classmethod
    def _fetch_te(cls):
        key = os.getenv("TRADING_ECONOMICS_KEY", "guest:guest")
        if key == "guest:guest":
            return []
        try:
            r = requests.get(cls.TE_URL, params={"c": key, "format": "json"}, timeout=10)
            if r.status_code != 200:
                return []
            return [cls._normalize_te(x) for x in r.json()]
        except Exception:
            return []

    @classmethod
    def _fallback(cls):
        """Fallback enrichi avec événements typiques de la semaine."""
        today = datetime.utcnow().date()
        events = []

        for currency, name, impact, hour, day_off, category in cls.KNOWN_EVENTS:
            dt = datetime.combine(today, datetime.min.time()) + timedelta(days=day_off, hours=hour)
            events.append({
                "date_obj": dt,
                "date_display": dt.strftime("%d %b %Y • %H:%M"),
                "country": currency,
                "currency": currency,
                "event": name,
                "actual": "-",
                "forecast": "-",
                "previous": "-",
                "impact": impact,
                "assets": cls.ASSET_MAP.get(currency, []),
                "category": category,
            })

        return events

    @classmethod
    def fetch_events(cls, period="today", country=None, importance=None, search_query=None):
        from_date, to_date = cls.get_date_range(period)

        events = cls._fetch_te()
        fallback = not bool(events)
        if fallback:
            events = cls._fallback()

        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt   = datetime.strptime(to_date,   "%Y-%m-%d").date()

        events = [e for e in events if e["date_obj"] and from_dt <= e["date_obj"].date() <= to_dt]

        if country:
            c = country.lower()
            events = [e for e in events if c in e["currency"].lower() or c in e["country"].lower()]

        if importance:
            events = [e for e in events if e["impact"] == importance]

        if search_query:
            q = search_query.lower()
            events = [e for e in events if q in e["event"].lower() or q in e["currency"].lower()]

        events.sort(key=lambda x: x["date_obj"])
        return events, fallback
