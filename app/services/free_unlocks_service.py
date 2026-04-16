from datetime import datetime, timedelta


class FreeUnlocksService:
    def __init__(self):
        self.unlocks = [
            {"token": "ARB", "name": "Arbitrum", "date": "2026-04-23", "value": 1100000000, "market_cap_ratio": 8.70},
            {"token": "APT", "name": "Aptos", "date": "2026-04-20", "value": 62000000, "market_cap_ratio": 1.95},
            {"token": "SUI", "name": "Sui", "date": "2026-04-27", "value": 35000000, "market_cap_ratio": 0.83},
            {"token": "IMX", "name": "Immutable", "date": "2026-04-16", "value": 26000000, "market_cap_ratio": 1.12},
            {"token": "SEI", "name": "Sei", "date": "2026-04-19", "value": 18000000, "market_cap_ratio": 0.76},
            {"token": "STRK", "name": "Starknet", "date": "2026-04-14", "value": 28000000, "market_cap_ratio": 2.10},
            {"token": "ZK", "name": "ZKsync", "date": "2026-04-21", "value": 19000000, "market_cap_ratio": 1.34},
            {"token": "ACE", "name": "Fusionist", "date": "2026-04-30", "value": 10000000, "market_cap_ratio": 3.20},
        ]

        self.token_colors = {
            "ARB": "#22c55e",
            "APT": "#3b82f6",
            "SUI": "#06b6d4",
            "IMX": "#8b5cf6",
            "SEI": "#f97316",
            "STRK": "#e11d48",
            "ZK": "#a855f7",
            "ACE": "#f59e0b",
        }

    def _parse_date(self, value):
        return datetime.strptime(value, "%Y-%m-%d")

    def _days_until(self, date_obj):
        now = datetime.utcnow().date()
        return (date_obj.date() - now).days

    def _token_color(self, token):
        return self.token_colors.get(token.upper(), "#22c55e")

    def _risk_level(self, value, market_cap_ratio, days_until):
        score = 0

        if market_cap_ratio >= 5:
            score += 55
        elif market_cap_ratio >= 2:
            score += 35
        elif market_cap_ratio >= 1:
            score += 20
        else:
            score += 10

        if value >= 500_000_000:
            score += 30
        elif value >= 100_000_000:
            score += 20
        elif value >= 25_000_000:
            score += 10

        if days_until <= 3:
            score += 15
        elif days_until <= 7:
            score += 10
        elif days_until <= 14:
            score += 5

        score = min(score, 100)

        if score >= 75:
            return score, "HIGH RISK", "high"
        if score >= 45:
            return score, "MEDIUM RISK", "medium"
        return score, "LOW RISK", "low"

    def _signal_engine(self, score, market_cap_ratio, days_until, value):
        if score >= 75 and days_until <= 7:
            return {
                "signal": "SELL BIAS",
                "signal_level": "sell",
                "signal_note": "Fort risque de pression vendeuse avant ou pendant l'unlock.",
            }

        if score >= 45 and days_until <= 10:
            return {
                "signal": "CAUTION",
                "signal_level": "caution",
                "signal_note": "Volatilité probable, attendre confirmation avant exposition.",
            }

        if market_cap_ratio >= 3 and days_until <= 14:
            return {
                "signal": "REDUCE RISK",
                "signal_level": "reduce",
                "signal_note": "Mieux vaut alléger ou protéger une position existante.",
            }

        if value < 25_000_000 and market_cap_ratio < 1:
            return {
                "signal": "WATCH",
                "signal_level": "watch",
                "signal_note": "Impact potentiellement limité, simple surveillance.",
            }

        return {
            "signal": "NEUTRAL WATCH",
            "signal_level": "neutral",
            "signal_note": "Pas de signal fort, suivre le contexte marché.",
        }

    def get_upcoming_unlocks(self, days=30):
        now = datetime.utcnow()
        max_date = now + timedelta(days=days)

        items = []
        for item in self.unlocks:
            unlock_date = self._parse_date(item["date"])
            if now <= unlock_date <= max_date:
                days_until = self._days_until(unlock_date)
                score, risk_label, risk_level = self._risk_level(
                    value=item["value"],
                    market_cap_ratio=item["market_cap_ratio"],
                    days_until=days_until,
                )
                signal_data = self._signal_engine(
                    score=score,
                    market_cap_ratio=item["market_cap_ratio"],
                    days_until=days_until,
                    value=item["value"],
                )

                items.append({
                    **item,
                    "date_obj": unlock_date,
                    "date_label": unlock_date.strftime("%d %b %Y"),
                    "day_number": unlock_date.day,
                    "days_until": days_until,
                    "score": score,
                    "risk_label": risk_label,
                    "risk_level": risk_level,
                    "token_color": self._token_color(item["token"]),
                    "is_big": item["value"] > 100_000_000,
                    **signal_data,
                })

        return sorted(items, key=lambda x: x["date_obj"])

    def get_top_unlocks(self, days=30, limit=10):
        upcoming = self.get_upcoming_unlocks(days=days)
        return sorted(upcoming, key=lambda x: (x["score"], x["value"]), reverse=True)[:limit]

    def get_chart(self, days=30):
        upcoming = self.get_upcoming_unlocks(days=days)
        today = datetime.utcnow().date()

        chart_map = {}
        for i in range(days):
            d = today + timedelta(days=i)
            chart_map[d] = {
                "day": d.strftime("%d"),
                "value": 0,
                "events": 0,
                "token": None,
                "color": "#1f2937",
            }

        for item in upcoming:
            d = item["date_obj"].date()
            if d in chart_map:
                chart_map[d]["value"] += item["value"]
                chart_map[d]["events"] += 1
                chart_map[d]["token"] = item["token"]
                chart_map[d]["color"] = item["token_color"]

        return list(chart_map.values())

    def get_alert_summary(self, days=7):
        upcoming = self.get_upcoming_unlocks(days=days)
        if not upcoming:
            return {
                "has_alert": False,
                "title": "Aucune alerte majeure",
                "message": "Aucun unlock important détecté sur la fenêtre proche.",
                "level": "low",
            }

        highest = sorted(upcoming, key=lambda x: (x["score"], x["value"]), reverse=True)[0]

        return {
            "has_alert": highest["risk_level"] in {"high", "medium"},
            "title": f"{highest['token']} - {highest['risk_label']}",
            "message": (
                f"Unlock prévu le {highest['date_label']} | "
                f"${highest['value']:,.0f} | "
                f"{highest['market_cap_ratio']:.2f}% mcap | "
                f"J-{highest['days_until']}"
            ),
            "level": highest["risk_level"],
        }

    def get_calendar_month(self, year=None, month=None):
        today = datetime.utcnow()

        if year is None:
            year = today.year
        if month is None:
            month = today.month

        first_day = datetime(year, month, 1)
        start_weekday = (first_day.weekday() + 1) % 7
        calendar_start = first_day - timedelta(days=start_weekday)

        upcoming = self.get_upcoming_unlocks(days=60)
        by_day = {item["date_obj"].strftime("%Y-%m-%d"): item for item in upcoming}

        weeks = []
        current = calendar_start

        for _ in range(6):
            week = []
            for _ in range(7):
                key = current.strftime("%Y-%m-%d")
                unlock = by_day.get(key)

                week.append({
                    "date": current,
                    "day": current.day,
                    "is_current_month": current.month == month,
                    "unlock": unlock,
                })
                current += timedelta(days=1)
            weeks.append(week)

        return {
            "month_name": first_day.strftime("%B"),
            "year": year,
            "month": month,
            "weeks": weeks,
        }