"""The room agent's process: join the call, hear people, play pi's voice, and renew the claim.

This is the only module that imports the video provider's Python SDK (`getstream[webrtc]`, a
Linux-only native wheel in the separate `room-agent` dependency group). Everything it decides lives
in `room_agent`, `room_speech`, `room_turns` and `voice`, which are tested without the SDK. The SDK
calls below follow the SDK's source (getstream 8.2.0, getstream-rtc 0.1.0) and the Phase 0 join
test; they have NOT yet been run against a live call from this code
(see docs/pi-saas/pi-room-agent.md).

The process polls for rooms (`room_agent_claim.claim`), takes at most `MAX_ROOMS`, and for each one:
joins as `pi_agent`, publishes an audio track, feeds every person's frames to `RoomRun`, and every
`BEAT_S` seconds renews its claim and applies the host's orders. When the claim is lost, the room
ends, speech is switched off or the pause switch is on, it leaves. No audio is stored here; the only
text it writes is pi's own lines, into the meeting's transcript.
"""

import asyncio
import contextlib
import logging
import secrets
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.manager import build_llm_manager
from app.core.config import Settings, get_settings
from app.core.database import create_engine
from app.modules.pi_meetings import room_agent_claim as claims
from app.modules.pi_meetings import room_agent_lines as lines
from app.modules.pi_meetings.room_agent import AGENT_USER, RoomRun
from app.modules.pi_meetings.room_provider import CALL_TYPE
from app.modules.pi_meetings.room_speech import RoomSpeech, Session
from app.modules.pi_meetings.room_speech import Settings as SpeechSettings

logger = logging.getLogger("pi_room_agent")

MAX_ROOMS = 3  # rooms one agent process holds at once
POLL_S = 5.0


class TrackOut:
    """`room_speech.AudioOut` over the SDK's audio track."""

    def __init__(self, track: Any, pcm_data: Any, audio_format: Any) -> None:
        self.track = track
        self._pcm_data = pcm_data
        self._format = audio_format

    async def write(self, pcm: bytes, sample_rate: int) -> None:
        import numpy as np

        await self.track.write(
            self._pcm_data(
                sample_rate=sample_rate,
                format=self._format.S16,
                samples=np.frombuffer(pcm, dtype=np.int16),
                channels=1,
            )
        )

    async def flush(self) -> None:
        await self.track.flush()


async def run_room(
    settings: Settings,
    sessions: async_sessionmaker[Any],
    manager: Any,
    agent_id: str,
    room_id: Any,
    orders: claims.Orders,
) -> None:
    """Hold one room until it should be left. Never raises: a room that fails is released."""
    from getstream import AsyncStream
    from getstream.video import rtc
    from getstream.video.rtc.audio_track import AudioStreamTrack
    from getstream.video.rtc.track_util import AudioFormat, PcmData

    secret = settings.stream_api_secret
    if not settings.stream_api_key or secret is None:
        logger.error("stream_keys_missing")
        return
    client = AsyncStream(api_key=settings.stream_api_key, api_secret=secret.get_secret_value())
    track = AudioStreamTrack(sample_rate=48000, channels=1, pace=False)

    async def on_line(who: str, words: str) -> None:
        """pi's own lines go into the transcript; people's come later, from the recordings."""
        if not lines.is_pi(who):
            return
        try:
            async with sessions() as db:
                if await lines.store_pi_line(db, orders, words):
                    await db.commit()
        except Exception:  # noqa: BLE001 - a missing line must never stop pi talking
            logger.warning("room_pi_line_not_stored")

    out = TrackOut(track, PcmData, AudioFormat)
    speech = RoomSpeech(
        manager=manager,
        scope=orders.scope,
        session=Session(
            SpeechSettings(
                mode="speak" if orders.speak else "off",
                intake=orders.intake,
                language=orders.language,
            )
        ),
        out=out,
        customers=lambda: 0,
        someone_speaking=lambda: False,
        clock=time.monotonic,
        on_line=on_line,
    )
    run = RoomRun(speech, clock=time.monotonic)
    run.apply(orders)
    stop = asyncio.Event()

    def on_audio(pcm: Any) -> None:
        participant = getattr(pcm, "participant", None)
        who = str(getattr(participant, "user_id", "") or "")
        data = pcm.to_int16()
        run.on_audio(who, data.to_bytes(), int(data.sample_rate), int(data.channels or 1))

    async def beat_loop() -> None:
        unread_since: float | None = None
        while not stop.is_set():
            await asyncio.sleep(claims.BEAT_S)
            try:
                async with sessions() as db:
                    got = await claims.beat(db, room_id, agent_id, datetime.now(UTC))
                    await db.commit()
                unread_since = None
            except Exception:  # noqa: BLE001 - a database blip must not drop pi at once
                logger.warning("room_beat_failed")
                unread_since = unread_since or time.monotonic()
                if time.monotonic() - unread_since > claims.LEASE_S:
                    stop.set()
                continue
            if got is None or not got.stay:
                stop.set()
                return
            run.apply(got)

    beat_task: asyncio.Task[None] | None = None
    try:
        call = client.video.call(CALL_TYPE, orders.call_id)
        async with await rtc.join(call, AGENT_USER) as connection:
            connection.on("audio", on_audio)
            connection.on("participant_joined", lambda p: run.joined(str(p.user_id)))
            connection.on("participant_left", lambda p: run.left(str(p.user_id)))
            connection.on("call_ended", lambda *_: stop.set())
            await connection.add_tracks(audio=track)
            for person in connection.participants_state.get_participants():
                run.joined(str(person.user_id))
            beat_task = asyncio.create_task(beat_loop())
            await stop.wait()
            await run.drain()
    except Exception:  # noqa: BLE001 - the room is released below so another agent can try
        logger.exception("room_agent_failed")
    finally:
        stop.set()
        if beat_task is not None:
            beat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await beat_task
        with contextlib.suppress(Exception):
            async with sessions() as db:
                await claims.release(db, room_id, agent_id)
                await db.commit()
        with contextlib.suppress(Exception):
            await client.aclose()


async def main() -> None:
    """The agent service: claim rooms, hold them, repeat. One process, a few rooms."""
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    engine = create_engine(settings)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    http = httpx.AsyncClient(timeout=15, follow_redirects=False)
    manager = build_llm_manager(settings, http, sessions)
    agent_id = f"agent-{secrets.token_hex(8)}"
    held: dict[Any, asyncio.Task[None]] = {}
    logger.info("room_agent_started %s", agent_id)
    try:
        while True:
            for room_id, task in list(held.items()):
                if task.done():
                    held.pop(room_id)
            if len(held) < MAX_ROOMS:
                try:
                    async with sessions() as db:
                        taken = await claims.claim(
                            db, agent_id, datetime.now(UTC), limit=MAX_ROOMS - len(held)
                        )
                        found = []
                        for room in taken:
                            orders = await claims.beat(db, room.id, agent_id, datetime.now(UTC))
                            if orders is not None and orders.stay:
                                found.append((room.id, orders))
                        await db.commit()
                    for room_id, orders in found:
                        if room_id not in held:
                            held[room_id] = asyncio.create_task(
                                run_room(settings, sessions, manager, agent_id, room_id, orders)
                            )
                except Exception:  # noqa: BLE001 - keep polling
                    logger.exception("room_claim_failed")
            await asyncio.sleep(POLL_S)
    finally:
        for task in held.values():
            task.cancel()
        await http.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
