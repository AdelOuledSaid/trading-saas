from app import create_app
from app.models import Signal
from app.services.telegram_service import send_message_to_tier
from app.services.telegram_dispatcher import (
    send_morning_briefings,
    send_second_briefings,
    send_daily_news,
    send_hourly_news,
    send_liquidations_alerts,
    send_whale_alerts,
    send_token_unlocks_alerts,
    send_signal_open,
    send_signal_tp,
    send_signal_sl,
)


def print_block(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def test_simple_messages():
    print_block("1) TEST ENVOI SIMPLE PAR TIER")
    print("basic   :", send_message_to_tier("basic", "✅ TEST BASIC"))
    print("premium :", send_message_to_tier("premium", "✅ TEST PREMIUM"))
    print("vip     :", send_message_to_tier("vip", "✅ TEST VIP"))
    print("public  :", send_message_to_tier("public", "✅ TEST PUBLIC"))


def test_briefings():
    print_block("2) TEST BRIEFINGS")
    print("morning :", send_morning_briefings())
    print(
        "midday  :",
        send_second_briefings(
            second_brief_content="📍 Test Midday Brief\n\nCeci est un test briefing midday.",
            title="Midday Brief",
            slot="midday",
        ),
    )
    print(
        "evening :",
        send_second_briefings(
            second_brief_content="🌙 Test Evening Brief\n\nCeci est un test briefing evening.",
            title="Evening Brief",
            slot="evening",
        ),
    )


def test_news():
    print_block("3) TEST NEWS")
    print("daily morning :", send_daily_news("morning"))
    print("hourly        :", send_hourly_news())


def test_market_intelligence():
    print_block("4) TEST LIQUIDATIONS / WHALES / UNLOCKS")
    print("liquidations :", send_liquidations_alerts())
    print("whales       :", send_whale_alerts())
    print("unlocks      :", send_token_unlocks_alerts())


def get_latest_signal():
    return Signal.query.order_by(Signal.created_at.desc()).first()


def test_signals():
    print_block("5) TEST SIGNALS")
    signal = get_latest_signal()

    if not signal:
        print("Aucun signal trouvé en base.")
        return

    print(f"Signal trouvé: id={signal.id} trade_id={getattr(signal, 'trade_id', None)} status={signal.status}")
    print("signal open :", send_signal_open(signal))
    print("signal tp   :", send_signal_tp(signal))
    print("signal sl   :", send_signal_sl(signal))


def main():
    app = create_app()

    with app.app_context():
        test_simple_messages()
        test_briefings()
        test_news()
        test_market_intelligence()
        test_signals()

    print_block("FIN DES TESTS")


if __name__ == "__main__":
    main()