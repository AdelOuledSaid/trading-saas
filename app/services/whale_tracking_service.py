from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import random


@dataclass
class WhaleAlert:
    asset: str
    network: str
    amount: str
    usd_value: str
    wallet_from: str
    wallet_to: str
    flow_type: str
    bias: str
    impact: str
    time: str
    timestamp: str
    amount_value: float
    usd_value_number: float
    exchange_related: bool
    direction: str  # inflow / outflow / transfer / treasury
    score: int


class WhaleTrackingService:
    """
    Service Whale Tracking.

    Version actuelle :
    - retourne des données mockées propres
    - structure prête pour brancher une API réelle plus tard

    Utilisation :
        service = WhaleTrackingService()
        alerts = service.get_whale_alerts()

    Pour templates Jinja :
        alerts = service.get_whale_alerts_dict()
    """

    SUPPORTED_ASSETS = {"BTC", "ETH", "SOL", "USDT", "USDC"}
    KNOWN_EXCHANGES = {
        "Binance",
        "Coinbase",
        "Kraken",
        "OKX",
        "Bybit",
        "Bitfinex",
        "KuCoin",
        "Gate.io",
    }

    def __init__(self) -> None:
        pass

    # =========================================================
    # PUBLIC API
    # =========================================================

    def get_whale_alerts(
        self,
        asset: Optional[str] = None,
        only_high_impact: bool = False,
        direction: Optional[str] = None,
        limit: int = 20,
    ) -> List[WhaleAlert]:
        """
        Retourne une liste d'alertes WhaleAlert.

        Params:
            asset: BTC / ETH / SOL / USDT / USDC
            only_high_impact: filtre High Impact uniquement
            direction: inflow / outflow / transfer / treasury
            limit: nombre max d'éléments
        """
        alerts = self._load_mock_alerts()

        if asset:
            asset = asset.upper().strip()
            alerts = [a for a in alerts if a.asset == asset]

        if only_high_impact:
            alerts = [a for a in alerts if a.impact == "High Impact"]

        if direction:
            direction = direction.lower().strip()
            alerts = [a for a in alerts if a.direction == direction]

        alerts = sorted(alerts, key=lambda x: x.score, reverse=True)

        return alerts[:limit]

    def get_whale_alerts_dict(
        self,
        asset: Optional[str] = None,
        only_high_impact: bool = False,
        direction: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Retourne les alertes sous forme de dictionnaires
        pour render_template().
        """
        alerts = self.get_whale_alerts(
            asset=asset,
            only_high_impact=only_high_impact,
            direction=direction,
            limit=limit,
        )
        return [asdict(alert) for alert in alerts]

    def get_dashboard_snapshot(self) -> Dict[str, Any]:
        """
        Retourne un résumé global utile pour hero, cards, dashboard.
        """
        alerts = self._load_mock_alerts()

        total_alerts = len(alerts)
        exchange_flows = sum(1 for a in alerts if a.exchange_related)
        bullish_count = sum(1 for a in alerts if a.bias == "Bullish")
        bearish_count = sum(1 for a in alerts if a.bias == "Bearish")
        neutral_count = sum(1 for a in alerts if a.bias == "Neutral")

        total_usd = sum(a.usd_value_number for a in alerts)
        biggest = max(alerts, key=lambda a: a.usd_value_number) if alerts else None

        dominant_bias = "Neutral"
        if bullish_count > bearish_count and bullish_count >= neutral_count:
            dominant_bias = "Bullish"
        elif bearish_count > bullish_count and bearish_count >= neutral_count:
            dominant_bias = "Bearish"

        return {
            "total_alerts": total_alerts,
            "exchange_flows": exchange_flows,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "neutral_count": neutral_count,
            "dominant_bias": dominant_bias,
            "total_usd_tracked": self._format_usd(total_usd),
            "biggest_transaction_asset": biggest.asset if biggest else None,
            "biggest_transaction_value": biggest.usd_value if biggest else None,
            "biggest_transaction_type": biggest.flow_type if biggest else None,
        }

    def get_latest_high_impact(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retourne les plus grosses alertes à fort impact.
        """
        alerts = self.get_whale_alerts(only_high_impact=True, limit=limit)
        return [asdict(a) for a in alerts]

    # =========================================================
    # REAL API PLACEHOLDER
    # =========================================================

    def get_live_whale_alerts(
        self,
        asset: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Placeholder pour future intégration API réelle.

        Plus tard tu pourras :
        - appeler Whale Alert API
        - appeler Etherscan / Solscan / Arkham / Glassnode
        - normaliser les données reçues
        - calculer bias / impact / score
        """
        # Pour l'instant on renvoie les mocks
        return self.get_whale_alerts_dict(asset=asset, limit=limit)

    # =========================================================
    # INTERNAL HELPERS
    # =========================================================

    def _load_mock_alerts(self) -> List[WhaleAlert]:
        """
        Base mock premium.
        """
        raw_alerts = self._mock_seed_data()
        alerts: List[WhaleAlert] = []

        for item in raw_alerts:
            flow_type = item["flow_type"]
            wallet_from = item["wallet_from"]
            wallet_to = item["wallet_to"]
            amount_value = item["amount_value"]
            usd_value_number = item["usd_value_number"]

            direction = self._detect_direction(flow_type)
            exchange_related = self._is_exchange(wallet_from) or self._is_exchange(wallet_to)
            bias = self._compute_bias(direction=direction, wallet_from=wallet_from, wallet_to=wallet_to)
            score = self._compute_impact_score(
                usd_value_number=usd_value_number,
                exchange_related=exchange_related,
                asset=item["asset"],
                direction=direction,
            )
            impact = self._score_to_impact(score)

            alerts.append(
                WhaleAlert(
                    asset=item["asset"],
                    network=item["network"],
                    amount=self._format_amount(item["amount_value"], item["asset"]),
                    usd_value=self._format_usd(item["usd_value_number"]),
                    wallet_from=wallet_from,
                    wallet_to=wallet_to,
                    flow_type=flow_type,
                    bias=bias,
                    impact=impact,
                    time=item["time"],
                    timestamp=item["timestamp"],
                    amount_value=amount_value,
                    usd_value_number=usd_value_number,
                    exchange_related=exchange_related,
                    direction=direction,
                    score=score,
                )
            )

        return alerts

    def _mock_seed_data(self) -> List[Dict[str, Any]]:
        """
        Données mockées réalistes.
        """
        now = datetime.now(timezone.utc)

        def ts(minutes_ago: int) -> str:
            return (now - timedelta(minutes=minutes_ago)).isoformat()

        return [
            {
                "asset": "BTC",
                "network": "Bitcoin",
                "amount_value": 4850,
                "usd_value_number": 312_400_000,
                "wallet_from": "Binance",
                "wallet_to": "Unknown Wallet",
                "flow_type": "Exchange Outflow",
                "time": "12 min",
                "timestamp": ts(12),
            },
            {
                "asset": "ETH",
                "network": "Ethereum",
                "amount_value": 38200,
                "usd_value_number": 118_700_000,
                "wallet_from": "Unknown Wallet",
                "wallet_to": "Coinbase",
                "flow_type": "Exchange Inflow",
                "time": "18 min",
                "timestamp": ts(18),
            },
            {
                "asset": "SOL",
                "network": "Solana",
                "amount_value": 920000,
                "usd_value_number": 146_900_000,
                "wallet_from": "Unknown Wallet",
                "wallet_to": "Kraken",
                "flow_type": "Exchange Inflow",
                "time": "26 min",
                "timestamp": ts(26),
            },
            {
                "asset": "USDT",
                "network": "Ethereum",
                "amount_value": 125_000_000,
                "usd_value_number": 125_000_000,
                "wallet_from": "Tether Treasury",
                "wallet_to": "OKX",
                "flow_type": "Stablecoin Mint / Transfer",
                "time": "39 min",
                "timestamp": ts(39),
            },
            {
                "asset": "BTC",
                "network": "Bitcoin",
                "amount_value": 1240,
                "usd_value_number": 79_800_000,
                "wallet_from": "Unknown Wallet",
                "wallet_to": "Binance",
                "flow_type": "Exchange Inflow",
                "time": "54 min",
                "timestamp": ts(54),
            },
            {
                "asset": "ETH",
                "network": "Ethereum",
                "amount_value": 21700,
                "usd_value_number": 67_400_000,
                "wallet_from": "Kraken",
                "wallet_to": "Cold Wallet",
                "flow_type": "Exchange Outflow",
                "time": "1h 07",
                "timestamp": ts(67),
            },
            {
                "asset": "USDC",
                "network": "Ethereum",
                "amount_value": 84_000_000,
                "usd_value_number": 84_000_000,
                "wallet_from": "Circle Treasury",
                "wallet_to": "Unknown Wallet",
                "flow_type": "Treasury Transfer",
                "time": "1h 22",
                "timestamp": ts(82),
            },
            {
                "asset": "SOL",
                "network": "Solana",
                "amount_value": 410000,
                "usd_value_number": 65_700_000,
                "wallet_from": "Binance",
                "wallet_to": "Unknown Wallet",
                "flow_type": "Exchange Outflow",
                "time": "1h 48",
                "timestamp": ts(108),
            },
            {
                "asset": "BTC",
                "network": "Bitcoin",
                "amount_value": 3100,
                "usd_value_number": 201_200_000,
                "wallet_from": "Coinbase",
                "wallet_to": "Unknown Wallet",
                "flow_type": "Exchange Outflow",
                "time": "2h 04",
                "timestamp": ts(124),
            },
            {
                "asset": "ETH",
                "network": "Ethereum",
                "amount_value": 14500,
                "usd_value_number": 44_300_000,
                "wallet_from": "Unknown Wallet",
                "wallet_to": "Bybit",
                "flow_type": "Exchange Inflow",
                "time": "2h 16",
                "timestamp": ts(136),
            },
            {
                "asset": "USDT",
                "network": "Tron",
                "amount_value": 52_000_000,
                "usd_value_number": 52_000_000,
                "wallet_from": "Unknown Wallet",
                "wallet_to": "Binance",
                "flow_type": "Stablecoin Transfer",
                "time": "2h 32",
                "timestamp": ts(152),
            },
            {
                "asset": "BTC",
                "network": "Bitcoin",
                "amount_value": 890,
                "usd_value_number": 57_600_000,
                "wallet_from": "Unknown Wallet",
                "wallet_to": "Bitfinex",
                "flow_type": "Exchange Inflow",
                "time": "2h 44",
                "timestamp": ts(164),
            },
        ]

    def _compute_bias(self, direction: str, wallet_from: str, wallet_to: str) -> str:
        """
        Logique simple de lecture marché.
        """
        from_exchange = self._is_exchange(wallet_from)
        to_exchange = self._is_exchange(wallet_to)

        if direction == "outflow" and from_exchange and not to_exchange:
            return "Bullish"

        if direction == "inflow" and not from_exchange and to_exchange:
            return "Bearish"

        if direction in {"treasury", "transfer"}:
            return "Neutral"

        return "Neutral"

    def _compute_impact_score(
        self,
        usd_value_number: float,
        exchange_related: bool,
        asset: str,
        direction: str,
    ) -> int:
        """
        Score interne d’importance.
        """
        score = 0

        if usd_value_number >= 25_000_000:
            score += 1
        if usd_value_number >= 50_000_000:
            score += 2
        if usd_value_number >= 100_000_000:
            score += 2
        if usd_value_number >= 250_000_000:
            score += 2

        if exchange_related:
            score += 2

        if asset in {"BTC", "ETH"}:
            score += 1

        if direction in {"inflow", "outflow"}:
            score += 1

        return score

    def _score_to_impact(self, score: int) -> str:
        if score >= 7:
            return "High Impact"
        if score >= 4:
            return "Medium Impact"
        return "Low Impact"

    def _detect_direction(self, flow_type: str) -> str:
        flow = flow_type.lower()

        if "outflow" in flow:
            return "outflow"
        if "inflow" in flow:
            return "inflow"
        if "treasury" in flow:
            return "treasury"
        return "transfer"

    def _is_exchange(self, name: str) -> bool:
        return name in self.KNOWN_EXCHANGES

    def _format_amount(self, value: float, asset: str) -> str:
        if asset in {"USDT", "USDC"}:
            return f"{value:,.0f} {asset}"
        if asset == "SOL":
            return f"{value:,.0f} {asset}"
        if asset in {"BTC", "ETH"}:
            if value >= 1000:
                return f"{value:,.0f} {asset}"
            return f"{value:,.2f} {asset}"
        return f"{value:,.2f} {asset}"

    def _format_usd(self, value: float) -> str:
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"
        return f"${value / 1_000_000:.1f}M"


# =========================================================
# OPTIONAL HELPER FUNCTION
# =========================================================

def get_whale_tracking_service() -> WhaleTrackingService:
    return WhaleTrackingService()