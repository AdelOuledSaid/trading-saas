from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional


@dataclass
class OpenInterestSnapshot:
    asset: str
    price: str
    oi_value: str
    oi_value_number: float
    change_1h: str
    change_1h_number: float
    change_4h: str
    change_4h_number: float
    change_24h: str
    change_24h_number: float
    market_bias: str
    interpretation: str
    exchange_focus: str
    time: str
    timestamp: str
    score: int


class OpenInterestService:
    """
    Service mock pour la page Open Interest.
    """

    SUPPORTED_ASSETS = {"BTC", "ETH", "SOL", "XRP", "BNB"}

    def get_snapshots(
        self,
        asset: Optional[str] = None,
        only_high_conviction: bool = False,
        limit: int = 20,
    ) -> List[OpenInterestSnapshot]:
        snapshots = self._load_mock_snapshots()

        if asset:
            asset = asset.upper().strip()
            snapshots = [s for s in snapshots if s.asset == asset]

        if only_high_conviction:
            snapshots = [s for s in snapshots if s.score >= 7]

        snapshots = sorted(snapshots, key=lambda x: x.score, reverse=True)
        return snapshots[:limit]

    def get_snapshots_dict(
        self,
        asset: Optional[str] = None,
        only_high_conviction: bool = False,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return [
            asdict(snapshot)
            for snapshot in self.get_snapshots(
                asset=asset,
                only_high_conviction=only_high_conviction,
                limit=limit,
            )
        ]

    def get_summary(self) -> Dict[str, Any]:
        snapshots = self._load_mock_snapshots()

        total_oi = sum(s.oi_value_number for s in snapshots)
        positive_1h = sum(1 for s in snapshots if s.change_1h_number > 0)
        negative_1h = sum(1 for s in snapshots if s.change_1h_number < 0)

        dominant_bias = "Neutral"
        if positive_1h > negative_1h:
            dominant_bias = "Position Build-Up"
        elif negative_1h > positive_1h:
            dominant_bias = "Deleveraging"

        biggest = max(snapshots, key=lambda s: s.oi_value_number) if snapshots else None

        return {
            "total_assets": len(snapshots),
            "total_oi": self._format_billions(total_oi),
            "dominant_bias": dominant_bias,
            "positive_1h_count": positive_1h,
            "negative_1h_count": negative_1h,
            "biggest_asset": biggest.asset if biggest else "BTC",
            "biggest_oi": biggest.oi_value if biggest else "$0.0B",
            "biggest_exchange_focus": biggest.exchange_focus if biggest else "Binance / Bybit",
        }

    def get_top_snapshots(self, limit: int = 5) -> List[Dict[str, Any]]:
        snapshots = sorted(self._load_mock_snapshots(), key=lambda s: s.oi_value_number, reverse=True)
        return [asdict(s) for s in snapshots[:limit]]

    def _load_mock_snapshots(self) -> List[OpenInterestSnapshot]:
        now = datetime.now(timezone.utc)

        raw = [
            ("BTC", 68420, 12.8, 2.4, 5.8, 12.6, "Bullish", "Prix et OI montent ensemble, ce qui suggère de nouvelles positions acheteuses.", "Binance / Bybit", 9, 12),
            ("ETH", 3448, 6.4, -1.2, 3.5, 8.1, "Neutral", "Le prix reste ferme mais l’OI varie moins vite, la lecture reste mixte.", "Bybit / OKX", 6, 18),
            ("SOL", 182.4, 2.9, 4.8, 9.2, 15.4, "Bullish", "Hausse du prix et de l’OI, contexte compatible avec une construction de positions.", "Binance", 8, 24),
            ("XRP", 0.8421, 1.6, -3.4, -6.8, -2.1, "Bearish", "Baisse de l’OI avec affaiblissement du prix, contexte de dégonflement.", "OKX", 5, 33),
            ("BNB", 602.5, 1.9, 1.1, 2.9, 5.4, "Neutral", "L’OI remonte légèrement, mais la lecture reste modérée sans signal extrême.", "Binance", 5, 41),
            ("BTC", 68610, 13.1, 3.1, 6.4, 14.2, "Bullish", "OI solide et prix ferme, pression de continuation possible.", "CME / Binance", 10, 52),
            ("ETH", 3415, 6.1, -2.6, -1.4, 4.8, "Bearish", "Le prix faiblit pendant que l’OI ne confirme pas franchement une reprise.", "Bybit", 6, 63),
            ("SOL", 178.6, 2.7, -4.2, 1.8, 12.2, "Bearish", "Variation rapide de l’OI avec instabilité du prix, contexte plus fragile.", "Binance / OKX", 7, 75),
        ]

        snapshots: List[OpenInterestSnapshot] = []
        for asset, price, oi_b, ch1, ch4, ch24, bias, interpretation, exch, score, mins_ago in raw:
            ts = now - timedelta(minutes=mins_ago)
            snapshots.append(
                OpenInterestSnapshot(
                    asset=asset,
                    price=self._format_price(price, asset),
                    oi_value=f"${oi_b:.1f}B",
                    oi_value_number=oi_b,
                    change_1h=self._format_pct(ch1),
                    change_1h_number=ch1,
                    change_4h=self._format_pct(ch4),
                    change_4h_number=ch4,
                    change_24h=self._format_pct(ch24),
                    change_24h_number=ch24,
                    market_bias=bias,
                    interpretation=interpretation,
                    exchange_focus=exch,
                    time=self._humanize_minutes(mins_ago),
                    timestamp=ts.isoformat(),
                    score=score,
                )
            )
        return snapshots

    def _format_pct(self, value: float) -> str:
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.1f}%"

    def _format_billions(self, value: float) -> str:
        return f"${value:.1f}B"

    def _format_price(self, value: float, asset: str) -> str:
        if asset == "XRP":
            return f"${value:.4f}"
        return f"${value:,.2f}"

    def _humanize_minutes(self, mins_ago: int) -> str:
        if mins_ago < 60:
            return f"{mins_ago} min"
        hours = mins_ago // 60
        mins = mins_ago % 60
        if mins == 0:
            return f"{hours}h"
        return f"{hours}h {mins:02d}"


def get_open_interest_service() -> OpenInterestService:
    return OpenInterestService()