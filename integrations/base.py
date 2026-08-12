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
    def set_account_suspended(self, *, account_id, suspended, sending_enabled=False):
        raise NotImplementedError

    @abstractmethod
    def reset_account_password(self, *, account_id, password):
        raise NotImplementedError

    @abstractmethod
    def delete_account(self, *, account_id):
        raise NotImplementedError

    @abstractmethod
    def create_alias(self, *, address, destinations):
        raise NotImplementedError

    @abstractmethod
    def update_alias(self, *, alias_id, destinations):
        raise NotImplementedError

    @abstractmethod
    def delete_alias(self, *, alias_id):
        raise NotImplementedError
