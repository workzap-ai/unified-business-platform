# Pi tool connections: Google Calendar, Shopify, booking email

Status on 29 September 2026: code complete, verified only with HTTP doubles
(`apps/api/tests/integration/test_pi_connectors.py`, `apps/pi/tests/connectors.spec.ts`).
**No live Google, Shopify or email provider has been exercised yet.** See "Live verification
still needed" below.

## What a business sees

Pi app → My Pi → Tools → **Your accounts**. There are two cards: Google Calendar and
Shopify. Each card shows the status the server reports: Not connected, Not finished,
Connected, Needs attention, or Not available yet (the server has no app credentials).
Owners and admins (`integrations.manage`) can connect, test and disconnect. Other roles
can only see the status. No tokens, client IDs or provider account IDs are shown.

## How it works

| Piece | File |
| --- | --- |
| Google Calendar adapter (freeBusy, events insert/get/patch/delete) | `apps/api/app/integrations/providers/google_calendar.py` |
| Shopify adapter (GraphQL Admin API: shop, customers, orders) | `apps/api/app/integrations/providers/shopify.py` |
| Connect/callback/refresh/test/disconnect for the Pi app | `apps/api/app/modules/pi_saas/connectors.py`, `connector_routes.py` |
| Busy times and after-commit event sync | `apps/api/app/modules/pi_saas/calendar_sync.py` (job `sweep_pi_calendar`) |
| Pi tools | `apps/api/app/modules/pi/tools/connector_handlers.py`, `work_handlers.py` |
| UI | `apps/pi/src/features/connectors.tsx` (rendered in `my-pi.tsx`) |

The connections are ordinary integration connections. Credentials are encrypted, and
health, the circuit breaker, rate limits and audit apply. Owner OS operators therefore
see the same records.

### Google Calendar

- **Connect.** Authorization code with PKCE, `access_type=offline` and
  `prompt=consent`. The scopes are `calendar.events` and `calendar.freebusy`. The single-use
  state is bound to the same user, business and environment. A session from a different
  business can neither complete the authorization nor consume the state.
- **Availability.** The business calendar's busy times are removed from the offered
  slots, and they are read again just before a booking is written. If the calendar is
  connected but can't be read, the tools refuse with `CALENDAR_UNAVAILABLE`, and Pi hands the
  conversation to the team. An unreadable calendar is never treated as "all free".
- **Event sync.** Sync runs after the booking commits, never inside the customer's run
  transaction. The event id is derived from the booking id (`pi` + UUID hex, valid
  base32hex). A retry after an uncertain outcome gets 409, reads the existing event and
  never creates a second one. A reschedule patches the event and a cancellation deletes it.
  The booking's `external_sync` field moves from `pending` to `synced` or `failed`.
  Retries stop once the appointment has ended.
- **Invitations.** A customer is invited only when the CRM record holds a valid email
  address, and then `sendUpdates=all`. Google sends the invitation email itself.
- **Tokens.** Expiring access tokens are refreshed before use. A failed refresh marks the
  connection `expired`, which shows as "Needs attention".

### Shopify (order status only)

- **Connect.** The owner types `your-store.myshopify.com`. The flow is Shopify's
  authorization code grant with an expiring offline token (`expiring=1`). The callback
  HMAC is verified with the app secret. The `shop` parameter must match
  `^[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com$` and equal the store the owner typed. The
  state is single-use and bound to the same user and business. The scopes are
  `read_orders` and `read_customers`.
- **The `get_store_orders` tool.** It finds exactly one Shopify customer, first by the
  conversation's verified WhatsApp phone number, then by the CRM email. It returns only
  that customer's five most recent orders (name, payment/fulfilment status, total, items).
  If no customer matches, or more than one does, it returns an empty list rather than
  guessing. Until a store is connected it returns `connected: false`.
- **Limits.** Pi cannot change orders. Disconnecting deletes the stored tokens. To remove
  access completely, the owner also uninstalls the app in the Shopify admin (the UI says
  this).

### Booking confirmation email (`email_booking_confirmation`)

This tool queues one email to the customer's own CRM address, using the business's
connected email provider (SMTP, Resend or SendGrid). The integration outbox delivers it
after commit. Each booking time is sent at most once, via a dedupe key. The recipient never
comes from model arguments. It uses the `customer_notice` template (subject "Booking
confirmed: …", signed with the business name), not the internal `system_alert` template.

### New tools (opt-in, off by default)

| Tool | Permission | Group |
| --- | --- | --- |
| `reschedule_booking` | `pi.bookings.manage` | bookings |
| `email_booking_confirmation` | `pi.bookings.manage` | bookings |
| `get_store_orders` | `orders.read` | catalog_orders |

Every tool acts only for the conversation's verified customer. Moving, confirming or
cancelling another customer's booking returns `RESOURCE_NOT_FOUND`.

## Server setup

Add these to the API environment (see `.env.example`). Never commit real values.

```
PI_APP_PUBLIC_URL=https://pi.example.com
GOOGLE_OAUTH_CLIENT_ID=<web client id>.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=<web client secret>
SHOPIFY_CLIENT_ID=<Dev Dashboard app client id>
SHOPIFY_CLIENT_SECRET=<Dev Dashboard app client secret>
SHOPIFY_API_VERSION=2026-07
```

**Google Cloud Console**
1. Create an OAuth client of type "Web application".
2. Add the authorized redirect URI
   `<PI_APP_PUBLIC_URL>/api/v1/pi-app/pi/connectors/google_calendar/callback`.
3. Enable the Google Calendar API.
4. Configure the consent screen with the two scopes above. Using them with external
   users requires Google's app verification before general availability. Until then,
   add test users.

**Shopify Dev Dashboard**
1. Create an app and set its redirect URL to
   `<PI_APP_PUBLIC_URL>/api/v1/pi-app/pi/connectors/shopify/callback`.
2. Request `read_orders` and `read_customers`.
3. Apply for protected customer data access (customer email and phone), which the
   order lookup needs.
4. Distribution: a custom (single-merchant) app, or public distribution for many stores.

**Worker.** `sweep_pi_calendar` runs every 30 seconds under ARQ. In development it runs in
the inline sweeper.

## Live verification still needed

Nothing below has been done. Credentials and explicit authorization are required.

1. Google: connect a test calendar, confirm that freeBusy excludes a real event, book
   a slot, and check that the event and invitation arrive. Then reschedule, cancel,
   revoke access in the Google account and confirm the card shows "Needs attention".
2. Shopify: connect a development store, place an order with a customer phone number,
   ask Pi for its status from that WhatsApp number, and confirm that a different number
   sees nothing. Also check token refresh after 24 hours.
3. Email: send a booking confirmation through a sandbox Resend/SendGrid account and
   check the delivery status in the integration activity.

## Known limitations

- Rescheduling ignores the booking's own calendar event by matching its exact time.
  Google merges adjacent busy periods, so moving into a time that overlaps the old slot
  next to another event can be refused. The customer is then offered other times.
- Staff calendars per team member (`staff_user_ids`) and per-service calendars
  (`calendar_connection_id`) exist in the schema. Only one business calendar can be
  connected from the UI so far.
- Shopify product and catalog import is not included. Pi answers product questions
  from the approved native catalog.
- Outlook, WooCommerce and other CRMs remain `planned` in the integration catalog.
