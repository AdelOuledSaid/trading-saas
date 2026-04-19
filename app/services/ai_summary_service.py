from __future__ import annotations

import os
from typing import Any, Dict

from openai import OpenAI


class AISummaryService:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip()
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def summarize(self, payload: Dict[str, Any]) -> str:
        if not self.client:
            return self._fallback_summary(payload)

        token = payload.get("token", "Unknown")
        interval = payload.get("interval", "1h")
        indicator = payload.get("indicator", "stochasticrsi")
        signal = payload.get("signal", "neutral")
        bias = payload.get("bias", "mixed")

        prompt = f"""
Tu es l'analyste IA premium de VelWolef.
Rédige une analyse courte, pro, claire, style desk institutionnel.

Contraintes :
- 90 à 140 mots
- français
- pas de promesse
- pas de conseil financier absolu
- ton premium, précis, exploitable
- mentionne le token, le timeframe, le biais, l'indicateur sélectionné, la structure, le momentum et le risque principal

Données :
{payload}

Réponds uniquement avec le texte final.
""".strip()

        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )
        text = getattr(response, "output_text", "") or ""
        return text.strip() if text.strip() else self._fallback_summary(payload)

    def _fallback_summary(self, payload: Dict[str, Any]) -> str:
        token = payload.get("token", "Unknown")
        interval = str(payload.get("interval", "1h")).upper()
        trend = payload.get("trend", payload.get("bias", "mixed"))
        signal = payload.get("signal", "neutral")
        rsi = payload.get("rsi", "-")
        stoch_k = payload.get("stochastic_rsi_k", "-")
        mfi = payload.get("mfi", "-")
        confidence = payload.get("confidence", "-")

        return (
            f"{token} sur {interval} conserve une lecture {trend}. "
            f"Le signal ressort actuellement {signal}, avec un RSI à {rsi}, "
            f"un Stochastic RSI K à {stoch_k} et un MFI à {mfi}. "
            f"La structure reste exploitable si le momentum reste soutenu, "
            f"mais le risque principal demeure une perte du pivot ou un affaiblissement du flux. "
            f"Confiance estimée : {confidence}%."
        )