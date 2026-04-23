import os
from dotenv import load_dotenv

load_dotenv()

# =========================
# DATABASE
# =========================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///users.db")

# Fix PostgreSQL (Render / Heroku)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# =========================
# SECURITY
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "change-moi-plus-tard")
MANUAL_SIGNAL_SECRET = os.getenv("MANUAL_SIGNAL_SECRET")

# =========================
# RESEND EMAIL
# =========================
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

# =========================
# DOMAIN
# =========================
DOMAIN = os.getenv("DOMAIN", "http://127.0.0.1:5000").rstrip("/")

SITE_URL = os.getenv("SITE_URL", "https://www.velwolef.com")
# =========================
# TELEGRAM
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

TELEGRAM_PUBLIC_CHAT_ID = os.getenv("TELEGRAM_PUBLIC_CHAT_ID", "")
TELEGRAM_BASIC_CHAT_ID = os.getenv("TELEGRAM_BASIC_CHAT_ID", "")
TELEGRAM_PREMIUM_CHAT_ID = os.getenv("TELEGRAM_PREMIUM_CHAT_ID", "")
TELEGRAM_VIP_CHAT_ID = os.getenv("TELEGRAM_VIP_CHAT_ID", "")

TELEGRAM_VIP_INVITE_LINK = os.getenv("TELEGRAM_VIP_INVITE_LINK", "")
TELEGRAM_PREMIUM_INVITE_LINK = os.getenv("TELEGRAM_PREMIUM_INVITE_LINK", "")
TELEGRAM_BASIC_INVITE_LINK = os.getenv("TELEGRAM_BASIC_INVITE_LINK", "")
TELEGRAM_PUBLIC_INVITE_LINK = os.getenv("TELEGRAM_PUBLIC_INVITE_LINK", "")

TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")

# =========================
# STRIPE
# =========================
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# =========================
# STRIPE PRICING (MULTI DEVISE)
# =========================
STRIPE_PRICE_BASIC_EUR = os.getenv("STRIPE_PRICE_BASIC_EUR", "")
STRIPE_PRICE_BASIC_USD = os.getenv("STRIPE_PRICE_BASIC_USD", "")

STRIPE_PRICE_PREMIUM_EUR = os.getenv("STRIPE_PRICE_PREMIUM_EUR", "")
STRIPE_PRICE_PREMIUM_USD = os.getenv("STRIPE_PRICE_PREMIUM_USD", "")

STRIPE_PRICE_VIP_EUR = os.getenv("STRIPE_PRICE_VIP_EUR", "")
STRIPE_PRICE_VIP_USD = os.getenv("STRIPE_PRICE_VIP_USD", "")

# =========================
# TRADING / APIs
# =========================
TRADINGVIEW_WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")

# =========================
# TRADING CONFIG
# =========================
ALLOWED_ASSETS = [
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "XRPUSD",
    "GOLD",
    "XAUUSD",
    "US100",
    "US500",
    "FRA40",
]

ALLOWED_ACTIONS = ["BUY", "SELL"]
ALLOWED_EVENTS = ["OPEN", "TP", "SL", "CLOSE"]