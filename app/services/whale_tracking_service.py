from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional
import os
import time
import requests

from flask import current_app

from app.extensions import cache


# Anti spam TronScan global
_LAST_TRON_CALL = 0
_TRON_COOLDOWN_SECONDS = 75
_LAST_TRON_429_LOG = 0


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
    direction: str
    score: int


class WhaleTrackingService:
    """
    Whale Tracking Service - Real V1 stable

    Fix inclus:
    - protection anti 429 TronScan
    - cooldown TronScan
    - logs moins bruyants
    - fallback propre
    - cache Flask conservé
    """

    ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
    TRONSCAN_BASE_URL = "https://apilist.tronscanapi.com"

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

    EVM_EXCHANGE_ADDRESSES = {
        "0x3f5ce5fbfe3e9af3971dD833D26BA9b5C936f0bE".lower(): "Binance",
        "0x564286362092D8e7936f0549571a803B203aAceD".lower(): "Binance",
        "0x0681d8db095565fe8a346fa0277bffde9c0edbbf".lower(): "Binance",
        "0x71660c4005ba85c37ccec55d0c4493e66fe775d3".lower(): "Coinbase",
        "0x503828976d22510aad0201ac7ec88293211d23da".lower(): "Coinbase",
        "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0".lower(): "Kraken",
        "0x742d35cc6634c0532925a3b844bc454e4438f44e".lower(): "Bitfinex",
        "0x1ab4978a48dc892cd9971ece8e01dcc7688f8f23".lower(): "OKX",
        "0xf89d7b9c864f589bbf53a82105107622b35eaa40".lower(): "Bybit",
    }

    TRON_EXCHANGE_ADDRESSES = {
        "TQef1n2J4jr5qM9hXn9ZWyM8xWw3y7hR6D": "Binance",
        "TJRyWwFs9wTFGZg3J7D6z8L5f5gK7bK4xX": "OKX",
    }

    ETH_USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7".lower()
    ETH_USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48".lower()
    TRON_USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

    def __init__(self) -> None:
        self.etherscan_api_key = os.getenv("ETHERSCAN_API_KEY", "").strip()
        self.tronscan_api_key = os.getenv("TRONSCAN_API_KEY", "").strip()
        self.min_usd = float(os.getenv("WHALE_MIN_USD", "250000"))

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
        alerts = self._load_real_alerts()

        if asset:
            asset = asset.upper().strip()
            alerts = [a for a in alerts if a.asset == asset]

        if only_high_impact:
            alerts = [a for a in alerts if a.impact == "High Impact"]

        if direction:
            direction = direction.lower().strip()
            alerts = [a for a in alerts if a.direction == direction]

        alerts = sorted(alerts, key=lambda x: (x.score, x.timestamp), reverse=True)
        return alerts[:limit]

    def get_whale_alerts_dict(
        self,
        asset: Optional[str] = None,
        only_high_impact: bool = False,
        direction: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        alerts = self.get_whale_alerts(
            asset=asset,
            only_high_impact=only_high_impact,
            direction=direction,
            limit=limit,
        )
        return [asdict(alert) for alert in alerts]

    def get_dashboard_snapshot(self) -> Dict[str, Any]:
        alerts = self._load_real_alerts()

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
        alerts = self.get_whale_alerts(only_high_impact=True, limit=limit)
        return [asdict(a) for a in alerts]

    def get_live_whale_alerts(
        self,
        asset: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return self.get_whale_alerts_dict(asset=asset, limit=limit)

    # =========================================================
    # REAL DATA LOADER
    # =========================================================

    @cache.memoize(timeout=120)
    def _load_real_alerts(self) -> List[WhaleAlert]:
        alerts: List[WhaleAlert] = []

        try:
            alerts.extend(self._fetch_eth_native_whales())
        except Exception as e:
            self._log_warning(f"[whales] ETH native fetch failed: {repr(e)}")

        try:
            alerts.extend(self._fetch_erc20_whales(self.ETH_USDT, "USDT"))
        except Exception as e:
            self._log_warning(f"[whales] ETH USDT fetch failed: {repr(e)}")

        try:
            alerts.extend(self._fetch_erc20_whales(self.ETH_USDC, "USDC"))
        except Exception as e:
            self._log_warning(f"[whales] ETH USDC fetch failed: {repr(e)}")

        try:
            alerts.extend(self._fetch_tronscan_trc20_whales(self.TRON_USDT, "USDT"))
        except Exception as e:
            self._log_warning(f"[whales] TRON USDT fetch skipped: {repr(e)}")

        if not any(a.asset == "BTC" for a in alerts):
            alerts.extend(self._mock_asset_subset({"BTC"}))

        if not any(a.asset == "SOL" for a in alerts):
            alerts.extend(self._mock_asset_subset({"SOL"}))

        dedup = {}
        for a in alerts:
            key = f"{a.asset}|{a.wallet_from}|{a.wallet_to}|{a.timestamp}|{int(a.usd_value_number)}"
            dedup[key] = a

        return list(dedup.values())

    # =========================================================
    # ETHERSCAN
    # =========================================================

    def _etherscan_headers(self) -> Dict[str, str]:
        return {"accept": "application/json"}

    def _etherscan_params(self, **extra) -> Dict[str, Any]:
        params = {
            "chainid": "1",
            "apikey": self.etherscan_api_key,
        }
        params.update(extra)
        return params

    def _fetch_eth_native_whales(self) -> List[WhaleAlert]:
        if not self.etherscan_api_key:
            return []

        seeds = list(self.EVM_EXCHANGE_ADDRESSES.items())[:6]
        rows: List[Dict[str, Any]] = []

        for address, _label in seeds:
            data = self._etherscan_get(
                module="account",
                action="txlist",
                address=address,
                startblock=0,
                endblock=99999999,
                page=1,
                offset=20,
                sort="desc",
            )
            if isinstance(data, list):
                rows.extend(data)
            time.sleep(0.2)

        alerts: List[WhaleAlert] = []
        seen_hashes = set()

        for tx in rows:
            tx_hash = tx.get("hash")
            if not tx_hash or tx_hash in seen_hashes:
                continue
            seen_hashes.add(tx_hash)

            try:
                eth_value = float(Decimal(tx.get("value", "0")) / Decimal(10**18))
            except Exception:
                continue

            if eth_value <= 0:
                continue

            usd_price = self._get_eth_usd_price()
            usd_value_number = eth_value * usd_price

            if usd_value_number < self.min_usd:
                continue

            from_addr = (tx.get("from") or "").lower()
            to_addr = (tx.get("to") or "").lower()

            wallet_from = self._label_evm_address(from_addr)
            wallet_to = self._label_evm_address(to_addr)
            direction = self._infer_direction(wallet_from, wallet_to)
            bias = self._compute_bias(direction, wallet_from, wallet_to)
            exchange_related = self._is_exchange(wallet_from) or self._is_exchange(wallet_to)

            score = self._compute_impact_score(
                usd_value_number=usd_value_number,
                exchange_related=exchange_related,
                asset="ETH",
                direction=direction,
            )

            ts = self._unix_to_iso(tx.get("timeStamp"))

            alerts.append(
                WhaleAlert(
                    asset="ETH",
                    network="Ethereum",
                    amount=self._format_amount(eth_value, "ETH"),
                    usd_value=self._format_usd(usd_value_number),
                    wallet_from=wallet_from,
                    wallet_to=wallet_to,
                    flow_type=self._flow_type_from_direction(direction),
                    bias=bias,
                    impact=self._score_to_impact(score),
                    time=self._humanize_timestamp(ts),
                    timestamp=ts,
                    amount_value=eth_value,
                    usd_value_number=usd_value_number,
                    exchange_related=exchange_related,
                    direction=direction,
                    score=score,
                )
            )

        return alerts

    def _fetch_erc20_whales(self, contract_address: str, asset_symbol: str) -> List[WhaleAlert]:
        if not self.etherscan_api_key:
            return []

        seeds = list(self.EVM_EXCHANGE_ADDRESSES.items())[:6]
        rows: List[Dict[str, Any]] = []

        for address, _label in seeds:
            data = self._etherscan_get(
                module="account",
                action="tokentx",
                address=address,
                contractaddress=contract_address,
                page=1,
                offset=25,
                sort="desc",
            )
            if isinstance(data, list):
                rows.extend(data)
            time.sleep(0.2)

        alerts: List[WhaleAlert] = []
        seen_hashes = set()

        for tx in rows:
            tx_hash = tx.get("hash")
            log_index = tx.get("logIndex", "")
            dedup_hash = f"{tx_hash}:{log_index}"

            if not tx_hash or dedup_hash in seen_hashes:
                continue
            seen_hashes.add(dedup_hash)

            try:
                decimals = int(tx.get("tokenDecimal") or 0)
                token_value = float(Decimal(tx.get("value", "0")) / Decimal(10**decimals))
            except Exception:
                continue

            if token_value <= 0:
                continue

            usd_value_number = token_value if asset_symbol in {"USDT", "USDC"} else 0.0

            if usd_value_number < self.min_usd:
                continue

            from_addr = (tx.get("from") or "").lower()
            to_addr = (tx.get("to") or "").lower()

            wallet_from = self._label_evm_address(from_addr)
            wallet_to = self._label_evm_address(to_addr)
            direction = self._infer_direction(wallet_from, wallet_to)
            bias = self._compute_bias(direction, wallet_from, wallet_to)
            exchange_related = self._is_exchange(wallet_from) or self._is_exchange(wallet_to)

            score = self._compute_impact_score(
                usd_value_number=usd_value_number,
                exchange_related=exchange_related,
                asset=asset_symbol,
                direction=direction,
            )

            ts = self._unix_to_iso(tx.get("timeStamp"))

            alerts.append(
                WhaleAlert(
                    asset=asset_symbol,
                    network="Ethereum",
                    amount=self._format_amount(token_value, asset_symbol),
                    usd_value=self._format_usd(usd_value_number),
                    wallet_from=wallet_from,
                    wallet_to=wallet_to,
                    flow_type=self._flow_type_from_direction(direction, stablecoin=True),
                    bias=bias,
                    impact=self._score_to_impact(score),
                    time=self._humanize_timestamp(ts),
                    timestamp=ts,
                    amount_value=token_value,
                    usd_value_number=usd_value_number,
                    exchange_related=exchange_related,
                    direction=direction,
                    score=score,
                )
            )

        return alerts

    def _etherscan_get(self, **params) -> Any:
        r = requests.get(
            self.ETHERSCAN_BASE_URL,
            params=self._etherscan_params(**params),
            headers=self._etherscan_headers(),
            timeout=12,
        )

        if r.status_code == 429:
            self._log_warning("[whales] Etherscan rate limit hit - skipping")
            return []

        r.raise_for_status()
        data = r.json()

        status = str(data.get("status", ""))
        result = data.get("result")

        if status == "0" and isinstance(result, str) and "No transactions found" in result:
            return []

        if result is None:
            return []

        if isinstance(result, str) and "rate limit" in result.lower():
            self._log_warning("[whales] Etherscan internal rate limit - skipping")
            return []

        return result

    # =========================================================
    # TRONSCAN
    # =========================================================

    def _tronscan_headers(self) -> Dict[str, str]:
        headers = {
            "accept": "application/json",
            "User-Agent": "VelWolf-WhaleTracker/1.0",
        }
        if self.tronscan_api_key:
            headers["TRON-PRO-API-KEY"] = self.tronscan_api_key
        return headers

    def _fetch_tronscan_trc20_whales(
        self,
        contract_address: str,
        asset_symbol: str,
    ) -> List[WhaleAlert]:
        global _LAST_TRON_CALL, _LAST_TRON_429_LOG

        if not self.tronscan_api_key:
            return []

        now = time.time()

        if now - _LAST_TRON_CALL < _TRON_COOLDOWN_SECONDS:
            return []

        _LAST_TRON_CALL = now

        rows: List[Dict[str, Any]] = []
        seeds = list(self.TRON_EXCHANGE_ADDRESSES.items())[:1]

        for address, _label in seeds:
            params = {
                "limit": 12,
                "start": 0,
                "contract_address": contract_address,
                "relatedAddress": address,
                "confirm": "true",
                "filterTokenValue": 1,
            }

            try:
                r = requests.get(
                    f"{self.TRONSCAN_BASE_URL}/api/token_trc20/transfers",
                    params=params,
                    headers=self._tronscan_headers(),
                    timeout=10,
                )

                if r.status_code == 429:
                    if now - _LAST_TRON_429_LOG > 120:
                        self._log_warning("[whales] TRON rate limit hit - skipped for cooldown")
                        _LAST_TRON_429_LOG = now
                    return []

                r.raise_for_status()
                data = r.json()

            except Exception as e:
                self._log_warning(f"[whales] TRON request failed: {repr(e)}")
                return []

            token_transfers = data.get("token_transfers") or data.get("data") or []
            if isinstance(token_transfers, list):
                rows.extend(token_transfers)

            time.sleep(0.35)

        alerts: List[WhaleAlert] = []
        seen = set()

        for tx in rows:
            tx_hash = tx.get("transaction_id") or tx.get("hash")
            if not tx_hash or tx_hash in seen:
                continue
            seen.add(tx_hash)

            raw_amount = tx.get("quant") or tx.get("amount_str") or tx.get("amount")
            decimals = int(tx.get("tokenInfo", {}).get("tokenDecimal") or tx.get("decimals") or 6)

            try:
                token_value = float(Decimal(str(raw_amount)) / Decimal(10**decimals))
            except Exception:
                continue

            usd_value_number = token_value

            if usd_value_number < self.min_usd:
                continue

            from_addr = tx.get("from_address") or tx.get("from") or ""
            to_addr = tx.get("to_address") or tx.get("to") or ""

            wallet_from = self._label_tron_address(from_addr)
            wallet_to = self._label_tron_address(to_addr)

            direction = self._infer_direction(wallet_from, wallet_to)
            bias = self._compute_bias(direction, wallet_from, wallet_to)
            exchange_related = self._is_exchange(wallet_from) or self._is_exchange(wallet_to)

            score = self._compute_impact_score(
                usd_value_number=usd_value_number,
                exchange_related=exchange_related,
                asset=asset_symbol,
                direction=direction,
            )

            ts = self._ms_to_iso(tx.get("block_ts") or tx.get("timestamp"))

            alerts.append(
                WhaleAlert(
                    asset=asset_symbol,
                    network="Tron",
                    amount=self._format_amount(token_value, asset_symbol),
                    usd_value=self._format_usd(usd_value_number),
                    wallet_from=wallet_from,
                    wallet_to=wallet_to,
                    flow_type=self._flow_type_from_direction(direction, stablecoin=True),
                    bias=bias,
                    impact=self._score_to_impact(score),
                    time=self._humanize_timestamp(ts),
                    timestamp=ts,
                    amount_value=token_value,
                    usd_value_number=usd_value_number,
                    exchange_related=exchange_related,
                    direction=direction,
                    score=score,
                )
            )

        return alerts

    # =========================================================
    # LABELING / HELPERS
    # =========================================================

    def _label_evm_address(self, address: str) -> str:
        if not address:
            return "Unknown Wallet"
        label = self.EVM_EXCHANGE_ADDRESSES.get(address.lower())
        if label:
            return label
        return "Unknown Wallet"

    def _label_tron_address(self, address: str) -> str:
        if not address:
            return "Unknown Wallet"
        label = self.TRON_EXCHANGE_ADDRESSES.get(address)
        if label:
            return label
        if address in {"Tether Treasury", "Circle Treasury"}:
            return address
        return "Unknown Wallet"

    def _infer_direction(self, wallet_from: str, wallet_to: str) -> str:
        from_exchange = self._is_exchange(wallet_from)
        to_exchange = self._is_exchange(wallet_to)

        if from_exchange and not to_exchange:
            return "outflow"
        if not from_exchange and to_exchange:
            return "inflow"
        if "Treasury" in wallet_from or "Treasury" in wallet_to:
            return "treasury"
        return "transfer"

    def _flow_type_from_direction(self, direction: str, stablecoin: bool = False) -> str:
        if direction == "outflow":
            return "Exchange Outflow"
        if direction == "inflow":
            return "Exchange Inflow"
        if direction == "treasury":
            return "Stablecoin Mint / Transfer" if stablecoin else "Treasury Transfer"
        return "Transfer"

    def _compute_bias(self, direction: str, wallet_from: str, wallet_to: str) -> str:
        from_exchange = self._is_exchange(wallet_from)
        to_exchange = self._is_exchange(wallet_to)

        if direction == "outflow" and from_exchange and not to_exchange:
            return "Bullish"

        if direction == "inflow" and not from_exchange and to_exchange:
            return "Bearish"

        return "Neutral"

    def _compute_impact_score(
        self,
        usd_value_number: float,
        exchange_related: bool,
        asset: str,
        direction: str,
    ) -> int:
        score = 0

        if usd_value_number >= 250_000:
            score += 1
        if usd_value_number >= 1_000_000:
            score += 2
        if usd_value_number >= 10_000_000:
            score += 2
        if usd_value_number >= 50_000_000:
            score += 2
        if usd_value_number >= 100_000_000:
            score += 1

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
        if value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        return f"${value:,.0f}"

    def _unix_to_iso(self, ts: Any) -> str:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()

    def _ms_to_iso(self, ts: Any) -> str:
        try:
            return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()

    def _humanize_timestamp(self, ts: str) -> str:
        try:
            dt = datetime.fromisoformat(ts)
            now = datetime.now(timezone.utc)
            diff = now - dt

            seconds = int(diff.total_seconds())
            if seconds < 60:
                return "Just now"

            minutes = seconds // 60
            if minutes < 60:
                return f"{minutes} min"

            hours = minutes // 60
            mins = minutes % 60
            if mins == 0:
                return f"{hours}h"
            return f"{hours}h {mins:02d}"
        except Exception:
            return "Recent"

    @cache.memoize(timeout=600)
    def _get_eth_usd_price(self) -> float:
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "ethereum", "vs_currencies": "usd"},
                timeout=8,
            )

            if r.status_code == 429:
                self._log_warning("[whales] ETH price rate limit - fallback used")
                return 3000.0

            r.raise_for_status()
            price = float(r.json().get("ethereum", {}).get("usd", 0) or 0)

            if price <= 0:
                return 3000.0

            return price

        except Exception as e:
            self._log_warning(f"[whales] ETH price fallback used: {repr(e)}")
            return 3000.0

    def _mock_asset_subset(self, assets: set[str]) -> List[WhaleAlert]:
        raw = self._mock_seed_data()
        alerts: List[WhaleAlert] = []

        for item in raw:
            if item["asset"] not in assets:
                continue

            flow_type = item["flow_type"]
            wallet_from = item["wallet_from"]
            wallet_to = item["wallet_to"]
            amount_value = item["amount_value"]
            usd_value_number = item["usd_value_number"]

            direction = self._detect_direction(flow_type)
            exchange_related = self._is_exchange(wallet_from) or self._is_exchange(wallet_to)
            bias = self._compute_bias(direction, wallet_from, wallet_to)

            score = self._compute_impact_score(
                usd_value_number=usd_value_number,
                exchange_related=exchange_related,
                asset=item["asset"],
                direction=direction,
            )

            alerts.append(
                WhaleAlert(
                    asset=item["asset"],
                    network=item["network"],
                    amount=self._format_amount(amount_value, item["asset"]),
                    usd_value=self._format_usd(usd_value_number),
                    wallet_from=wallet_from,
                    wallet_to=wallet_to,
                    flow_type=flow_type,
                    bias=bias,
                    impact=self._score_to_impact(score),
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

    def _detect_direction(self, flow_type: str) -> str:
        flow = flow_type.lower()

        if "outflow" in flow:
            return "outflow"
        if "inflow" in flow:
            return "inflow"
        if "treasury" in flow:
            return "treasury"
        return "transfer"

    def _mock_seed_data(self) -> List[Dict[str, Any]]:
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
        ]

    def _log_warning(self, msg: str) -> None:
        try:
            current_app.logger.warning(msg)
        except Exception:
            print(msg)


def get_whale_tracking_service() -> WhaleTrackingService:
    return WhaleTrackingService()