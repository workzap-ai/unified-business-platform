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
import os
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.manager import build_llm_manager
from app.core.config import Settings, get_settings
from app.core.database import create_engine
from app.modules.pi_meetings import room_agent_claim as claims
from app.modules.pi_meetings import room_agent_lines as lines
from app.modules.pi_meetings import room_agent_memory as memory
from app.modules.pi_meetings import room_recall, room_sight, voice
from app.modules.pi_meetings.room_agent import AGENT_USER, RoomRun
from app.modules.pi_meetings.room_provider import CALL_TYPE
from app.modules.pi_meetings.room_sight import Sight
from app.modules.pi_meetings.room_speech import RoomSpeech, Session
from app.modules.pi_meetings.room_speech import Settings as SpeechSettings

logger = logging.getLogger("pi_room_agent")

MAX_ROOMS = 3  # rooms one agent process holds at once
POLL_S = 5.0
SEE_SCREEN_ENV = "PI_ROOM_SEE_SCREEN"  # "1" lets pi look at a shared screen; off by default
SCREEN_NOTE = "[On screen] "
MEMORY_EVERY = 12  # beats between reads of the customer's memory (about a minute)


def join_options(see_screen: bool) -> dict[str, Any]:
    """Extra arguments for joining: with sight on, the agent also receives shared screens (never
    cameras). Without it the join is exactly as before."""
    if not see_screen:
        return {}
    from getstream.video.rtc import SubscriptionConfig
    from getstream.video.rtc.pb.stream.video.sfu.models import models_pb2
    from getstream.video.rtc.tracks import TrackSubscriptionConfig

    rule = TrackSubscriptionConfig(
        track_types=[models_pb2.TRACK_TYPE_AUDIO, models_pb2.TRACK_TYPE_SCREEN_SHARE]
    )
    return {"subscription_config": SubscriptionConfig(default=rule)}


def _uid(event: Any) -> str:
    """The user id of a participant or of a join/leave event (the event wraps the participant)."""
    for holder in (event, getattr(event, "participant", None)):
        value = getattr(holder, "user_id", None)
        if value:
            return str(value)
    return ""


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

    known: dict[str, Any] = {"block": {}}

    async def refresh_memory() -> None:
        """The customer's memory, read again every minute: staff may link the customer mid-call."""
        try:
            async with sessions() as db:
                known["block"] = await memory.load_block(db, orders)
        except Exception:  # noqa: BLE001 - no memory means pi asks, it never stops pi talking
            logger.warning("room_memory_not_loaded")

    await refresh_memory()

    async def on_state(session: Session) -> None:
        """Keep what pi has done, so a restarted agent carries on and does not start over."""
        when = (
            datetime.now(UTC) - timedelta(seconds=time.monotonic() - session.last_spoke_at)
            if session.last_spoke_at is not None
            else None
        )
        async with sessions() as db:
            if await claims.save_state(
                db,
                room_id,
                agent_id,
                spoken=session.spoken,
                disclosed=session.disclosed,
                halted=session.halted,
                last_spoke_at=when,
                notes=room_recall.pack(session),
            ):
                await db.commit()

    # what pi did before a restart: the pause since it last spoke is counted on this clock
    since = (
        (datetime.now(UTC) - orders.last_spoke_at).total_seconds()
        if orders.last_spoke_at is not None
        else None
    )
    out = TrackOut(track, PcmData, AudioFormat)
    see_screen = os.environ.get(SEE_SCREEN_ENV, "") == "1"

    async def on_screen_note(note: str) -> None:
        await on_line(voice.PI_LABEL, SCREEN_NOTE + note)

    sight = Sight(manager, orders.scope, clock=time.monotonic, on_note=on_screen_note)
    speech = RoomSpeech(
        manager=manager,
        scope=orders.scope,
        session=Session(
            SpeechSettings(
                mode="speak" if orders.speak else "off",
                intake=orders.intake,
                language=orders.language,
            ),
            disclosed=orders.disclosed,
            # the disclosure was spoken before the restart: the rules must know it was made
            history=[voice.Said(True, voice.opening(language=orders.language))]
            if orders.disclosed
            else [],
            halted=orders.halted,
            spoken=orders.spoken,
            last_spoke_at=None if since is None else time.monotonic() - max(0.0, since),
        ),
        out=out,
        customers=lambda: 0,
        someone_speaking=lambda: False,
        clock=time.monotonic,
        on_line=on_line,
        on_state=on_state,
        what_i_know=lambda: known["block"],
        on_screen=sight.current,
    )
    room_recall.restore(speech.session, orders.notes)  # what pi noted before a restart
    run = RoomRun(speech, clock=time.monotonic)
    run.apply(orders)
    stop = asyncio.Event()

    def on_audio(pcm: Any) -> None:
        participant = getattr(pcm, "participant", None)
        who = str(getattr(participant, "user_id", "") or "")
        data = pcm.to_int16()
        run.on_audio(who, data.to_bytes(), int(data.sample_rate), int(data.channels or 1))

    async def watch_screen(remote: Any) -> None:
        """Looks at a shared screen now and then; ends when the share ends. Never raises."""
        try:
            async for frame in remote.video_frames():
                await sight.look(frame.data, frame.width, frame.height)
                if stop.is_set():
                    return
                # the stream keeps only the newest frame while this waits
                await asyncio.sleep(room_sight.EVERY_S)
        except Exception:  # noqa: BLE001 - sight is a bonus
            logger.warning("room_screen_watch_ended")

    screen_tasks: set[asyncio.Task[None]] = set()

    def on_track(remote: Any) -> None:
        if not see_screen:
            return
        from getstream_rtc import TrackType

        if getattr(remote, "track_type", None) != TrackType.SCREEN_SHARE:
            return  # a camera or audio: not looked at
        task = asyncio.create_task(watch_screen(remote))
        screen_tasks.add(task)
        task.add_done_callback(screen_tasks.discard)

    async def beat_loop() -> None:
        unread_since: float | None = None
        beats = 0
        while not stop.is_set():
            await asyncio.sleep(claims.BEAT_S)
            beats += 1
            if beats % MEMORY_EVERY == 0:
                await refresh_memory()
            try:
                async with sessions() as db:
                    got = await claims.beat(db, room_id, agent_id, datetime.now(UTC))
                    await db.commit()
                unread_since = None
            except Exception:  # noqa: BLE001 - a database blip must not drop pi at once
                logger.warning("room_beat_failed")
                run.speech.session.muted = True  # fail closed: no orders means no speaking
                run.speech.barge_in()
                unread_since = unread_since or time.monotonic()
                if time.monotonic() - unread_since > claims.LEASE_S:
                    stop.set()
                continue
            if got is None or not got.stay:
                stop.set()
                return
            run.apply(got)

    async def tick_loop() -> None:
        """Ends turns by the clock when frames stop, and says how much audio is arriving."""
        ticks = 0
        while not stop.is_set():
            await asyncio.sleep(0.2)
            run.tick()
            ticks += 1
            if ticks % 50 == 0:  # every 10 seconds
                heard = run.report()
                if heard:
                    logger.info("room_audio frames=%s speaking=%s", heard, run.cutter.speaking())

    beat_task: asyncio.Task[None] | None = None
    tick_task: asyncio.Task[None] | None = None
    try:
        call = client.video.call(CALL_TYPE, orders.call_id)
        async with await rtc.join(call, AGENT_USER, **join_options(see_screen)) as connection:
            connection.on("audio", on_audio)
            connection.on("participant_joined", lambda p: run.joined(_uid(p)))
            connection.on("participant_left", lambda p: run.left(_uid(p)))
            connection.on("call_ended", lambda *_: stop.set())
            connection.on("track_added", on_track)
            await connection.add_tracks(audio=track)
            for person in connection.participants_state.get_participants():
                run.joined(_uid(person))
            beat_task = asyncio.create_task(beat_loop())
            tick_task = asyncio.create_task(tick_loop())
            await stop.wait()
            await run.drain()
    except Exception:  # noqa: BLE001 - the room is released below so another agent can try
        logger.exception("room_agent_failed")
    finally:
        stop.set()
        for task in (beat_task, tick_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
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
