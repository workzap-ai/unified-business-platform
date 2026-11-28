"""Cleaning the sound of a saved room recording (steady background noise, uneven loudness).

The worker runs ffmpeg on the recording before it is stored: a high-pass and low-pass band for
speech, `afftdn` (steady noise it learns as it goes) and loudness levelling. The picture is copied
untouched, so this is quick and loses no video quality. It is best effort and never blocks a save:
no ffmpeg installed, a failure, a timeout, or an output that came out empty all give back the
original bytes. Nothing that was said is logged.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

TIMEOUT_S = 15 * 60
AUDIO_FILTER = "highpass=f=90,lowpass=f=7500,afftdn=nr=14:nf=-45:tn=1,loudnorm=I=-16:TP=-1.5:LRA=11"


def available() -> bool:
    return shutil.which("ffmpeg") is not None


def command(source: str, target: str) -> list[str]:
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", source,
        "-map", "0:v?", "-c:v", "copy",
        "-map", "0:a?", "-af", AUDIO_FILTER, "-ac", "1", "-ar", "44100",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart", target,
    ]  # fmt: skip


async def clean(data: bytes) -> bytes:
    """The recording with its sound cleaned, or `data` itself when that is not possible."""
    if not data or not available():
        return data
    try:
        with tempfile.TemporaryDirectory(prefix="room-audio-") as folder:
            source = Path(folder) / "in.mp4"
            target = Path(folder) / "out.mp4"
            source.write_bytes(data)
            process = await asyncio.create_subprocess_exec(
                *command(str(source), str(target)),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=TIMEOUT_S)
            except TimeoutError:
                process.kill()
                await process.wait()
                logger.warning("room_audio_clean_timeout")
                return data
            if process.returncode != 0 or not target.exists():
                logger.warning("room_audio_clean_failed code=%s", process.returncode)
                return data
            cleaned = target.read_bytes()
            return cleaned if cleaned else data
    except OSError:
        logger.warning("room_audio_clean_unavailable")
        return data
