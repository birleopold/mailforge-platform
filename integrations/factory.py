import os

from integrations.base import MailBackend
from integrations.stalwart.client import StalwartClient


class UnsupportedMailBackend(RuntimeError):
    pass


def get_mail_backend() -> MailBackend:
    backend_name = os.environ.get("MAIL_BACKEND", "stalwart").strip().lower()
    if backend_name == "stalwart":
        return StalwartClient()
    raise UnsupportedMailBackend(f"Unsupported mail backend: {backend_name}")
