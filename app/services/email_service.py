import resend
from flask import current_app


def send_email(to_email, subject, html):
    api_key = current_app.config.get("RESEND_API_KEY")

    # 🔥 sécurité clé
    if not api_key:
        current_app.logger.error("RESEND_API_KEY manquante")
        raise Exception("RESEND_API_KEY manquante")

    resend.api_key = api_key

    current_app.logger.info("Sending email to: %s", to_email)

    try:
        response = resend.Emails.send({
            "from": "VelWolef <support@velwolef.com>",
            "to": [to_email],
            "subject": subject,
            "html": html
        })

        current_app.logger.info("Resend OK: %s", response)
        return response

    except Exception as e:
        current_app.logger.exception("Erreur envoi email Resend")
        raise e