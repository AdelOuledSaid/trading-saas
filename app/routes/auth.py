from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from email_validator import validate_email, EmailNotValidError

from app.extensions import db
from app.models import User
from app.services.email_service import send_email

auth_bp = Blueprint("auth", __name__)

SUPPORTED_LANGS = ["fr", "en", "es"]
DEFAULT_LANG = "fr"


def get_lang(lang_code):
    if lang_code in SUPPORTED_LANGS:
        session["lang"] = lang_code
        return lang_code
    return session.get("lang", DEFAULT_LANG)


def normalize_and_validate_email(email_raw: str):
    email_raw = (email_raw or "").strip().lower()

    if not email_raw:
        raise EmailNotValidError("empty email")

    # check_deliverability=True = vérifie mieux le domaine mail
    valid = validate_email(email_raw, check_deliverability=True)
    return valid.email.lower()


def get_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_confirmation_token(email):
    serializer = get_serializer()
    return serializer.dumps(email, salt="email-confirm")


def confirm_token(token, expiration=3600):
    serializer = get_serializer()
    return serializer.loads(token, salt="email-confirm", max_age=expiration)


def generate_reset_token(email):
    serializer = get_serializer()
    return serializer.dumps(email, salt="password-reset")


def confirm_reset_token(token, expiration=3600):
    serializer = get_serializer()
    return serializer.loads(token, salt="password-reset", max_age=expiration)


def send_verification_email(user, lang_code):
    token = generate_confirmation_token(user.email)

    base_url = current_app.config.get("APP_BASE_URL", "")
    confirm_url = base_url + url_for(
        "auth.reset_password",
        token=token,
        lang_code=lang_code
    )

    html = f"""
    <div style="background:#0b0f1a;padding:30px;color:white;font-family:Arial,sans-serif;">
        <h2 style="color:#00ff99;margin-bottom:10px;">VelWolef 🚀</h2>
        <p style="font-size:15px;line-height:1.6;">
            Confirme ton email pour activer ton compte.
        </p>

        <a href="{confirm_url}"
           style="display:inline-block;margin-top:20px;padding:12px 20px;background:#00ff99;color:#000;text-decoration:none;border-radius:6px;font-weight:bold;">
            Confirmer mon compte
        </a>

        <p style="margin-top:25px;font-size:12px;color:#aaaaaa;">
            Si tu n’as pas créé ce compte, ignore cet email.
        </p>

        <p style="margin-top:15px;font-size:12px;color:#777777;word-break:break-all;">
            Lien direct : {confirm_url}
        </p>
    </div>
    """

    return send_email(
        to_email=user.email,
        subject="Confirme ton compte VelWolef",
        html=html
    )


def send_reset_password_email(user, lang_code):
    token = generate_reset_token(user.email)

    reset_url = url_for(
        "auth.reset_password",
        token=token,
        lang_code=lang_code,
        _external=True
    )

    html = f"""
    <div style="background:#0b0f1a;padding:30px;color:white;font-family:Arial,sans-serif;">
        <h2 style="color:#ff4d4d;margin-bottom:10px;">VelWolef 🔐</h2>
        <p style="font-size:15px;line-height:1.6;">
            Tu as demandé la réinitialisation de ton mot de passe.
        </p>

        <a href="{reset_url}"
           style="display:inline-block;margin-top:20px;padding:12px 20px;background:#ff4d4d;color:#fff;text-decoration:none;border-radius:6px;font-weight:bold;">
            Réinitialiser mon mot de passe
        </a>

        <p style="margin-top:25px;font-size:12px;color:#aaaaaa;">
            Si tu n’es pas à l’origine de cette demande, ignore cet email.
        </p>

        <p style="margin-top:15px;font-size:12px;color:#777777;word-break:break-all;">
            Lien direct : {reset_url}
        </p>
    </div>
    """

    return send_email(
        to_email=user.email,
        subject="Réinitialisation de ton mot de passe VelWolef",
        html=html
    )


# =========================
# REGISTER
# =========================
@auth_bp.route("/<lang_code>/register", methods=["GET", "POST"])
def register(lang_code):
    current_lang = get_lang(lang_code)

    if request.method == "POST":
        email_raw = request.form.get("email", "")
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not email_raw.strip() or not password or not confirm_password:
            flash("Merci de remplir tous les champs.", "warning")
            return redirect(url_for("auth.register", lang_code=current_lang))

        try:
            email = normalize_and_validate_email(email_raw)
        except EmailNotValidError:
            flash("Veuillez entrer une adresse email valide.", "danger")
            return redirect(url_for("auth.register", lang_code=current_lang))

        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "warning")
            return redirect(url_for("auth.register", lang_code=current_lang))

        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas.", "danger")
            return redirect(url_for("auth.register", lang_code=current_lang))

        if User.query.filter_by(email=email).first():
            flash("Cet email existe déjà.", "warning")
            return redirect(url_for("auth.register", lang_code=current_lang))

        hashed_password = generate_password_hash(password)

        new_user = User(
            email=email,
            password=hashed_password,
            is_verified=False
        )

        db.session.add(new_user)
        db.session.commit()

        try:
            send_verification_email(new_user, current_lang)
            flash("Compte créé avec succès. Vérifie ton email avant de te connecter.", "success")
        except Exception as e:
            current_app.logger.exception("Erreur envoi email verification")
            flash("Compte créé, mais l'email de confirmation n'a pas pu être envoyé.", "danger")

        return redirect(url_for("auth.login", lang_code=current_lang))

    return render_template("register.html")


# =========================
# EMAIL CONFIRMATION
# =========================
@auth_bp.route("/<lang_code>/confirm/<token>")
def confirm_email(lang_code, token):
    current_lang = get_lang(lang_code)

    try:
        email = confirm_token(token)
    except SignatureExpired:
        flash("Le lien de confirmation a expiré.", "warning")
        return redirect(url_for("auth.resend_verification", lang_code=current_lang))
    except BadSignature:
        flash("Lien de confirmation invalide.", "danger")
        return redirect(url_for("auth.login", lang_code=current_lang))

    user = User.query.filter_by(email=email).first()

    if not user:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("auth.register", lang_code=current_lang))

    if user.is_verified:
        flash("Ton email est déjà confirmé. Tu peux te connecter.", "success")
        return redirect(url_for("auth.login", lang_code=current_lang))

    user.is_verified = True
    db.session.commit()

    flash("Email confirmé avec succès. Tu peux maintenant te connecter.", "success")
    return redirect(url_for("auth.login", lang_code=current_lang))


# =========================
# RESEND VERIFICATION
# =========================
@auth_bp.route("/<lang_code>/resend-verification", methods=["GET", "POST"])
def resend_verification(lang_code):
    current_lang = get_lang(lang_code)

    if request.method == "POST":
        email_raw = request.form.get("email", "")

        if not email_raw.strip():
            flash("Merci d’entrer ton email.", "warning")
            return redirect(url_for("auth.resend_verification", lang_code=current_lang))

        try:
            email = normalize_and_validate_email(email_raw)
        except EmailNotValidError:
            flash("Veuillez entrer une adresse email valide.", "danger")
            return redirect(url_for("auth.resend_verification", lang_code=current_lang))

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("Aucun compte trouvé avec cet email.", "warning")
            return redirect(url_for("auth.resend_verification", lang_code=current_lang))

        if user.is_verified:
            flash("Cet email est déjà vérifié. Tu peux te connecter.", "success")
            return redirect(url_for("auth.login", lang_code=current_lang))

        try:
            send_verification_email(user, current_lang)
            flash("Un nouveau lien de confirmation a été envoyé.", "success")
        except Exception:
            current_app.logger.exception("Erreur renvoi email verification")
            flash("Impossible d'envoyer l'email de confirmation pour le moment.", "danger")

        return redirect(url_for("auth.login", lang_code=current_lang))

    return render_template("resend_verification.html")


# =========================
# RESET PASSWORD REQUEST
# =========================
@auth_bp.route("/<lang_code>/forgot-password", methods=["GET", "POST"])
def forgot_password(lang_code):
    current_lang = get_lang(lang_code)

    if request.method == "POST":
        email_raw = request.form.get("email", "")

        if not email_raw.strip():
            flash("Merci d’entrer ton email.", "warning")
            return redirect(url_for("auth.forgot_password", lang_code=current_lang))

        try:
            email = normalize_and_validate_email(email_raw)
        except EmailNotValidError:
            flash("Veuillez entrer une adresse email valide.", "danger")
            return redirect(url_for("auth.forgot_password", lang_code=current_lang))

        user = User.query.filter_by(email=email).first()

        if user:
            try:
                send_reset_password_email(user, current_lang)
            except Exception:
                current_app.logger.exception("Erreur envoi email reset password")
                flash("Impossible d'envoyer l'email de réinitialisation pour le moment.", "danger")
                return redirect(url_for("auth.forgot_password", lang_code=current_lang))

        flash("Si cet email existe, un lien de réinitialisation a été envoyé.", "success")
        return redirect(url_for("auth.login", lang_code=current_lang))

    return render_template("forgot_password.html")


# =========================
# RESET PASSWORD
# =========================
@auth_bp.route("/<lang_code>/reset-password/<token>", methods=["GET", "POST"])
def reset_password(lang_code, token):
    current_lang = get_lang(lang_code)

    try:
        email = confirm_reset_token(token)
    except SignatureExpired:
        flash("Le lien de réinitialisation a expiré.", "warning")
        return redirect(url_for("auth.forgot_password", lang_code=current_lang))
    except BadSignature:
        flash("Lien de réinitialisation invalide.", "danger")
        return redirect(url_for("auth.login", lang_code=current_lang))

    user = User.query.filter_by(email=email).first()

    if not user:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("auth.register", lang_code=current_lang))

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not password or not confirm_password:
            flash("Merci de remplir tous les champs.", "warning")
            return redirect(url_for("auth.reset_password", lang_code=current_lang, token=token))

        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "warning")
            return redirect(url_for("auth.reset_password", lang_code=current_lang, token=token))

        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas.", "danger")
            return redirect(url_for("auth.reset_password", lang_code=current_lang, token=token))

        user.password = generate_password_hash(password)
        db.session.commit()

        flash("Ton mot de passe a été réinitialisé avec succès. Tu peux maintenant te connecter.", "success")
        return redirect(url_for("auth.login", lang_code=current_lang))

    return render_template("reset_password.html", token=token)


# =========================
# LOGIN
# =========================
@auth_bp.route("/<lang_code>/login", methods=["GET", "POST"])
def login(lang_code):
    current_lang = get_lang(lang_code)

    if request.method == "POST":
        email_raw = request.form.get("email", "")
        password = request.form.get("password", "").strip()

        if not email_raw.strip() or not password:
            flash("Merci de remplir tous les champs.", "warning")
            return render_template("login.html")

        try:
            email = normalize_and_validate_email(email_raw)
        except EmailNotValidError:
            flash("Veuillez entrer une adresse email valide.", "danger")
            return render_template("login.html")

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash("Email ou mot de passe incorrect.", "danger")
            return render_template("login.html")

        if not user.is_verified:
            flash("Tu dois vérifier ton email avant de te connecter.", "warning")
            return redirect(url_for("auth.resend_verification", lang_code=current_lang))

        login_user(user)
        flash("Connexion réussie.", "success")
        return redirect(url_for("dashboard.dashboard", lang_code=current_lang))

    return render_template("login.html")


# =========================
# LOGOUT
# =========================
@auth_bp.route("/<lang_code>/logout")
@login_required
def logout(lang_code):
    current_lang = get_lang(lang_code)

    logout_user()
    flash("Tu es déconnecté.", "success")

    return redirect(url_for("main.home", lang_code=current_lang))