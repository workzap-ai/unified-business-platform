# PI service conversations

PI now collects service enquiries without publishing service prices. A service or hybrid
business uses this flow automatically. In **PI → Settings → Response rules**, select
**Treat all enquiries as services** to use it for another business type.

The assistant uses recent conversation history, the existing brief, customer memory,
approved knowledge passages and active offering names. Catalog variant prices are excluded
from its context. Knowledge and memory retrieval respect the configured tool switches.
It asks about scope, audience, existing assets, customer-stated budget and desired timing.
Budget and dates are internal requirements, never a company quotation or delivery promise.
Service replies are generated in the customer's current language, including Roman Urdu
and language changes during a conversation. This depends on the configured language model;
automated tests verify the routing and preservation of multilingual content, not fluency in
every language.

The inbox context panel shows the current English team summary, structured requirements,
missing information, reminder permission and next follow-up date. PI creates or updates
the conversation's sales lead and notifies members with `pi.read` when an enquiry first
arrives and when it becomes ready for review. The complete brief stays in the inbox;
notifications contain a short preview. No email or company WhatsApp notification is sent.

Human requests and sensitive account questions go to the team. Product-business order
and quotation tools retain their existing confirmation workflow. Changing to service mode
does not confirm an old order draft.

## Reminders

The default delay is seven days after the last successfully sent assistant reply while
awaiting the customer's response. PI asks for reminder permission and records the source
message. There is at most one reminder per unanswered turn; silence never creates a loop.

Configure **PI → Settings → WhatsApp → Follow-up reminders**:

1. Enable reminders and choose the delay (1–30 days).
2. Add an approved, text-only Meta reminder template for each customer language. This
   version supports templates with no variables, media headers or buttons.
3. Enter the WhatsApp business account ID on the connection page. The access token needs
   permission to read that account's message templates as well as send messages.

For example, customer language `roman_ur` can map to template `service_followup_roman_ur`
with Meta language `ur` or `en_US`, according to how Meta approved that template. PI does
not silently substitute an English template for another customer language.

The worker checks every five minutes. It rechecks permission, the latest customer turn,
connection, active product/environment, auto-reply state and human takeover before sending.
Opt-out, a new message, closure or takeover cancels the reminder. Template approval and
language are checked with Meta before sending. Missing configuration creates a deduplicated
operator notification and is revisited hourly. Ambiguous delivery is not blindly retried.

WhatsApp requires approved templates outside its 24-hour customer-service window and
permission for subsequent messages. See the [official WhatsApp policy](https://whatsappbusiness.com/policy/).

## Audio, images and video

The media controls enable audio transcription, image understanding and video understanding.
Captions are retained alongside the transcript/description. MIME types, content signatures
and size limits are validated; arbitrary customer URLs are not downloaded. Unsupported,
oversized, mismatched or failed media is handed to a person.

Video currently uses the Gemini provider's `video` model alias. Pin an appropriate model
through `GEMINI_MODELS` if default aliases are disabled. The implementation sends MP4/3GPP
bytes inline through the existing scoped AI manager, including video sound, with usage
metering and budget enforcement. The smaller of the workspace/deployment limit and 16 MB
applies. Large-file upload and long-video processing are not implemented. See Google's
[video input documentation](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding).

## Activation and verification

- Apply Alembic revision `0006_pi_service_conversations` to the intended application
  database before running the updated API. It adds the brief and due date, plus the video
  message type. It was exercised against the local disposable test database.
- Run the API and the ARQ worker with Redis. Inline job execution alone does not schedule
  future reminders. Existing workspace media choices are preserved; enable media explicitly
  if it was previously disabled.
- Configure a live AI provider, active WhatsApp connection and approved reminder templates.
  No live customer messages or real AI-provider calls were made during automated verification.
- Regression coverage includes no-price service discovery, retained history/language,
  summaries/leads, media and captions, provider failures, template checks, reminder timing,
  duplicate delivery prevention, opt-out, takeover and stale queued replies.

Reply validation rejects numeric/currency-bearing service replies rather than risking an
unreviewed amount; such a failure goes to the team. A customer can still state a numeric
budget or date, which is saved internally. Provider-dependent language and media quality
requires live acceptance checks with representative recordings and conversations.

Verified on 2026-09-25:

- Full backend suite on a fresh local test database: **403 passed, 1 skipped** (Redis worker).
- Final PI regression run: **62 passed**, including the new service and reminder flows.
- Media/provider tests were rerun after normalizing WhatsApp's `audio/ogg; codecs=opus`.
- Ruff and strict mypy pass for the changed backend areas; frontend lint, formatting,
  TypeScript and the isolated production build pass.
- Playwright: service mode, reminder template editing/saving and 390px layout pass.
- Migration upgrade → downgrade → upgrade and `alembic check` pass with no schema drift.

An earlier run against the shared local test database had two integration-outbox failures.
Both passed in isolation on a fresh disposable database, followed by the passing full run.
Live application database migration, Meta template approval, actual WhatsApp delivery and
real-provider language/media acceptance testing have not been performed by this change.
