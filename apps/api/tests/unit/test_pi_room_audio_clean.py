# ruff: noqa: ASYNC221
import shutil
import subprocess  # noqa: S404

import pytest

from app.modules.pi_meetings import audio_clean


async def test_without_ffmpeg_the_original_comes_back(monkeypatch):
    monkeypatch.setattr(audio_clean, "available", lambda: False)
    assert await audio_clean.clean(b"abc") == b"abc"


async def test_empty_input_is_left_alone():
    assert await audio_clean.clean(b"") == b""


async def test_a_file_ffmpeg_cannot_read_comes_back_unchanged():
    if not audio_clean.available():
        pytest.skip("ffmpeg not installed")
    assert await audio_clean.clean(b"not a media file") == b"not a media file"


def test_the_picture_is_copied_not_re_encoded():
    cmd = audio_clean.command("a.mp4", "b.mp4")
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "afftdn" in cmd[cmd.index("-af") + 1]


async def test_a_real_clip_is_cleaned_and_keeps_its_audio(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=160x120:d=2",
            "-f", "lavfi", "-i", "sine=f=300:d=2",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", str(clip),
        ],
        check=True,
    )  # fmt: skip
    out = await audio_clean.clean(clip.read_bytes())
    assert out != clip.read_bytes() and len(out) > 1000
    (tmp_path / "out.mp4").write_bytes(out)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
         str(tmp_path / "out.mp4")],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert "video" in probe.stdout and "audio" in probe.stdout
