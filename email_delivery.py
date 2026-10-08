import os
import smtplib
import ssl
from email.message import EmailMessage


class EmailDeliveryError(RuntimeError):
    """Raised when the daily digest cannot be delivered."""


def send_digest(subject: str, body: str) -> bool:
    sender = os.environ.get("JOBHUNT_EMAIL_FROM", "").strip()
    recipient = os.environ.get("JOBHUNT_EMAIL_TO", "").strip()
    password = os.environ.get("JOBHUNT_EMAIL_PASSWORD", "").strip().replace(" ", "")
    configured = (bool(sender), bool(recipient), bool(password))
    if not any(configured):
        return False
    if not all(configured):
        raise EmailDeliveryError(
            "Set JOBHUNT_EMAIL_FROM, JOBHUNT_EMAIL_TO, and JOBHUNT_EMAIL_PASSWORD to enable email."
        )

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(sender, password)
            refused = smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError(f"Could not send the job digest: {exc}") from exc
    if refused:
        raise EmailDeliveryError(f"Gmail refused delivery to: {', '.join(refused)}")
    return True
