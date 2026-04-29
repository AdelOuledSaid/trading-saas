import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def get_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        return None

    return OpenAI(api_key=api_key)


def generate_daily_briefing(btc_data: str, gold_data: str, eco_data: str) -> str:
    """
    Generate institutional-grade daily briefing (Hedge fund style)
    """

    client = get_client()

    # =========================
    # FALLBACK (IMPORTANT)
    # =========================
    fallback = f"""
🏛 Market Brief

BTC:
{btc_data}

Gold:
{gold_data}

Macro:
{eco_data}

Plan:
- wait for confirmation
- monitor volatility
- manage risk
""".strip()

    if client is None:
        return fallback

    try:
        prompt = f"""
You are a senior macro analyst working in a hedge fund trading desk.

Your mission:
Produce a high-quality institutional trading briefing in ENGLISH ONLY.

Requirements:
- professional tone (Bloomberg / Glassnode style)
- concise, no fluff
- actionable insights
- no hype, no promises
- adapt dynamically to market conditions

Dynamic adaptation rules:
- If volatility is high → emphasize risk, liquidity, invalidation
- If BTC trending → focus continuation / breakout logic
- If Gold leading → highlight macro / safe haven flows
- If macro heavy → explain impact clearly
- If mixed market → emphasize patience & confirmation

========================
STRUCTURE (MANDATORY)
========================

🏛 Market Regime
- risk-on / risk-off / mixed
- dominant flow
- liquidity conditions

₿ Bitcoin Desk View
- structure
- momentum
- key zones
- bullish / bearish scenarios

🥇 Gold Desk View
- trend
- safe-haven demand
- key levels

🌍 Macro & News
- key events
- expected impact

🎯 Trading Opportunities
- assets to monitor
- conditions before entry
- confirmation signals

⚠️ Risk Management
- main risks
- invalidation levels
- what to avoid

📌 Desk Conclusion
- final bias
- execution strategy

========================
DATA
========================

BTC:
{btc_data}

GOLD:
{gold_data}

MACRO:
{eco_data}

Return ONLY the final briefing in English.
"""

        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=prompt
        )

        text = getattr(response, "output_text", "").strip()

        if not text:
            return fallback

        return text

    except Exception:
        return fallback