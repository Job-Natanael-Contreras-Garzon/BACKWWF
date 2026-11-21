from app.core.config import settings
from app.integrations.email.base import EmailProvider, EmailSendError
from app.integrations.email.console import ConsoleEmailProvider
from app.integrations.email.resend import ResendEmailProvider


def get_email_provider() -> EmailProvider:
    if settings.EMAIL_PROVIDER == "resend":
        return ResendEmailProvider()
    return ConsoleEmailProvider()


__all__ = [
    "ConsoleEmailProvider",
    "EmailProvider",
    "EmailSendError",
    "ResendEmailProvider",
    "get_email_provider",
]
