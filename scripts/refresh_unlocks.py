from app import create_app
from app.services.free_unlocks_service import FreeUnlocksService

app = create_app()

with app.app_context():
    result = FreeUnlocksService().refresh_now()
    print(result)
