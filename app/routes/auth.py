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


def build_absolute_url(endpoint, **values):
    base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")

    path = url_for(endpoint, **values)

    if base_url:
        return f"{base_url}{path}"

    return path


def send_verification_email(user, lang_code):
    token = generate_confirmation_token(user.email)

    confirm_url = build_absolute_url(
        "auth.confirm_email",
        token=token,
        lang_code=lang_code
    )

    html = f"""
    <div style="margin:0;padding:0;background:#05070b;font-family:Arial,sans-serif;">
      <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
        <div style="background:linear-gradient(180deg,#0b1220 0%,#09101b 100%);border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:40px 32px;box-shadow:0 20px 60px rgba(0,0,0,0.35);">

          <div style="margin-bottom:24px;">
            <div style="display:inline-block;padding:8px 12px;border-radius:999px;background:rgba(34,197,94,0.12);color:#86efac;font-size:12px;font-weight:700;letter-spacing:.04em;">
              VÉRIFICATION DE COMPTE
            </div>
          </div>

          <h1 style="margin:0 0 14px 0;color:#f8fafc;font-size:30px;line-height:1.2;font-weight:800;">
            Bienvenue sur VelWolef
          </h1>

          <p style="margin:0 0 18px 0;color:#cbd5e1;font-size:16px;line-height:1.7;">
            Merci d’avoir créé ton compte. Confirme ton adresse email pour activer ton accès et sécuriser ton espace.
          </p>

          <div style="margin:28px 0 30px 0;">
            <a href="{confirm_url}"
               style="display:inline-block;background:linear-gradient(135deg,#22c55e,#3b82f6);color:#ffffff;text-decoration:none;font-size:16px;font-weight:800;padding:14px 24px;border-radius:14px;">
              Confirmer mon compte
            </a>
          </div>

          <div style="margin:0 0 22px 0;padding:16px 18px;border-radius:14px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <p style="margin:0 0 8px 0;color:#f8fafc;font-size:14px;font-weight:700;">
              Pourquoi cet email ?
            </p>
            <p style="margin:0;color:#94a3b8;font-size:14px;line-height:1.6;">
              Tu reçois cet email car une demande de création de compte a été effectuée sur VelWolef.
            </p>
          </div>

          <p style="margin:0 0 8px 0;color:#94a3b8;font-size:13px;line-height:1.6;">
            Si le bouton ne fonctionne pas, copie ce lien dans ton navigateur :
          </p>

          <p style="margin:0 0 28px 0;word-break:break-all;">
            <a href="{confirm_url}" style="color:#60a5fa;font-size:13px;text-decoration:none;">{confirm_url}</a>
          </p>

          <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:0 0 20px 0;">

          <p style="margin:0 0 8px 0;color:#e2e8f0;font-size:13px;font-weight:700;">
            VelWolef
          </p>
          <p style="margin:0;color:#64748b;font-size:12px;line-height:1.6;">
            Plateforme de signaux trading, performance et academy.<br>
            support@velwolef.com
          </p>
        </div>
      </div>
    </div>
    """

    return send_email(
        to_email=user.email,
        subject="Confirme ton compte VelWolef",
        html=html
    )


def send_reset_password_email(user, lang_code):
    token = generate_reset_token(user.email)

    reset_url = build_absolute_url(
        "auth.reset_password",
        token=token,
        lang_code=lang_code
    )

    html = f"""
    <div style="margin:0;padding:0;background:#05070b;font-family:Arial,sans-serif;">
      <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
        <div style="background:linear-gradient(180deg,#0b1220 0%,#09101b 100%);border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:40px 32px;box-shadow:0 20px 60px rgba(0,0,0,0.35);">

          <div style="margin-bottom:24px;">
            <div style="display:inline-block;padding:8px 12px;border-radius:999px;background:rgba(239,68,68,0.12);color:#fca5a5;font-size:12px;font-weight:700;letter-spacing:.04em;">
              SÉCURITÉ COMPTE
            </div>
          </div>

          <h1 style="margin:0 0 14px 0;color:#f8fafc;font-size:30px;line-height:1.2;font-weight:800;">
            Réinitialisation du mot de passe
          </h1>

          <p style="margin:0 0 18px 0;color:#cbd5e1;font-size:16px;line-height:1.7;">
            Nous avons reçu une demande de réinitialisation pour ton compte VelWolef.
          </p>

          <p style="margin:0 0 24px 0;color:#94a3b8;font-size:14px;line-height:1.7;">
            Si tu es à l’origine de cette demande, clique sur le bouton ci-dessous pour choisir un nouveau mot de passe.
          </p>

          <div style="margin:28px 0 30px 0;">
            <a href="{reset_url}"
               style="display:inline-block;background:linear-gradient(135deg,#ef4444,#f97316);color:#ffffff;text-decoration:none;font-size:16px;font-weight:800;padding:14px 24px;border-radius:14px;">
              Réinitialiser mon mot de passe
            </a>
          </div>

          <div style="margin:0 0 22px 0;padding:16px 18px;border-radius:14px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <p style="margin:0 0 8px 0;color:#f8fafc;font-size:14px;font-weight:700;">
              Important
            </p>
            <p style="margin:0;color:#94a3b8;font-size:14px;line-height:1.6;">
              Si tu n’as pas demandé cette action, ignore simplement cet email. Ton mot de passe actuel restera inchangé.
            </p>
          </div>

          <p style="margin:0 0 8px 0;color:#94a3b8;font-size:13px;line-height:1.6;">
            Si le bouton ne fonctionne pas, copie ce lien dans ton navigateur :
          </p>

          <p style="margin:0 0 28px 0;word-break:break-all;">
            <a href="{reset_url}" style="color:#60a5fa;font-size:13px;text-decoration:none;">{reset_url}</a>
          </p>

          <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:0 0 20px 0;">

          <p style="margin:0 0 8px 0;color:#e2e8f0;font-size:13px;font-weight:700;">
            VelWolef
          </p>
          <p style="margin:0;color:#64748b;font-size:12px;line-height:1.6;">
            Plateforme de signaux trading, performance et academy.<br>
            support@velwolef.com
          </p>
        </div>
      </div>
    </div>
    """

    return send_email(
        to_email=user.email,
        subject="Réinitialisation de ton mot de passe VelWolef",
        html=html
    )


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
        except Exception:
            current_app.logger.exception("Erreur envoi email verification")
            flash("Compte créé, mais l'email de confirmation n'a pas pu être envoyé.", "danger")

        return redirect(url_for("auth.login", lang_code=current_lang))

    return render_template("register.html")


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


@auth_bp.route("/<lang_code>/logout")
@login_required
def logout(lang_code):
    current_lang = get_lang(lang_code)

    logout_user()
    flash("Tu es déconnecté.", "success")

    return redirect(url_for("main.home", lang_code=current_lang))