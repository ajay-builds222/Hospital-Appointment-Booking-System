import logging
import smtplib
from email.message import EmailMessage
from app.database import settings

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, body: str):
    if not settings.smtp_username or not settings.smtp_password:
        logger.warning("Email not sent: SMTP credentials are not configured.")
        return
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_username
    message["To"] = to_email
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except Exception:
        logger.exception("Email delivery failed for %s", to_email)
