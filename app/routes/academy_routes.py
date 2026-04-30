from flask import Blueprint, render_template, session, redirect, url_for, flash
from flask_login import current_user, login_required

academy_bp = Blueprint("academy", __name__)


# =========================================================
# HELPERS
# =========================================================

def get_user_plan():
    try:
        if not current_user.is_authenticated:
            return "free"
        return str(getattr(current_user, "plan", "free") or "free").lower()
    except Exception:
        return "free"


def is_premium():
    return get_user_plan() in ["premium", "vip"]


def is_vip():
    return get_user_plan() == "vip"


def has_academy_plus():
    return get_user_plan() in ["premium", "vip"]


def academy_progress():
    return session.get(
        "academy_progress",
        {
            "level1": 0,
            "level2": 0,
            "level3": 0,
            "level4": 0,
            "certificate_ready": False,
        },
    )


def update_progress(progress):
    session["academy_progress"] = progress


def academy_context():
    return {
        "user_plan": get_user_plan(),
        "is_premium": is_premium(),
        "is_vip": is_vip(),
        "has_academy_plus": has_academy_plus(),
        "academy_progress": academy_progress(),
    }


# =========================================================
# INDEX
# =========================================================

@academy_bp.route("/academy")
@academy_bp.route("/<lang_code>/academy")
def academy_index(lang_code=None):
    return render_template("academy/index.html", **academy_context())


# =========================================================
# LEVEL 1 (accessible a tous)
# =========================================================

@academy_bp.route("/academy/level-1")
def academy_level_1():
    return render_template("academy/level1.html", **academy_context())


# =========================================================
# LEVEL 2 (premium / vip)
# =========================================================

@academy_bp.route("/academy/level-2")
def academy_level_2():
    if not is_premium():
        flash("Le niveau 2 est reserve aux plans Premium et VIP.", "warning")
        return redirect(url_for("academy.academy_upgrade"))

    return render_template("academy/level2.html", **academy_context())


# =========================================================
# LEVEL 3 (premium / vip)
# =========================================================

@academy_bp.route("/academy/level-3")
def academy_level_3():
    if not is_premium():
        flash("Le niveau 3 est reserve aux plans Premium et VIP.", "warning")
        return redirect(url_for("academy.academy_upgrade"))

    return render_template("academy/level3.html", **academy_context())


# =========================================================
# LEVEL 4 (vip)
# =========================================================

@academy_bp.route("/academy/level-4")
def academy_level_4():
    if not is_vip():
        flash("Le niveau 4 Pro est reserve au plan VIP.", "warning")
        return redirect(url_for("academy.academy_upgrade"))

    return render_template("academy/level4.html", **academy_context())


# =========================================================
# UPGRADE
# =========================================================

@academy_bp.route("/academy/upgrade")
def academy_upgrade():
    return render_template("academy/upgrade.html", **academy_context())


# =========================================================
# COMPLETE LEVEL
# =========================================================

@academy_bp.route("/academy/complete/<level>", methods=["POST"])
@login_required
def academy_complete_level(level):
    progress = academy_progress()

    if level == "level1":
        progress["level1"] = 100
        progress["level2"] = max(progress.get("level2", 0), 10)

    elif level == "level2":
        if not is_premium():
            flash("Le niveau 2 est reserve aux plans Premium et VIP.", "warning")
            return redirect(url_for("academy.academy_upgrade"))

        progress["level2"] = 100
        progress["level3"] = max(progress.get("level3", 0), 10)

    elif level == "level3":
        if not is_premium():
            flash("Le niveau 3 est reserve aux plans Premium et VIP.", "warning")
            return redirect(url_for("academy.academy_upgrade"))

        progress["level3"] = 100
        progress["level4"] = max(progress.get("level4", 0), 10)

    elif level == "level4":
        if not is_vip():
            flash("Le niveau 4 Pro est reserve au plan VIP.", "warning")
            return redirect(url_for("academy.academy_upgrade"))

        progress["level4"] = 100
        progress["certificate_ready"] = True

    else:
        flash("Niveau invalide.", "danger")
        return redirect(url_for("academy.academy_index"))

    update_progress(progress)
    flash("Progression mise a jour.", "success")
    return redirect(url_for("academy.academy_index"))