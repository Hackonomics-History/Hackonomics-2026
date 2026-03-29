from events.domain.entities import DomainEvent


class UserEventPublisher:

    @staticmethod
    def user_signed_up(user) -> DomainEvent:
        return DomainEvent(
            aggregate_type="User",
            aggregate_id=user.ory_id,
            event_type="USER_SIGNUP",
            payload={
                "ory_id": user.ory_id,
                "email": user.email,
            },
        )
