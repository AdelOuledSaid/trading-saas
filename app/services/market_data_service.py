import requests


class MarketDataService:
    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self, timeout=12):
        self.timeout = timeout

    def _get(self, endpoint, params=None):
        url = f"{self.BASE_URL}{endpoint}"
        response = requests.get(url, params=params or {}, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_global_market_snapshot(self):
        try:
            data = self._get("/global")
            global_data = data.get("data", {})

            return {
                "market_cap_usd": global_data.get("total_market_cap", {}).get("usd", 0),
                "volume_usd": global_data.get("total_volume", {}).get("usd", 0),
                "btc_dominance": global_data.get("market_cap_percentage", {}).get("btc", 0),
                "active_cryptos": global_data.get("active_cryptocurrencies", 0),
                "markets": global_data.get("markets", 0),
                "market_cap_change_24h": global_data.get("market_cap_change_percentage_24h_usd", 0),
            }
        except Exception:
            return {
                "market_cap_usd": 0,
                "volume_usd": 0,
                "btc_dominance": 0,
                "active_cryptos": 0,
                "markets": 0,
                "market_cap_change_24h": 0,
            }

    def get_top_coins(self, per_page=20, page=1):
        try:
            data = self._get(
                "/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": per_page,
                    "page": page,
                    "sparkline": "false",
                    "price_change_percentage": "24h",
                },
            )

            coins = []
            for coin in data:
                coins.append({
                    "id": coin.get("id"),
                    "symbol": (coin.get("symbol") or "").upper(),
                    "name": coin.get("name"),
                    "image": coin.get("image"),
                    "price": coin.get("current_price", 0),
                    "market_cap": coin.get("market_cap", 0),
                    "volume": coin.get("total_volume", 0),
                    "change_24h": coin.get("price_change_percentage_24h", 0),
                })
            return coins
        except Exception:
            return []

    def get_watchlist(self):
        return self.get_top_coins(per_page=8, page=1)