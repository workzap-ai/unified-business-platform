"""Recording a meeting end to end: consent first, parts are transcribed as they arrive, sending a
part again replaces it, the audio is never kept, then the transcript is analysed like an import."""

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, update
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, FakeManager, body, switch_on

from app.ai.errors import GatewayUnavailable
from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import recording_routes, routes
from app.modules.pi_meetings.models import PiMeeting, PiMeetingSegment

pytestmark = pytest.mark.integration
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64


class Speech(FakeManager):
    """Transcribes what the test says the audio contains; fails on demand."""

    def __init__(self, text="Our evening stock keeps running out. We need a list by Friday."):
        self.text = text
        self.calls = []
        self.fail = False

    async def transcribe(self, scope, audio, mime, **kw):
        self.calls.append((mime, len(audio), kw))
        if self.fail:
            raise GatewayUnavailable()
        return SimpleNamespace(text=self.text, language="en")


def part(api, mid, index, **kw):
    return api.post(
        f"{BASE}/{mid}/recording/parts",
        data={
            "index": str(index),
            "offset_ms": str(index * 300_000),
            "duration_ms": "60000",
            **kw,
        },
        files={"file": ("part.webm", WEBM, "audio/webm;codecs=opus")},
    )


async def test_record_transcribe_complete_and_analyse(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366100001")
    await switch_on(api)
    speech = Speech()
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: speech)
    monkeypatch.setattr(routes, "build_llm_manager", lambda *a, **k: speech)
    mid = (await api.post(BASE, json=body(source="browser"))).json()["id"]

    first = await part(api, mid, 0)
    assert first.status_code == 200, first.text
    assert first.json() == {"part": 0, "segments": 2}
    assert speech.calls[0][0] == "audio/webm"  # the codec suffix is not sent on
    second = await part(api, mid, 1)
    assert second.status_code == 200 and second.json()["segments"] == 2

    detail = (await api.get(f"{BASE}/{mid}")).json()
    assert detail["status"] == "transcribing"
    assert [s["ordinal"] for s in detail["segments"]] == [0, 1, 1000, 1001]
    assert detail["segments"][2]["start_ms"] >= 300_000  # the part's offset is applied
    # one speaker of unknown role: nothing is taken as the customer's own words
    assert detail["participants"] == ["Speaker 1"]
    assert detail["has_recording"] is False  # the audio is not kept

    done = await api.post(
        f"{BASE}/{mid}/recording/complete", json={"duration_ms": 360_000, "parts": 2}
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "analysing" and done.json()["duration_ms"] == 360_000

    analysed = await api.post(f"{BASE}/{mid}/analyse")
    assert analysed.status_code == 200, analysed.text
    assert analysed.json()["status"] == "review"
    await pi.close()


async def test_sending_a_part_again_replaces_it(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366100002")
    await switch_on(api)
    speech = Speech()
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: speech)
    mid = (await api.post(BASE, json=body())).json()["id"]
    await part(api, mid, 0)
    speech.text = "A corrected line."
    again = await part(api, mid, 0)
    assert again.json() == {"part": 0, "segments": 1}
    business_db.expire_all()
    rows = (await business_db.scalars(select(PiMeetingSegment.text))).all()
    assert list(rows) == ["A corrected line."]
    await pi.close()


async def test_a_provider_failure_stores_nothing_and_can_be_retried(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366100003")
    await switch_on(api)
    speech = Speech()
    speech.fail = True
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: speech)
    mid = (await api.post(BASE, json=body())).json()["id"]
    failed = await part(api, mid, 0)
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "MEETING_TRANSCRIBE_FAILED"
    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiMeetingSegment)) == 0
    speech.fail = False
    assert (await part(api, mid, 0)).status_code == 200  # the retry works and clears the failure
    status = await business_db.scalar(select(PiMeeting.status))
    assert status == "transcribing"
    await pi.close()


async def test_bad_audio_and_no_speech_are_refused_clearly(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366100004")
    await switch_on(api)
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: Speech())
    mid = (await api.post(BASE, json=body())).json()["id"]
    empty = await api.post(
        f"{BASE}/{mid}/recording/parts",
        data={"index": "0"},
        files={"file": ("part.webm", b"", "audio/webm")},
    )
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "MEETING_AUDIO_EMPTY"
    bad_index = await api.post(
        f"{BASE}/{mid}/recording/parts",
        data={"index": "-1"},
        files={"file": ("part.webm", WEBM, "audio/webm")},
    )
    assert bad_index.status_code == 422
    none = await api.post(f"{BASE}/{mid}/recording/complete", json={"duration_ms": 1, "parts": 0})
    assert none.status_code == 422 and none.json()["error"]["code"] == "TRANSCRIPT_EMPTY"
    await pi.close()


async def test_the_feature_flag_and_permissions_still_apply(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366100005")
    off = await part(api, "00000000-0000-0000-0000-000000000001", 0)
    assert off.status_code == 403 and off.json()["error"]["code"] == "MEETING_INTEL_OFF"
    await switch_on(api)
    unknown = await part(api, "00000000-0000-0000-0000-000000000001", 0)
    assert unknown.status_code == 404  # another workspace's meeting is "not found"
    await pi.close()


async def test_a_card_or_phone_spoken_across_sentences_is_redacted_before_it_is_stored(
    api, business_db, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "366100006")
    await switch_on(api)
    # speech-to-text writes spoken digits with a full stop between the groups
    speech = Speech(
        "My card is 4111. 1111. 1111. 1111. And call me on 0300. 1234567. The stock runs out."
    )
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: speech)
    mid = (await api.post(BASE, json=body())).json()["id"]
    assert (await part(api, mid, 0)).status_code == 200
    detail = (await api.get(f"{BASE}/{mid}")).json()
    stored = " ".join(s["text"] for s in detail["segments"])
    for digits in ("4111", "1111", "0300", "1234567"):
        assert digits not in stored
    assert "stock runs out" in stored
    await pi.close()


async def test_no_consent_means_no_audio_is_sent_to_speech_to_text(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366100007")
    await switch_on(api)
    speech = Speech()
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: speech)
    mid = (await api.post(BASE, json=body())).json()["id"]
    await business_db.execute(update(PiMeeting).values(consent_at=None))
    await business_db.commit()
    refused = await part(api, mid, 0)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "MEETING_CONSENT_REQUIRED"
    assert speech.calls == []  # nothing left for the provider
    await pi.close()


async def test_a_meeting_with_a_finished_transcript_is_not_reopened(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366100008")
    await switch_on(api)
    speech = Speech()
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: speech)
    monkeypatch.setattr(routes, "build_llm_manager", lambda *a, **k: speech)

    # a recorded meeting: complete closes it to more audio
    mid = (await api.post(BASE, json=body())).json()["id"]
    await part(api, mid, 0)
    await api.post(f"{BASE}/{mid}/recording/complete", json={"duration_ms": 60_000, "parts": 1})
    late = await part(api, mid, 1)
    assert late.status_code == 409 and late.json()["error"]["code"] == "MEETING_CLOSED"

    # an analysed meeting: its insights cite segment numbers that new audio would rewrite
    await api.post(f"{BASE}/{mid}/analyse")
    business_db.expire_all()
    await business_db.execute(update(PiMeeting).values(status="transcribing"))
    await business_db.commit()
    assert (await part(api, mid, 0)).status_code == 409

    # an imported transcript: part 0 would overwrite its lines
    other = (await api.post(BASE, json=body(title="Imported"))).json()["id"]
    await api.post(f"{BASE}/{other}/transcript", json={"text": "Customer: hello there"})
    await business_db.execute(
        update(PiMeeting).where(PiMeeting.id == other).values(status="created")
    )
    await business_db.commit()
    clash = await part(api, other, 0)
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "MEETING_CLOSED"
    await pi.close()


async def test_another_workspaces_meeting_is_not_found_and_not_transcribed(
    api, business_db, monkeypatch
):
    first, _, _ = await workspace(api, business_db, "366100009")
    await switch_on(api)
    speech = Speech()
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: speech)
    mid = (await api.post(BASE, json=body())).json()["id"]
    second, _, _ = await workspace(api, business_db, "366100010")
    await switch_on(api)  # the second workspace has the feature on too
    foreign = await part(api, mid, 0)
    assert foreign.status_code == 404  # never "forbidden", which would confirm it exists
    assert (
        await api.post(f"{BASE}/{mid}/recording/complete", json={"duration_ms": 1, "parts": 1})
    ).status_code == 404
    assert speech.calls == []
    await first.close()
    await second.close()


async def test_the_audit_trail_holds_counts_and_ids_never_the_words(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366100011")
    await switch_on(api)
    monkeypatch.setattr(
        recording_routes, "build_llm_manager", lambda *a, **k: Speech("Secret roadmap words.")
    )
    mid = (await api.post(BASE, json=body())).json()["id"]
    await part(api, mid, 0)
    await api.post(f"{BASE}/{mid}/recording/complete", json={"duration_ms": 60_000, "parts": 1})
    business_db.expire_all()
    rows = (
        await business_db.execute(
            select(AuditEvent.action, AuditEvent.details).where(
                AuditEvent.action.in_(
                    ["pi.meeting_part_transcribed", "pi.meeting_recording_completed"]
                )
            )
        )
    ).all()
    by_action = {action: details for action, details in rows}
    assert by_action["pi.meeting_part_transcribed"] == {"part": 0, "segments": 1}
    assert set(by_action["pi.meeting_recording_completed"]) == {"parts", "skipped", "duration_ms"}
    assert "Secret" not in str(rows)
    await pi.close()
