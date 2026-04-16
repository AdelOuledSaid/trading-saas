import requests
import config
from datetime import datetime, timedelta


class TokenUnlocksService:
    BASE_URL = "https://api.tokenomist.ai/v4"

    def __init__(self):
        self.api_key = config.TOKENOMIST_API_KEY

    def _headers(self):
        return {
            "x-api-key": self.api_key,
            "accept": "application/json"
        }

    def _get(self, endpoint, params=None):
        url = f"{self.BASE_URL}{endpoint}"
        r = requests.get(url, headers=self._headers(), params=params or {}, timeout=15)
        r.raise_for_status()
        return r.json()

    # =========================
    # 1) GET ALL TOKENS
    # =========================
    def get_tokens(self, limit=50):
        try:
            data = self._get("/token/list")
            tokens = data.get("data", [])

            return tokens[:limit]
        except Exception:
            return []

    # =========================
    # 2) GET UNLOCKS FOR TOKEN
    # =========================
    def get_token_unlocks(self, token_id):
        try:
            data = self._get("/unlock/events", params={"tokenId": token_id})
            return data.get("data", [])
        except Exception:
            return []

    # =========================
    # 3) GLOBAL AGGREGATOR
    # =========================
    def get_global_unlocks(self, days=30, limit_tokens=30):
        tokens = self.get_tokens(limit=limit_tokens)

        now = datetime.utcnow()
        max_date = now + timedelta(days=days)

        all_unlocks = []

        for token in tokens:
            token_id = token.get("id")
            token_symbol = token.get("symbol", "").upper()
            token_name = token.get("name")

            events = self.get_token_unlocks(token_id)

            for e in events:
                unlock_date = e.get("unlockDate")
                if not unlock_date:
                    continue

                try:
                    unlock_date = datetime.fromisoformat(unlock_date.replace("Z", ""))
                except:
                    continue

                if unlock_date < now or unlock_date > max_date:
                    continue

                cliff = e.get("cliffUnlocks", {})

                value = float(cliff.get("cliffValue", 0) or 0)

                all_unlocks.append({
                    "token": token_symbol,
                    "name": token_name,
                    "date": unlock_date,
                    "value": value
                })

        return sorted(all_unlocks, key=lambda x: x["date"])

    # =========================
    # 4) CHART
    # =========================
    def get_chart(self, days=30):
        unlocks = self.get_global_unlocks(days=days)

        chart = {}
        now = datetime.utcnow().date()

        for i in range(days):
            d = now + timedelta(days=i)
            chart[d] = 0

        for u in unlocks:
            d = u["date"].date()
            if d in chart:
                chart[d] += u["value"]

        return [
            {
                "day": d.strftime("%d"),
                "value": chart[d]
            }
            for d in chart
        ]

    # =========================
    # 5) TOP UNLOCKS
    # =========================
    def get_top_unlocks(self):
        unlocks = self.get_global_unlocks(days=30)
        return sorted(unlocks, key=lambda x: x["value"], reverse=True)[:10]