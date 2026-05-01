import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()


class EconomicCalendarService:

    # =========================
    # CONFIG
    # =========================
    TE_URL = "https://api.tradingeconomics.com/calendar"

    # =========================
    # SAFE
    # =========================
    @staticmethod
    def _safe(value, default="-"):
        if value is None:
            return default
        v = str(value).strip()
        return v if v else default

    # =========================
    # DATE PARSE
    # =========================
    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None

        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str[:19], fmt)
            except:
                continue

        return None

    # =========================
    # PERIOD
    # =========================
    @staticmethod
    def get_date_range(period: str) -> Tuple[str, str]:
        today = datetime.utcnow().date()

        if period == "yesterday":
            start = today - timedelta(days=1)
            end = start
        elif period == "tomorrow":
            start = today + timedelta(days=1)
            end = start
        elif period == "this_week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
        elif period == "next_week":
            start = today + timedelta(days=7 - today.weekday())
            end = start + timedelta(days=6)
        else:
            start = today
            end = today

        return start.isoformat(), end.isoformat()

    # =========================
    # NORMALIZE TE
    # =========================
    @classmethod
    def _normalize_te(cls, item: Dict[str, Any]) -> Dict[str, Any]:

        dt = cls._parse_date(item.get("Date"))

        impact_map = {
            1: "low",
            2: "medium",
            3: "high"
        }

        impact = impact_map.get(item.get("Importance"), "low")

        return {
            "date_obj": dt,
            "date_display": dt.strftime("%d %b %Y • %H:%M") if dt else "-",
            "country": cls._safe(item.get("Country")),
            "currency": cls._safe(item.get("Currency")),
            "event": cls._safe(item.get("Event")),
            "actual": cls._safe(item.get("Actual")),
            "forecast": cls._safe(item.get("Forecast")),
            "previous": cls._safe(item.get("Previous")),
            "impact": impact,
        }

    # =========================
    # API TRADING ECONOMICS
    # =========================
    @classmethod
    def _fetch_te(cls) -> List[Dict[str, Any]]:

        key = os.getenv("TRADING_ECONOMICS_KEY", "guest:guest")

        try:
            params = {
                "c": key,
                "format": "json"
            }

            r = requests.get(cls.TE_URL, params=params, timeout=15)

            print("=== TE DEBUG ===")
            print("STATUS:", r.status_code)
            print("URL:", r.url)

            if r.status_code != 200:
                return []

            data = r.json()

            return [cls._normalize_te(x) for x in data]

        except Exception as e:
            print("TE ERROR:", str(e))
            return []

    # =========================
    # FALLBACK INTELLIGENT
    # =========================
    @classmethod
    def _fallback(cls) -> List[Dict[str, Any]]:

        today = datetime.utcnow().date()

        base = [
            ("USD", "Core CPI YoY", "high"),
            ("USD", "Fed Speech", "medium"),
            ("EUR", "ECB Rate Decision", "high"),
            ("GBP", "CPI YoY", "high"),
            ("JPY", "BoJ Statement", "medium"),
        ]

        events = []

        for i, (cur, name, impact) in enumerate(base):
            dt = datetime.combine(today, datetime.min.time()) + timedelta(hours=8 + i * 2)

            events.append({
                "date_obj": dt,
                "date_display": dt.strftime("%d %b %Y • %H:%M"),
                "country": cur,
                "currency": cur,
                "event": name,
                "actual": "-",
                "forecast": "-",
                "previous": "-",
                "impact": impact,
            })

        return events

    # =========================
    # MAIN
    # =========================
    @classmethod
    def fetch_events(
        cls,
        period: str = "today",
        country: Optional[str] = None,
        importance: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], bool]:

        from_date, to_date = cls.get_date_range(period)

        events = cls._fetch_te()
        fallback = False

        if not events:
            events = cls._fallback()
            fallback = True

        # FILTER DATE
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()

        events = [
            e for e in events
            if e["date_obj"] and from_dt <= e["date_obj"].date() <= to_dt
        ]

        # FILTER COUNTRY
        if country:
            c = country.lower()
            events = [
                e for e in events
                if c in e["currency"].lower() or c in e["country"].lower()
            ]

        # FILTER IMPACT
        if importance:
            events = [e for e in events if e["impact"] == importance]

        # SEARCH SMART
        if search_query:
            q = search_query.lower()

            events = [
                e for e in events
                if q in e["event"].lower()
                or q in e["currency"].lower()
            ]

        events.sort(key=lambda x: x["date_obj"])

        return events, fallback