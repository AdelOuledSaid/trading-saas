import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import requests


class EconomicCalendarService:
    BASE_URL = "https://eodhistoricaldata.com/api/economic-events"

    FALLBACK_EVENTS = [
        {
            "date": "2026-04-14",
            "time": "08:00:00",
            "country": "EU",
            "currency": "EUR",
            "event": "ECB President Speech",
            "actual": "-",
            "forecast": "-",
            "previous": "-",
            "importance": "high",
        },
        {
            "date": "2026-04-14",
            "time": "12:30:00",
            "country": "US",
            "currency": "USD",
            "event": "Core CPI YoY",
            "actual": "3.2%",
            "forecast": "3.1%",
            "previous": "3.4%",
            "importance": "high",
        },
        {
            "date": "2026-04-14",
            "time": "12:30:00",
            "country": "US",
            "currency": "USD",
            "event": "CPI MoM",
            "actual": "0.4%",
            "forecast": "0.3%",
            "previous": "0.4%",
            "importance": "high",
        },
        {
            "date": "2026-04-14",
            "time": "14:00:00",
            "country": "US",
            "currency": "USD",
            "event": "Fed Member Speech",
            "actual": "-",
            "forecast": "-",
            "previous": "-",
            "importance": "medium",
        },
        {
            "date": "2026-04-15",
            "time": "06:00:00",
            "country": "UK",
            "currency": "GBP",
            "event": "CPI YoY",
            "actual": "2.8%",
            "forecast": "2.7%",
            "previous": "3.0%",
            "importance": "high",
        },
        {
            "date": "2026-04-15",
            "time": "12:30:00",
            "country": "US",
            "currency": "USD",
            "event": "Retail Sales MoM",
            "actual": "0.6%",
            "forecast": "0.4%",
            "previous": "0.3%",
            "importance": "high",
        },
        {
            "date": "2026-04-15",
            "time": "14:30:00",
            "country": "US",
            "currency": "USD",
            "event": "Crude Oil Inventories",
            "actual": "-1.8M",
            "forecast": "-0.9M",
            "previous": "1.2M",
            "importance": "medium",
        },
        {
            "date": "2026-04-16",
            "time": "01:30:00",
            "country": "AU",
            "currency": "AUD",
            "event": "Employment Change",
            "actual": "24K",
            "forecast": "18K",
            "previous": "11K",
            "importance": "high",
        },
        {
            "date": "2026-04-16",
            "time": "11:00:00",
            "country": "EU",
            "currency": "EUR",
            "event": "Core CPI YoY Final",
            "actual": "2.7%",
            "forecast": "2.7%",
            "previous": "2.9%",
            "importance": "high",
        },
        {
            "date": "2026-04-16",
            "time": "12:15:00",
            "country": "EU",
            "currency": "EUR",
            "event": "ECB Rate Decision",
            "actual": "4.25%",
            "forecast": "4.25%",
            "previous": "4.50%",
            "importance": "high",
        },
        {
            "date": "2026-04-17",
            "time": "12:30:00",
            "country": "US",
            "currency": "USD",
            "event": "Initial Jobless Claims",
            "actual": "221K",
            "forecast": "225K",
            "previous": "232K",
            "importance": "medium",
        },
        {
            "date": "2026-04-17",
            "time": "14:00:00",
            "country": "US",
            "currency": "USD",
            "event": "Consumer Sentiment",
            "actual": "77.5",
            "forecast": "76.9",
            "previous": "76.1",
            "importance": "medium",
        },
        {
            "date": "2026-04-20",
            "time": "00:01:00",
            "country": "CN",
            "currency": "CNY",
            "event": "Loan Prime Rate 1Y",
            "actual": "3.35%",
            "forecast": "3.35%",
            "previous": "3.45%",
            "importance": "medium",
        },
        {
            "date": "2026-04-21",
            "time": "14:00:00",
            "country": "CA",
            "currency": "CAD",
            "event": "BoC Governor Speech",
            "actual": "-",
            "forecast": "-",
            "previous": "-",
            "importance": "medium",
        },
        {
            "date": "2026-04-22",
            "time": "13:45:00",
            "country": "US",
            "currency": "USD",
            "event": "Flash Manufacturing PMI",
            "actual": "51.6",
            "forecast": "51.2",
            "previous": "50.8",
            "importance": "medium",
        },
    ]

    @staticmethod
    def _safe_text(value: Any, default: str = "-") -> str:
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default

    @staticmethod
    def _parse_date(date_raw: Optional[str], time_raw: Optional[str] = None) -> Optional[datetime]:
        if not date_raw:
            return None

        candidates = []

        if time_raw:
            candidates.extend([
                f"{date_raw} {time_raw}",
                f"{date_raw} {time_raw}:00",
            ])

        candidates.append(date_raw)

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
        ]

        for candidate in candidates:
            for fmt in formats:
                try:
                    return datetime.strptime(candidate, fmt)
                except ValueError:
                    continue

        return None

    @staticmethod
    def get_date_range(period: str) -> tuple[str, str]:
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
            start = today - timedelta(days=today.weekday()) + timedelta(days=7)
            end = start + timedelta(days=6)
        else:
            start = today
            end = today

        return start.isoformat(), end.isoformat()

    @classmethod
    def _normalize_event(cls, item: Dict[str, Any]) -> Dict[str, Any]:
        date_raw = item.get("date")
        time_raw = item.get("time")
        dt = cls._parse_date(date_raw, time_raw)

        impact_raw = cls._safe_text(
            item.get("importance") or item.get("impact") or "low",
            "low"
        ).lower()

        if impact_raw not in {"low", "medium", "high"}:
            impact_raw = "low"

        return {
            "date_obj": dt,
            "date_display": dt.strftime("%d %b %Y • %H:%M") if dt else cls._safe_text(date_raw),
            "country": cls._safe_text(item.get("country")),
            "currency": cls._safe_text(item.get("currency")),
            "event": cls._safe_text(item.get("event")),
            "actual": cls._safe_text(item.get("actual")),
            "forecast": cls._safe_text(item.get("forecast")),
            "previous": cls._safe_text(item.get("previous")),
            "impact": impact_raw,
        }

    @classmethod
    def _fetch_from_api(cls, from_date: str, to_date: str) -> List[Dict[str, Any]]:
        api_key = os.getenv("EODHD_API_KEY")
        if not api_key:
            return []

        params = {
            "api_token": api_key,
            "fmt": "json",
            "from": from_date,
            "to": to_date,
        }

        try:
            response = requests.get(cls.BASE_URL, params=params, timeout=20)
            print("=== EODHD DEBUG START ===", flush=True)
            print("URL:", response.url, flush=True)
            print("STATUS:", response.status_code, flush=True)
            print("RESPONSE:", response.text[:1000], flush=True)
            print("=== EODHD DEBUG END ===", flush=True)

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                return []

            return [cls._normalize_event(item) for item in data]

        except Exception as e:
            print("=== EODHD ERROR ===", flush=True)
            print(str(e), flush=True)
            return []

    @classmethod
    def _fetch_fallback(cls) -> List[Dict[str, Any]]:
        return [cls._normalize_event(item) for item in cls.FALLBACK_EVENTS]

    @classmethod
    def fetch_events(
        cls,
        period: str = "today",
        country: Optional[str] = None,
        importance: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from_date, to_date = cls.get_date_range(period)

        events = cls._fetch_from_api(from_date, to_date)

        if not events:
            events = cls._fetch_fallback()

        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()

        filtered_by_period = []
        for event in events:
            if event["date_obj"] is None:
                continue
            event_date = event["date_obj"].date()
            if from_dt <= event_date <= to_dt:
                filtered_by_period.append(event)

        events = filtered_by_period

        if country:
            country_lower = country.strip().lower()
            events = [
                e for e in events
                if country_lower in e["country"].lower() or country_lower in e["currency"].lower()
            ]

        if importance and importance.lower() in {"low", "medium", "high"}:
            events = [e for e in events if e["impact"] == importance.lower()]

        if search_query:
            q = search_query.strip().lower()
            if q:
                query_aliases = {
                    "gold": ["gold", "xau", "usd", "cpi", "fed", "inflation", "interest", "jobless"],
                    "btc": ["btc", "bitcoin", "usd", "fed", "cpi", "risk", "nasdaq"],
                    "nasdaq": ["nasdaq", "usd", "fed", "cpi", "retail", "pmi", "jobs"],
                }

                expanded_terms = [q]
                if q in query_aliases:
                    expanded_terms.extend(query_aliases[q])

                events = [
                    e for e in events
                    if any(
                        term in e["event"].lower()
                        or term in e["country"].lower()
                        or term in e["currency"].lower()
                        for term in expanded_terms
                    )
                ]

        events.sort(key=lambda x: x["date_obj"] or datetime.max)
        return events