from abc import ABC, abstractmethod


class MailBackend(ABC):
    @abstractmethod
    def create_domain(self, *, domain, max_mailboxes, quota_mb):
        raise NotImplementedError

    @abstractmethod
    def create_mailbox(
        self,
        *,
        email,
        password,
        quota_mb,
        display_name="",
        sending_enabled=True,
    ):
        raise NotImplementedError

    @abstractmethod
    def set_account_sending_enabled(self, *, account_id, enabled):
        raise NotImplementedError

    @abstractmethod
    def suspend_mailbox(self, *, email):
        raise NotImplementedError

    @abstractmethod
    def create_alias(self, *, address, destinations):
        raise NotImplementedError
