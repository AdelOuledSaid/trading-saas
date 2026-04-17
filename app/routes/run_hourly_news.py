from app import create_app
from app.services.telegram_dispatcher import dispatch_event

app = create_app()

with app.app_context():
    print(dispatch_event("hourly_news"))