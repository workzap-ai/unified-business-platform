import base64
import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.ai.errors import GatewayUnavailable, MediaValidationError
from app.ai.manager import LLMManager
from app.ai.media import validate_video
from app.ai.types import Message, TextPart, VideoPart
from app.ai.usage import InMemoryUsageStore
from app.modules.pi.models import PiConversation, PiSettings
from app.modules.pi.service_conversation import compose_service_turn
from app.modules.pi.whatsapp import WhatsApp, normalize
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 30


async def test_video_uses_only_capable_provider_and_inline_payload(settings):
    settings.openai_api_key = SecretStr("test-openai")
    settings.gemini_api_key = SecretStr("test-gemini")
    settings.gemini_models = {"video": "test-video-model"}
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Customer shows a website mockup and asks for booking."}
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 20},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        response = await LLMManager(settings, http).complete(
            WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "PI"),
            alias="video",
            purpose="pi_video",
            messages=[
                Message.user(
                    [TextPart("Describe the video and speech."), VideoPart(VIDEO, "video/mp4")]
                )
            ],
        )
    assert len(calls) == 1 and calls[0].url.host == "generativelanguage.googleapis.com"
    data = json.loads(calls[0].content)["contents"][0]["parts"][1]["inlineData"]
    assert data == {"mimeType": "video/mp4", "data": base64.b64encode(VIDEO).decode()}
    assert "booking" in response.text and response.attempts[0].status == "success"


@pytest.mark.parametrize(
    "content,mime", [(b"not video", "video/mp4"), (VIDEO, "text/plain"), (b"", "video/mp4")]
)
def test_video_rejects_spoofed_and_empty_content(content, mime):
    with pytest.raises(MediaValidationError):
        validate_video(content, mime, 1000)


def test_video_limit_is_bounded():
    with pytest.raises(MediaValidationError):
        validate_video(VIDEO, "video/mp4", 10)


async def test_unconfigured_video_does_not_fall_through_to_text_provider(settings):
    settings.openai_api_key = SecretStr("test-openai")
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: calls.append(request))
    ) as http:
        with pytest.raises(GatewayUnavailable):
            await LLMManager(settings, http).complete(
                None,
                alias="video",
                purpose="pi_video",
                messages=[Message.user([VideoPart(VIDEO, "video/mp4")])],
            )
    assert calls == []


@pytest.mark.parametrize(
    "status,language,components",
    [
        ("PENDING", "en_US", [{"type": "BODY", "text": "Hello"}]),
        ("APPROVED", "es", [{"type": "BODY", "text": "Hola"}]),
        ("APPROVED", "en_US", [{"type": "BODY", "text": "Hello {{1}}"}]),
    ],
)
async def test_reminder_never_sends_unapproved_wrong_language_or_parameterized_template(
    settings, status, language, components
):
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "name": "followup",
                        "status": status,
                        "language": language,
                        "components": components,
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        with pytest.raises(BusinessRuleViolation):
            await WhatsApp(settings, http).send_template(
                "1234567",
                "7654321",
                "15550000001",
                {"name": "followup", "language": "en_US"},
                "test-token",
            )
    assert len(calls) == 1 and calls[0].method == "GET"


def test_video_webhook_preserves_caption_and_media_id():
    events = normalize(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "1234567"},
                                "messages": [
                                    {
                                        "from": "15550000001",
                                        "id": "video-1",
                                        "type": "video",
                                        "video": {
                                            "id": "7654321",
                                            "caption": "Is tarah ki website chahiye",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert events[0]["message_type"] == "video" and events[0]["media_id"] == "7654321"
    assert events[0]["body"] == "Is tarah ki website chahiye"


async def test_service_reply_uses_structured_provider_and_scoped_usage(settings):
    settings.gemini_api_key = SecretStr("test-gemini")
    settings.gemini_models = {"agent": "test-service-model"}
    calls = []
    payload = {
        "reply": "آپ کو ویب سائٹ میں کون سی سہولتیں چاہییں؟",
        "language": "ur",
        "summary": "Customer wants a website; features are unknown.",
        "requirements": {"service": "Website"},
        "missing": ["scope"],
        "awaiting_customer": True,
        "ready_for_team": False,
    }

    def provider(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(payload)}]}, "finishReason": "STOP"}
                ],
                "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 15},
            },
        )

    usage = InMemoryUsageStore()
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "PI")
    conversation = PiConversation(id=uuid4())
    policy = PiSettings(ai_config={"reply_alias": "balanced"}, response_rules={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        turn = await compose_service_turn(
            LLMManager(settings, http, usage=usage),
            scope,
            conversation,
            policy,
            {"latest_customer_message": "مجھے ویب سائٹ بنوانی ہے"},
        )
    assert turn.language == "ur" and "ویب" in turn.reply
    assert turn._attempts[0].input_tokens == 20
    assert (
        json.loads(calls[0].content)["generationConfig"]["responseMimeType"] == "application/json"
    )


async def test_whatsapp_voice_codec_parameter_is_normalized(settings):
    def provider(request):
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/voice",
                    "mime_type": "audio/ogg; codecs=opus",
                    "file_size": 8,
                },
            )
        return httpx.Response(200, content=b"OggSdata")

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        content, mime = await WhatsApp(settings, http).media("1234567", "test-token")
    assert mime == "audio/ogg" and content == b"OggSdata"


@pytest.mark.parametrize("mime", [None, ["audio/ogg"]])
async def test_malformed_media_metadata_is_a_controlled_failure(settings, mime):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"url": "https://lookaside.fbsbx.com/voice", "mime_type": mime}
            )
        )
    ) as http:
        with pytest.raises(BusinessRuleViolation) as error:
            await WhatsApp(settings, http).media("1234567", "test-token")
    assert error.value.code == "INVALID_MEDIA"
