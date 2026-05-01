from datetime import datetime, timedelta


class FreeUnlocksService:
    def __init__(self):
        # =========================
        # DATA (REALISTIC SIMULATION)
        # =========================
        self.unlocks = [
            # 01 MAI
            {"token": "STABLE", "name": "Stable", "date": "2026-05-01", "value": 29650000, "market_cap_ratio": 0.5},
            {"token": "SAT", "name": "Space and Time", "date": "2026-05-01", "value": 6510000, "market_cap_ratio": 0.8},
            {"token": "SCAL", "name": "Scallop", "date": "2026-05-01", "value": 46220, "market_cap_ratio": 0.2},
            {"token": "PORT3", "name": "Port3 Network", "date": "2026-05-01", "value": 8580, "market_cap_ratio": 0.1},
            {"token": "GMEE", "name": "GAMEE", "date": "2026-05-01", "value": 6110, "market_cap_ratio": 0.1},
            {"token": "ERN", "name": "Ethernity", "date": "2026-05-01", "value": 1590, "market_cap_ratio": 0.1},

            # 03 MAI
            {"token": "STO", "name": "StakeStone", "date": "2026-05-03", "value": 1910000, "market_cap_ratio": 0.6},
            {"token": "IMP", "name": "Impossible Cloud", "date": "2026-05-03", "value": 1250000, "market_cap_ratio": 0.5},
            {"token": "BIO", "name": "BIO Protocol", "date": "2026-05-03", "value": 278970, "market_cap_ratio": 0.3},
            {"token": "NYM", "name": "Nym", "date": "2026-05-03", "value": 108100, "market_cap_ratio": 0.2},
            {"token": "PORTAL", "name": "Portal", "date": "2026-05-03", "value": 74200, "market_cap_ratio": 0.2},
            {"token": "BNDX", "name": "Bondex", "date": "2026-05-03", "value": 44810, "market_cap_ratio": 0.2},

            # 05 MAI
            {"token": "PWR", "name": "Power Protocol", "date": "2026-05-05", "value": 1070000, "market_cap_ratio": 0.7},
            {"token": "GAL", "name": "Galxe", "date": "2026-05-05", "value": 689130, "market_cap_ratio": 0.9},
            {"token": "ASTER", "name": "Aster", "date": "2026-05-05", "value": 294210, "market_cap_ratio": 0.4},
            {"token": "XION", "name": "XION", "date": "2026-05-05", "value": 240830, "market_cap_ratio": 0.4},
            {"token": "INT", "name": "Intuition", "date": "2026-05-05", "value": 240280, "market_cap_ratio": 0.4},
            {"token": "CUDIS", "name": "CUDIS", "date": "2026-05-05", "value": 95690, "market_cap_ratio": 0.3},

            # 08 MAI
            {"token": "MOV", "name": "Movement", "date": "2026-05-08", "value": 2830000, "market_cap_ratio": 1.2},
            {"token": "BSU", "name": "Baby Shark Universe", "date": "2026-05-08", "value": 586680, "market_cap_ratio": 0.4},
            {"token": "DOOD", "name": "Doodles", "date": "2026-05-08", "value": 190830, "market_cap_ratio": 0.3},
            {"token": "DRS", "name": "DRESSdio", "date": "2026-05-08", "value": 49430, "market_cap_ratio": 0.2},
            {"token": "RSG", "name": "Revolving Games", "date": "2026-05-08", "value": 16580, "market_cap_ratio": 0.2},
            {"token": "SKATE", "name": "Skate", "date": "2026-05-08", "value": 3720, "market_cap_ratio": 0.1},

            # 23 MAI (BIG EVENT)
            {"token": "KYUZO", "name": "Kyuzo's Friends", "date": "2026-05-23", "value": 1840000000, "market_cap_ratio": 9.5},
            {"token": "AVANT", "name": "Avantis", "date": "2026-05-23", "value": 3740000, "market_cap_ratio": 1.1},
            {"token": "METEORA", "name": "Meteora", "date": "2026-05-23", "value": 1140000, "market_cap_ratio": 0.8},
            {"token": "AVAIL", "name": "Avail", "date": "2026-05-23", "value": 849110, "market_cap_ratio": 0.7},
            {"token": "CYG", "name": "Cygnus Finance", "date": "2026-05-23", "value": 699110, "market_cap_ratio": 0.6},
            {"token": "ANIME", "name": "Animecoin", "date": "2026-05-23", "value": 607710, "market_cap_ratio": 0.6},
        ]

        # =========================
        # COLORS
        # =========================
        self.token_colors = {
            "STABLE": "#14b8a6",
            "SAT": "#8b5cf6",
            "SCAL": "#94a3b8",
            "PORT3": "#eab308",
            "GMEE": "#6366f1",
            "ERN": "#06b6d4",

            "STO": "#64748b",
            "IMP": "#22c55e",
            "BIO": "#16a34a",
            "NYM": "#0f172a",
            "PORTAL": "#7c3aed",
            "BNDX": "#10b981",

            "PWR": "#7c3aed",
            "GAL": "#3b82f6",
            "ASTER": "#fb923c",
            "XION": "#111827",
            "INT": "#9ca3af",
            "CUDIS": "#84cc16",

            "MOV": "#facc15",
            "BSU": "#0ea5e9",
            "DOOD": "#ec4899",
            "DRS": "#111827",
            "RSG": "#dc2626",
            "SKATE": "#84cc16",

            "KYUZO": "#ef4444",
            "AVANT": "#7c3aed",
            "METEORA": "#f97316",
            "AVAIL": "#38bdf8",
            "CYG": "#22c55e",
            "ANIME": "#f59e0b",
        }

    # =========================
    # INTERNAL HELPERS
    # =========================
    def _parse_date(self, value):
        return datetime.strptime(value, "%Y-%m-%d")

    def _days_until(self, date_obj):
        now = datetime.utcnow().date()
        return (date_obj.date() - now).days

    def _token_color(self, token):
        return self.token_colors.get(token.upper(), "#22c55e")

    # =========================
    # RISK ENGINE
    # =========================
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

        score = min(score, 95)

        if score >= 75:
            return score, "HIGH RISK", "high"
        if score >= 45:
            return score, "MEDIUM RISK", "medium"
        return score, "LOW RISK", "low"

    def _signal_engine(self, score, market_cap_ratio, days_until, value):
        if score >= 75 and days_until <= 7:
            return {"signal": "SELL BIAS", "signal_level": "sell", "signal_note": "Forte pression vendeuse probable."}

        if score >= 45 and days_until <= 10:
            return {"signal": "CAUTION", "signal_level": "caution", "signal_note": "Volatilité probable."}

        return {"signal": "WATCH", "signal_level": "watch", "signal_note": "Surveillance simple."}

    # =========================
    # CORE METHODS
    # =========================
    def get_upcoming_unlocks(self, days=30):
        now = datetime.utcnow()
        max_date = now + timedelta(days=days)

        items = []
        for item in self.unlocks:
            unlock_date = self._parse_date(item["date"])

            if now <= unlock_date <= max_date:
                days_until = self._days_until(unlock_date)

                score, risk_label, risk_level = self._risk_level(
                    item["value"], item["market_cap_ratio"], days_until
                )

                signal_data = self._signal_engine(
                    score, item["market_cap_ratio"], days_until, item["value"]
                )

                items.append({
                    **item,
                    "date_obj": unlock_date,
                    "date_label": unlock_date.strftime("%d %b %Y"),
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
        upcoming = self.get_upcoming_unlocks(days)
        return sorted(upcoming, key=lambda x: (x["score"], x["value"]), reverse=True)[:limit]

    def get_chart(self, days=30):
        upcoming = self.get_upcoming_unlocks(days)
        today = datetime.utcnow().date()

        chart = {}
        for i in range(days):
            d = today + timedelta(days=i)
            chart[d] = {"day": d.strftime("%d"), "value": 0, "events": 0, "token": None, "color": "#1f2937"}

        for item in upcoming:
            d = item["date_obj"].date()
            if d in chart:
                chart[d]["value"] += item["value"]
                chart[d]["events"] += 1
                chart[d]["token"] = item["token"]
                chart[d]["color"] = item["token_color"]

        return list(chart.values())

    def get_alert_summary(self, days=7):
        upcoming = self.get_upcoming_unlocks(days)

        if not upcoming:
            return {"has_alert": False, "level": "low"}

        top = sorted(upcoming, key=lambda x: (x["score"], x["value"]), reverse=True)[0]

        return {
            "has_alert": top["risk_level"] in {"high", "medium"},
            "title": f"{top['token']} - {top['risk_label']}",
            "message": f"{top['date_label']} | ${top['value']:,.0f}",
            "level": top["risk_level"],
        }

    def get_calendar_month(self, year=None, month=None):
        today = datetime.utcnow()

        if not year:
            year = today.year
        if not month:
            month = today.month

        first = datetime(year, month, 1)
        start = first - timedelta(days=(first.weekday() + 1) % 7)

        upcoming = self.get_upcoming_unlocks(days=60)
        by_day = {i["date_obj"].strftime("%Y-%m-%d"): i for i in upcoming}

        weeks = []
        current = start

        for _ in range(6):
            week = []
            for _ in range(7):
                key = current.strftime("%Y-%m-%d")
                week.append({
                    "date": current,
                    "day": current.day,
                    "is_current_month": current.month == month,
                    "unlock": by_day.get(key),
                })
                current += timedelta(days=1)
            weeks.append(week)

        return {
            "month_name": first.strftime("%B"),
            "year": year,
            "month": month,
            "weeks": weeks,
        }