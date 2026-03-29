from abc import ABC, abstractmethod
from typing import Optional

from accounts.domain.entities import Account


class AccountRepository(ABC):
    @abstractmethod
    def find_by_user_id(self, user_id: str) -> Optional[Account]:
        raise NotImplementedError

    @abstractmethod
    def save(self, account: Account) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_all_country_codes(self) -> list[str]:
        raise NotImplementedError
