import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///users.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", "change-moi-plus-tard")
DOMAIN = os.getenv("DOMAIN", "http://127.0.0.1:5000").rstrip("/")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_VIP_INVITE_LINK = os.getenv("TELEGRAM_VIP_INVITE_LINK", "")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_PRICE_BASIC = os.getenv("STRIPE_PRICE_BASIC", "")
STRIPE_PRICE_PREMIUM = os.getenv("STRIPE_PRICE_PREMIUM", "")
STRIPE_PRICE_VIP = os.getenv("STRIPE_PRICE_VIP", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

TRADINGVIEW_WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")

ALLOWED_ASSETS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "GOLD", "US100", "US500", "FRA40"]
ALLOWED_ACTIONS = ["BUY", "SELL"]
ALLOWED_EVENTS = ["OPEN", "TP", "SL"]
SITE_URL = "https://trading-saas-1.onrender.com"