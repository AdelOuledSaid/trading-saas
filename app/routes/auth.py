from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from email_validator import validate_email, EmailNotValidError
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models import User
from app.services.email_service import send_email

auth_bp = Blueprint("auth", __name__)

SUPPORTED_LANGS = ["fr", "en", "es", "de", "it", "pt", "ru"]
DEFAULT_LANG = "en"

# ─────────────────────────────────────────────────────────────────────────────
# Rate-limit : on garde en mémoire le dernier envoi par email.
# Délai minimum entre deux envois : 2 minutes.
# ─────────────────────────────────────────────────────────────────────────────
_verification_email_last_sent: dict[str, datetime] = {}
_RESEND_COOLDOWN = timedelta(minutes=2)


def _can_send_verification(email: str) -> bool:
    """Retourne True si aucun email de vérification n'a été envoyé
    dans les 2 dernières minutes pour cet email."""
    last = _verification_email_last_sent.get(email)
    if last is None:
        return True
    return datetime.now(timezone.utc) - last > _RESEND_COOLDOWN


def _mark_verification_sent(email: str) -> None:
    """Enregistre l'heure d'envoi pour cet email."""
    _verification_email_last_sent[email] = datetime.now(timezone.utc)


EMAIL_VERIFY_TEXTS = {
    "fr": {
        "subject": "Bienvenue sur Velwolef – Confirme ton adresse email",
        "badge": "VÉRIFICATION DE COMPTE",
        "title": "Bienvenue sur Velwolef 🚀",
        "intro": "Merci de rejoindre Velwolef. Confirme ton adresse email pour activer ton compte et accéder à toutes les fonctionnalités de la plateforme.",
        "button": "Confirmer mon email",
        "copy": "Si le bouton ne fonctionne pas, copie et colle ce lien dans ton navigateur :",
        "why_title": "Pourquoi cet email ?",
        "why_text": "Cet email a été envoyé car un compte Velwolef a été créé avec cette adresse email. Si ce n'est pas toi, tu peux ignorer ce message.",
    },

    "en": {
        "subject": "Welcome to Velwolef – Confirm your email",
        "badge": "ACCOUNT VERIFICATION",
        "title": "Welcome to Velwolef 🚀",
        "intro": "Thank you for joining Velwolef. Please confirm your email address to activate your account and start receiving trading signals, platform updates, and exclusive features.",
        "button": "Confirm My Email",
        "copy": "If the button does not work, copy and paste this link into your browser:",
        "why_title": "Why did you receive this email?",
        "why_text": "This email was sent because a Velwolef account was created using this email address. If you did not create an account, you can safely ignore this message.",
    },

    "es": {
        "subject": "Bienvenido a Velwolef – Confirma tu correo electrónico",
        "badge": "VERIFICACIÓN DE CUENTA",
        "title": "Bienvenido a Velwolef 🚀",
        "intro": "Gracias por unirte a Velwolef. Confirma tu correo electrónico para activar tu cuenta y acceder a todas las funciones de la plataforma.",
        "button": "Confirmar mi correo",
        "copy": "Si el botón no funciona, copia y pega este enlace en tu navegador:",
        "why_title": "¿Por qué recibiste este correo?",
        "why_text": "Este correo fue enviado porque se creó una cuenta de Velwolef con esta dirección de correo electrónico.",
    },

    "de": {
        "subject": "Willkommen bei Velwolef – Bestätige deine E-Mail",
        "badge": "KONTOBESTÄTIGUNG",
        "title": "Willkommen bei Velwolef 🚀",
        "intro": "Danke, dass du Velwolef beigetreten bist. Bitte bestätige deine E-Mail-Adresse, um dein Konto zu aktivieren.",
        "button": "E-Mail bestätigen",
        "copy": "Falls der Button nicht funktioniert, kopiere diesen Link in deinen Browser:",
        "why_title": "Warum erhältst du diese E-Mail?",
        "why_text": "Diese E-Mail wurde gesendet, weil mit dieser Adresse ein Velwolef-Konto erstellt wurde.",
    },

    "it": {
        "subject": "Benvenuto su Velwolef – Conferma la tua email",
        "badge": "VERIFICA ACCOUNT",
        "title": "Benvenuto su Velwolef 🚀",
        "intro": "Grazie per esserti unito a Velwolef. Conferma la tua email per attivare il tuo account.",
        "button": "Conferma la mia email",
        "copy": "Se il pulsante non funziona, copia e incolla questo link nel browser:",
        "why_title": "Perché hai ricevuto questa email?",
        "why_text": "Questa email è stata inviata perché è stato creato un account Velwolef con questo indirizzo email.",
    },

    "pt": {
        "subject": "Bem-vindo ao Velwolef – Confirme seu email",
        "badge": "VERIFICAÇÃO DE CONTA",
        "title": "Bem-vindo ao Velwolef 🚀",
        "intro": "Obrigado por se juntar ao Velwolef. Confirme seu email para ativar sua conta.",
        "button": "Confirmar meu email",
        "copy": "Se o botão não funcionar, copie e cole este link no navegador:",
        "why_title": "Por que você recebeu este email?",
        "why_text": "Este email foi enviado porque uma conta Velwolef foi criada usando este endereço de email.",
    },

    "ru": {
        "subject": "Добро пожаловать в Velwolef – Подтвердите email",
        "badge": "ПОДТВЕРЖДЕНИЕ АККАУНТА",
        "title": "Добро пожаловать в Velwolef 🚀",
        "intro": "Спасибо за регистрацию в Velwolef. Подтвердите свой email, чтобы активировать аккаунт.",
        "button": "Подтвердить email",
        "copy": "Если кнопка не работает, скопируйте и вставьте эту ссылку в браузер:",
        "why_title": "Почему вы получили это письмо?",
        "why_text": "Это письмо было отправлено, потому что с этим адресом электронной почты был создан аккаунт Velwolef.",
    },
}

def get_lang(lang_code):
    if lang_code in SUPPORTED_LANGS:
        session["lang"] = lang_code
        return lang_code

    session_lang = session.get("lang")
    if session_lang in SUPPORTED_LANGS:
        return session_lang

    session["lang"] = DEFAULT_LANG
    return DEFAULT_LANG


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
    base_url = (
        current_app.config.get("APP_BASE_URL")
        or current_app.config.get("SITE_URL")
        or current_app.config.get("DOMAIN")
        or "https://www.velwolef.com"
    ).rstrip("/")

    path = url_for(endpoint, **values)
    return f"{base_url}{path}"


def send_verification_email(user, lang_code):
    token = generate_confirmation_token(user.email)

    confirm_url = build_absolute_url(
        "auth.confirm_email",
        token=token,
        lang_code=lang_code
    )

    texts = EMAIL_VERIFY_TEXTS.get(lang_code, EMAIL_VERIFY_TEXTS["en"])

    html = f"""
    <div style="margin:0;padding:0;background:#05070b;font-family:Arial,sans-serif;">
      <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
        <div style="background:linear-gradient(180deg,#0b1220 0%,#09101b 100%);border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:40px 32px;box-shadow:0 20px 60px rgba(0,0,0,0.35);">

          <div style="margin-bottom:24px;">
            <div style="display:inline-block;padding:8px 12px;border-radius:999px;background:rgba(34,197,94,0.12);color:#86efac;font-size:12px;font-weight:700;letter-spacing:.04em;">
              {texts["badge"]}
            </div>
          </div>

          <h1 style="margin:0 0 14px 0;color:#f8fafc;font-size:30px;line-height:1.2;font-weight:800;">
            {texts["title"]}
          </h1>

          <p style="margin:0 0 18px 0;color:#cbd5e1;font-size:16px;line-height:1.7;">
            {texts["intro"]}
          </p>

          <div style="margin:28px 0 30px 0;">
            <a href="{confirm_url}"
               style="display:inline-block;background:linear-gradient(135deg,#22c55e,#3b82f6);color:#ffffff;text-decoration:none;font-size:16px;font-weight:800;padding:14px 24px;border-radius:14px;">
              {texts["button"]}
            </a>
          </div>

          <div style="margin:0 0 22px 0;padding:16px 18px;border-radius:14px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <p style="margin:0 0 8px 0;color:#f8fafc;font-size:14px;font-weight:700;">
              {texts["why_title"]}
            </p>
            <p style="margin:0;color:#94a3b8;font-size:14px;line-height:1.6;">
              {texts["why_text"]}
            </p>
          </div>

          <p style="margin:0 0 8px 0;color:#94a3b8;font-size:13px;line-height:1.6;">
            {texts["copy"]}
          </p>

          <p style="margin:0 0 28px 0;word-break:break-all;">
            <a href="{confirm_url}" style="color:#60a5fa;font-size:13px;text-decoration:none;">{confirm_url}</a>
          </p>

          <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:0 0 20px 0;">

          <p style="margin:0 0 8px 0;color:#e2e8f0;font-size:13px;font-weight:700;">
            VelWolef
          </p>
          <p style="margin:0;color:#64748b;font-size:12px;line-height:1.6;">
            Professional Trading Signals & Analytics Platform<br>
            support@velwolef.com<br>
            www.velwolef.com
          </p>
        </div>
      </div>
    </div>
    """

    return send_email(
        to_email=user.email,
        subject=texts["subject"],
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
              ACCOUNT SECURITY
            </div>
          </div>

          <h1 style="margin:0 0 14px 0;color:#f8fafc;font-size:30px;line-height:1.2;font-weight:800;">
            Password reset
          </h1>

          <p style="margin:0 0 18px 0;color:#cbd5e1;font-size:16px;line-height:1.7;">
            We received a password reset request for your VelWolef account.
          </p>

          <p style="margin:0 0 24px 0;color:#94a3b8;font-size:14px;line-height:1.7;">
            If you requested this action, click the button below to choose a new password.
          </p>

          <div style="margin:28px 0 30px 0;">
            <a href="{reset_url}"
               style="display:inline-block;background:linear-gradient(135deg,#ef4444,#f97316);color:#ffffff;text-decoration:none;font-size:16px;font-weight:800;padding:14px 24px;border-radius:14px;">
              Reset my password
            </a>
          </div>

          <div style="margin:0 0 22px 0;padding:16px 18px;border-radius:14px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <p style="margin:0 0 8px 0;color:#f8fafc;font-size:14px;font-weight:700;">
              Important
            </p>
            <p style="margin:0;color:#94a3b8;font-size:14px;line-height:1.6;">
              If you did not request this action, simply ignore this email. Your current password will remain unchanged.
            </p>
          </div>

          <p style="margin:0 0 8px 0;color:#94a3b8;font-size:13px;line-height:1.6;">
            If the button does not work, copy this link into your browser:
          </p>

          <p style="margin:0 0 28px 0;word-break:break-all;">
            <a href="{reset_url}" style="color:#60a5fa;font-size:13px;text-decoration:none;">{reset_url}</a>
          </p>

          <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:0 0 20px 0;">

          <p style="margin:0 0 8px 0;color:#e2e8f0;font-size:13px;font-weight:700;">
            VelWolef
          </p>
          <p style="margin:0;color:#64748b;font-size:12px;line-height:1.6;">
            Trading signals, performance and academy platform.<br>
            support@velwolef.com
          </p>
        </div>
      </div>
    </div>
    """

    return send_email(
        to_email=user.email,
        subject="Reset your VelWolef password",
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
            flash("Please fill in all fields.", "warning")
            return redirect(url_for("auth.register", lang_code=current_lang))

        try:
            email = normalize_and_validate_email(email_raw)
        except EmailNotValidError:
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("auth.register", lang_code=current_lang))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "warning")
            return redirect(url_for("auth.register", lang_code=current_lang))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.register", lang_code=current_lang))

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            if not existing_user.is_verified:
                # ── FIX : on n'envoie un email que si le cooldown est écoulé ──
                if not _can_send_verification(email):
                    flash("Account already created but not verified. A verification email was already sent recently, please check your inbox (and Spam folder).", "warning")
                    return redirect(url_for("auth.login", lang_code=current_lang))

                try:
                    send_verification_email(existing_user, current_lang)
                    _mark_verification_sent(email)
                    flash("Account already created but not verified. A new verification email has been sent.", "success")
                except Exception:
                    current_app.logger.exception("Erreur renvoi email verification")
                    flash("Account already created but the verification email could not be sent right now.", "danger")

                return redirect(url_for("auth.login", lang_code=current_lang))

            flash("This email already exists. Please log in.", "warning")
            return redirect(url_for("auth.login", lang_code=current_lang))

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
            _mark_verification_sent(email)
            flash("✅ Account created successfully. A verification email has been sent to your inbox. Please also check your Spam/Junk folder. Sender: support@velwolef.com","success")
        except Exception:
            current_app.logger.exception("Erreur envoi email verification")
            flash("Account created, but the verification email could not be sent.", "danger")

        return redirect(url_for("auth.login", lang_code=current_lang))

    return render_template("register.html")


@auth_bp.route("/<lang_code>/confirm/<token>")
def confirm_email(lang_code, token):
    current_lang = get_lang(lang_code)

    try:
        email = confirm_token(token)
    except SignatureExpired:
        flash("The confirmation link has expired.", "warning")
        return redirect(url_for("auth.resend_verification", lang_code=current_lang))
    except BadSignature:
        flash("Invalid confirmation link.", "danger")
        return redirect(url_for("auth.login", lang_code=current_lang))

    user = User.query.filter_by(email=email).first()

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("auth.register", lang_code=current_lang))

    if user.is_verified:
        flash("Your email is already confirmed. You can log in.", "success")
        return redirect(url_for("auth.login", lang_code=current_lang))

    user.is_verified = True
    db.session.commit()

    flash("Email confirmed successfully. You can now log in.", "success")
    return redirect(url_for("auth.login", lang_code=current_lang))


@auth_bp.route("/<lang_code>/resend-verification", methods=["GET", "POST"])
def resend_verification(lang_code):
    current_lang = get_lang(lang_code)

    if request.method == "POST":
        email_raw = request.form.get("email", "")

        if not email_raw.strip():
            flash("Please enter your email.", "warning")
            return redirect(url_for("auth.resend_verification", lang_code=current_lang))

        try:
            email = normalize_and_validate_email(email_raw)
        except EmailNotValidError:
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("auth.resend_verification", lang_code=current_lang))

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("No account found with this email.", "warning")
            return redirect(url_for("auth.resend_verification", lang_code=current_lang))

        if user.is_verified:
            flash("This email is already verified. You can log in.", "success")
            return redirect(url_for("auth.login", lang_code=current_lang))

        # ── FIX : même protection sur le renvoi manuel ──
        if not _can_send_verification(email):
            flash("A verification email was already sent recently. Please check your inbox and Spam/Junk folder.", "warning")
            return redirect(url_for("auth.login", lang_code=current_lang))

        try:
            send_verification_email(user, current_lang)
            _mark_verification_sent(email)
            flash("A new verification email has been sent.", "success")
        except Exception:
            current_app.logger.exception("Erreur renvoi email verification")
            flash("Unable to send the verification email right now.", "danger")

        return redirect(url_for("auth.login", lang_code=current_lang))

    return render_template("resend_verification.html")


@auth_bp.route("/<lang_code>/forgot-password", methods=["GET", "POST"])
def forgot_password(lang_code):
    current_lang = get_lang(lang_code)

    if request.method == "POST":
        email_raw = request.form.get("email", "")

        if not email_raw.strip():
            flash("Please enter your email.", "warning")
            return redirect(url_for("auth.forgot_password", lang_code=current_lang))

        try:
            email = normalize_and_validate_email(email_raw)
        except EmailNotValidError:
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("auth.forgot_password", lang_code=current_lang))

        user = User.query.filter_by(email=email).first()

        if user:
            try:
                send_reset_password_email(user, current_lang)
            except Exception:
                current_app.logger.exception("Erreur envoi email reset password")
                flash("Unable to send the password reset email right now.", "danger")
                return redirect(url_for("auth.forgot_password", lang_code=current_lang))

        flash("If this email exists, a password reset link has been sent.", "success")
        return redirect(url_for("auth.login", lang_code=current_lang))

    return render_template("forgot_password.html")


@auth_bp.route("/<lang_code>/reset-password/<token>", methods=["GET", "POST"])
def reset_password(lang_code, token):
    current_lang = get_lang(lang_code)

    try:
        email = confirm_reset_token(token)
    except SignatureExpired:
        flash("The password reset link has expired.", "warning")
        return redirect(url_for("auth.forgot_password", lang_code=current_lang))
    except BadSignature:
        flash("Invalid password reset link.", "danger")
        return redirect(url_for("auth.login", lang_code=current_lang))

    user = User.query.filter_by(email=email).first()

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("auth.register", lang_code=current_lang))

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not password or not confirm_password:
            flash("Please fill in all fields.", "warning")
            return redirect(url_for("auth.reset_password", lang_code=current_lang, token=token))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "warning")
            return redirect(url_for("auth.reset_password", lang_code=current_lang, token=token))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.reset_password", lang_code=current_lang, token=token))

        user.password = generate_password_hash(password)
        db.session.commit()

        flash("Your password has been reset successfully. You can now log in.", "success")
        return redirect(url_for("auth.login", lang_code=current_lang))

    return render_template("reset_password.html", token=token)


@auth_bp.route("/<lang_code>/login", methods=["GET", "POST"])
def login(lang_code):
    current_lang = get_lang(lang_code)

    if request.method == "POST":
        email_raw = request.form.get("email", "")
        password = request.form.get("password", "").strip()

        if not email_raw.strip() or not password:
            flash("Please fill in all fields.", "warning")
            return render_template("login.html")

        try:
            email = normalize_and_validate_email(email_raw)
        except EmailNotValidError:
            flash("Please enter a valid email address.", "danger")
            return render_template("login.html")

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

        if not user.is_verified:
            flash("⚠️ Your email address has not been verified yet. Please check your inbox and Spam/Junk folder, or request a new verification email.","warning")
            return redirect(url_for("auth.resend_verification", lang_code=current_lang))

        login_user(user)
        flash("Login successful.", "success")
        return redirect(url_for("dashboard.dashboard", lang_code=current_lang))

    return render_template("login.html")


@auth_bp.route("/<lang_code>/logout")
@login_required
def logout(lang_code):
    current_lang = get_lang(lang_code)

    logout_user()
    flash("You have been logged out.", "success")

    return redirect(url_for("main.home", lang_code=current_lang))