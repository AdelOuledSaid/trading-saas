from app import create_app
from app.models.signal import Signal

app = create_app()

with app.app_context():
    signals = Signal.query.order_by(Signal.id.asc()).limit(10).all()

    print(f"Nombre de signaux trouvés : {len(signals)}")
    for s in signals:
        print(
            f"id={s.id} | asset={s.asset} | action={s.action} | status={s.status} | entry={s.entry_price}"
        )