from abc import ABC, abstractmethod

from events.domain.entities import DomainEvent


class EventRepository(ABC):

    @abstractmethod
    def save(self, event: DomainEvent):
        pass

    @abstractmethod
    def get_by_id(self, event_id):
        pass

    @abstractmethod
    def mark_published(self, event):
        pass
