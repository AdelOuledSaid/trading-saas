from datetime import datetime
from flask import Blueprint, redirect, url_for, flash, request, render_template
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Signal

admin_trades_bp = Blueprint("admin_trades", __name__)


def admin_required():
    return bool(getattr(current_user, "is_admin", False))


@admin_trades_bp.get("/admin/trades")
@login_required
def all_trades():
    if not admin_required():
        return "Accès refusé", 403

    trades = Signal.query.order_by(Signal.created_at.desc()).all()

    return render_template("admin_trades.html", trades=trades)


@admin_trades_bp.post("/admin/trades/<int:trade_id>/delete")
@login_required
def soft_delete_trade(trade_id):
    if not admin_required():
        return "Accès refusé", 403

    trade = Signal.query.get_or_404(trade_id)
    trade.is_deleted = True
    trade.deleted_at = datetime.utcnow()

    db.session.commit()
    flash("Trade supprimé du dashboard et des résultats.", "success")

    return redirect(request.referrer or url_for("admin_trades.all_trades"))


@admin_trades_bp.post("/admin/trades/<int:trade_id>/restore")
@login_required
def restore_trade(trade_id):
    if not admin_required():
        return "Accès refusé", 403

    trade = Signal.query.get_or_404(trade_id)
    trade.is_deleted = False
    trade.deleted_at = None

    db.session.commit()
    flash("Trade restauré.", "success")

    return redirect(request.referrer or url_for("admin_trades.all_trades"))