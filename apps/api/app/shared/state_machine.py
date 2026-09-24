from collections.abc import Mapping

from app.shared.errors import InvalidTransition


class StateMachine:
    """Explicit allowed transitions; anything unlisted is rejected."""

    def __init__(self, entity: str, transitions: Mapping[str, frozenset[str]]) -> None:
        self.entity = entity
        self.transitions = transitions

    @property
    def states(self) -> frozenset[str]:
        return frozenset(self.transitions)

    def can(self, current: str, target: str) -> bool:
        return target in self.transitions.get(current, frozenset())

    def ensure(self, current: str, target: str) -> None:
        if not self.can(current, target):
            raise InvalidTransition(self.entity, current, target)

    def next_states(self, current: str) -> list[str]:
        return sorted(self.transitions.get(current, frozenset()))
