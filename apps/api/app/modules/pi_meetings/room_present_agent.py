"""The agent's side of presenting: draws the slide on show and publishes it as pi's video.

On every beat the agent hands this the room's `present` value. When it changed, the slide on show
is drawn (`slide_render`) and given to a video track that sends it a few times a second (a slide
does not move); a new slide only swaps the picture, and stopping ends the track, which the video
service then unpublishes. People see it as pi's own video tile, and pi's face comes back when it
stops. Nothing here decides WHAT to show: a person started it and chose the slide.

It is built so that a failure never touches the call. Drawing or publishing that fails is logged
(no words) and tried again on the next beat, three times at most for the same slide; pi keeps
listening and speaking either way. `aiortc` and `av` exist only in the room agent's image, so the
track class is made when first needed and the rest of this module is tested without them.
"""

import asyncio
import functools
import logging
from collections.abc import Callable
from fractions import Fraction
from typing import Any

from app.modules.pi_meetings import slide_render

logger = logging.getLogger(__name__)

FPS = 4  # a still slide needs no more; it keeps the stream alive and shows a change quickly
CLOCK = 90_000  # the video clock rate: a frame lasts CLOCK / FPS ticks
MAX_TRIES = 3  # the same slide is not retried forever


@functools.cache
def slide_track_class() -> Any:
    """The video track class (the agent image only: it needs aiortc and av)."""
    import av
    from aiortc import VideoStreamTrack
    from aiortc.mediastreams import MediaStreamError

    class SlideTrack(VideoStreamTrack):  # type: ignore[misc]
        """Sends the current picture FPS times a second; the picture can be swapped."""

        def __init__(self, image: Any) -> None:
            super().__init__()
            self._image = image
            self._ticks = 0

        def show(self, image: Any) -> None:
            self._image = image  # the same size as the first one: the track keeps its size

        async def recv(self) -> Any:
            if self.readyState != "live":
                raise MediaStreamError
            await asyncio.sleep(1 / FPS)  # the source paces the frames (the SDK does not)
            frame = av.VideoFrame.from_ndarray(self._image, format="rgb24")
            frame.pts = self._ticks
            frame.time_base = Fraction(1, CLOCK)
            self._ticks += CLOCK // FPS
            return frame

    return SlideTrack


def _make_track(image: Any) -> Any:
    return slide_track_class()(image)


def _picture(slide: dict[str, Any], number: int, total: int) -> Any:
    import numpy as np

    return np.ascontiguousarray(np.asarray(slide_render.render(slide, number, total)))


class Presenter:
    """Follows the room's `present` value and keeps pi's video in step with it."""

    def __init__(
        self,
        connection: Any,
        *,
        make_track: Callable[[Any], Any] = _make_track,
        picture: Callable[[dict[str, Any], int, int], Any] = _picture,
    ) -> None:
        self.connection = connection
        self._make_track, self._picture = make_track, picture
        self.track: Any = None
        self._key: tuple[int, bool, int] | None = None
        self._ident: tuple[int, bool] | None = None  # which presentation the count belongs to
        self._tries = 0

    @property
    def showing(self) -> bool:
        return self.track is not None

    async def apply(self, present: dict[str, Any] | None) -> None:
        """Bring the video in line with what the room says is on show. Never raises."""
        present = present or {}
        slides = present.get("slides") or []
        on = bool(present.get("on")) and bool(slides)
        index = max(0, min(int(present.get("index") or 0), max(len(slides) - 1, 0)))
        key = (int(present.get("v") or 0), on, index)
        if key == self._key:
            return
        if key[:2] != self._ident:
            self._ident, self._tries = key[:2], 0  # a new presentation (or its end): a clean count
        if self._tries >= MAX_TRIES:
            return
        try:
            if not on:
                await self.stop()
            else:
                image = await asyncio.to_thread(
                    self._picture, slides[index], index + 1, len(slides)
                )
                if self.track is None:
                    track = self._make_track(image)
                    await self.connection.add_tracks(video=track)
                    self.track = track
                else:
                    self.track.show(image)
            self._key = key
        except Exception:  # noqa: BLE001 - presenting is a bonus: pi goes on listening and speaking
            self._tries += 1
            logger.warning("room_present_failed tries=%d", self._tries)

    async def stop(self) -> None:
        """End the video track (the video service unpublishes it) and forget the slide."""
        track, self.track = self.track, None
        if track is not None:
            try:
                track.stop()
            except Exception:  # noqa: BLE001
                logger.warning("room_present_stop_failed")
