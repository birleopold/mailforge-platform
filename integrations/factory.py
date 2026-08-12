import os

from integrations.base import MailBackend
from integrations.stalwart.client import StalwartClient


class UnsupportedMailBackend(RuntimeError):
    pass


class MailBackendConfigurationError(RuntimeError):
    pass


def get_mail_backend() -> MailBackend:
    backend_name = os.environ.get("MAIL_BACKEND", "stalwart").strip().lower()
    if backend_name != "stalwart":
        raise UnsupportedMailBackend(f"Unsupported mail backend: {backend_name}")

    try:
        return StalwartClient()
    except KeyError as exc:
        raise MailBackendConfigurationError(
            "Stalwart backend is not configured. Set STALWART_BASE_URL and STALWART_API_TOKEN."
        ) from exc
