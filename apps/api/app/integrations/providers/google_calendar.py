"""Google Calendar (https://developers.google.com/workspace/calendar/api/v3/reference).

* Connect: OAuth 2.0 authorization code + PKCE; offline access for a refresh token.
  Scopes: calendar.events (create/update/delete the business's own events) and
  calendar.freebusy (busy times only; event details are never read for availability).
* Test connection / availability: POST /freeBusy (read-only).
* Events: POST /calendars/{id}/events with a client-supplied event id derived from the
  booking id (base32hex), so a retried insert returns 409 instead of a second event;
  PATCH to reschedule; DELETE to cancel (404/410 mean it is already gone).
* sendUpdates=all asks Google to email the invitation to attendees (the customer) only
  when the booking carries a verified email address.
"""

import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from app.core.config import Settings
from app.integrations.errors import IntegrationError
from app.integrations.providers.base import credential, ok
from app.integrations.registry import (
    CalendarProvider,
    ConfigField,
    ConfigurationInvalid,
    HealthResult,
    IntegrationDefinition,
    OAuthSpec,
    ProviderContext,
)

EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
BASE32HEX = frozenset("0123456789abcdefghijklmnopqrstuv")

DEFINITION = IntegrationDefinition(
    key="google_calendar",
    name="Google Calendar",
    description="Check free times and add bookings to your Google Calendar.",
    category="calendar",
    provider="Google",
    auth_type="oauth2_pkce",
    capabilities=("calendar_events", "free_busy"),
    supported_scopes=(EVENTS_SCOPE, FREEBUSY_SCOPE),
    required_scopes=(EVENTS_SCOPE, FREEBUSY_SCOPE),
    documentation_url="https://developers.google.com/workspace/calendar/api/v3/reference",
    config_schema=(
        ConfigField(
            "calendar_id",
            "Calendar",
            required=False,
            help="Leave empty to use the connected account's main calendar",
            max_length=200,
        ),
    ),
    oauth=OAuthSpec(
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://oauth2.googleapis.com/revoke",
        client_id_setting="google_oauth_client_id",
        client_secret_setting="google_oauth_client_secret",
        # A refresh token is only issued for offline access with explicit consent.
        extra_authorize_params=(("access_type", "offline"), ("prompt", "consent")),
    ),
)


def event_id(booking_id: Any) -> str:
    """Deterministic Google event id for a booking (UUID hex is valid base32hex)."""
    value = "pi" + str(booking_id).replace("-", "").lower()
    assert set(value) <= BASE32HEX and 5 <= len(value) <= 1024
    return value


def _rfc3339(at: datetime) -> str:
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise IntegrationError(
            "INVALID_RESPONSE", "Google returned an unexpected time", kind="invalid_response"
        ) from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class GoogleCalendarProvider(CalendarProvider):
    key = "google_calendar"
    capabilities = frozenset(DEFINITION.capabilities)

    def validate_configuration(
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        calendar = str(config.get("calendar_id") or "")
        if calendar and ("/" in calendar or len(calendar) > 200):
            raise ConfigurationInvalid("Enter a valid calendar ID", "calendar_id")

    @staticmethod
    def _base(ctx: ProviderContext) -> str:
        return ctx.settings.google_calendar_api_base_url.rstrip("/")

    @staticmethod
    def _headers(ctx: ProviderContext) -> dict[str, str]:
        return {"authorization": f"Bearer {credential(ctx.credentials, 'access_token')}"}

    @staticmethod
    def calendar(ctx: ProviderContext) -> str:
        return str(ctx.config.get("calendar_id") or "primary")

    def _events_url(self, ctx: ProviderContext, event: str | None = None) -> str:
        url = f"{self._base(ctx)}/calendars/{quote(self.calendar(ctx), safe='@.')}/events"
        return f"{url}/{quote(event, safe='')}" if event else url

    async def busy(
        self, ctx: ProviderContext, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        """Busy intervals only. Any calendar-level error is a failure, never 'all free'."""
        calendar = self.calendar(ctx)
        response = await ctx.http.request(
            "POST",
            f"{self._base(ctx)}/freeBusy",
            headers=self._headers(ctx),
            json_body={
                "timeMin": _rfc3339(start),
                "timeMax": _rfc3339(end),
                "items": [{"id": calendar}],
            },
            max_bytes=256 * 1024,
            context=ctx.call,
        )
        data = response.ensure_success().json_object()
        calendars = data.get("calendars")
        entry = calendars.get(calendar) if isinstance(calendars, dict) else None
        if not isinstance(entry, dict) or entry.get("errors"):
            raise IntegrationError(
                "CALENDAR_UNREADABLE",
                "Google could not share this calendar's busy times",
                kind="invalid_response",
            )
        return [(_parse(b.get("start")), _parse(b.get("end"))) for b in entry.get("busy") or []]

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        started = time.perf_counter()
        now = datetime.now(UTC)
        await self.busy(ctx, now, now + timedelta(hours=1))
        return ok("Google Calendar reachable", int((time.perf_counter() - started) * 1000))

    async def list_events(
        self, ctx: ProviderContext, start: datetime, end: datetime
    ) -> list[Mapping[str, Any]]:
        return [
            {"start": s.isoformat(), "end": e.isoformat()}
            for s, e in await self.busy(ctx, start, end)
        ]

    async def get_event(self, ctx: ProviderContext, event: str) -> Mapping[str, Any] | None:
        response = await ctx.http.request(
            "GET", self._events_url(ctx, event), headers=self._headers(ctx), context=ctx.call
        )
        if response.status_code in (404, 410):
            return None
        return response.ensure_success().json_object()

    async def create_event(
        self, ctx: ProviderContext, event: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Insert with a client-supplied id. A duplicate (409) means an earlier attempt
        succeeded: the existing event is returned, never a second one."""
        notify = "all" if event.get("attendees") else "none"
        response = await ctx.http.request(
            "POST",
            self._events_url(ctx),
            headers=self._headers(ctx),
            params={"sendUpdates": notify},
            json_body=dict(event),
            context=ctx.call,
        )
        if response.status_code == 409:
            existing = await self.get_event(ctx, str(event["id"]))
            if existing is None:
                raise IntegrationError(
                    "EVENT_CONFLICT", "Google reported a conflicting event id", kind="permanent"
                )
            return existing
        return response.ensure_success().json_object()

    async def update_event(
        self, ctx: ProviderContext, event: str, changes: Mapping[str, Any], notify: bool
    ) -> Mapping[str, Any] | None:
        response = await ctx.http.request(
            "PATCH",
            self._events_url(ctx, event),
            headers=self._headers(ctx),
            params={"sendUpdates": "all" if notify else "none"},
            json_body=dict(changes),
            context=ctx.call,
        )
        if response.status_code in (404, 410):
            return None
        return response.ensure_success().json_object()

    async def delete_event(self, ctx: ProviderContext, event: str, notify: bool) -> None:
        response = await ctx.http.request(
            "DELETE",
            self._events_url(ctx, event),
            headers=self._headers(ctx),
            params={"sendUpdates": "all" if notify else "none"},
            context=ctx.call,
        )
        if response.status_code in (404, 410):
            return  # Already deleted: the desired state is reached.
        response.ensure_success()
