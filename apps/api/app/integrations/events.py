"""The single catalog of platform domain event types (outbox + outbound webhooks)."""

from typing import Final

EVENT_TYPES: Final[dict[str, str]] = {
    "notification.created": "A workspace notification was created",
    "customer.created": "A customer was created",
    "customer.updated": "A customer was updated",
    "order.created": "An order was created",
    "order.confirmed": "An order was confirmed",
    "order.cancelled": "An order was cancelled",
    "order.fulfilled": "An order was fulfilled",
    "quote.sent": "A quote was sent",
    "quote.approved": "A quote was approved",
    "invoice.issued": "An invoice was issued",
    "invoice.paid": "An invoice was paid in full",
    "payment.received": "A payment was recorded",
    "inventory.low": "Stock fell below its reorder level",
    "handoff.created": "A conversation was handed off to a person",
    "handoff.resolved": "A handoff was resolved",
    "pi.message.received": "PI received a customer message",
    "pi.message.sent": "PI sent a message",
    "integration.connected": "An integration connection was verified",
    "integration.failed": "An integration connection started failing",
    "integration.disconnected": "An integration connection was disconnected",
}


def is_known(event_type: str) -> bool:
    return event_type in EVENT_TYPES
