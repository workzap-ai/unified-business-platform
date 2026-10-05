"""Face recognition for the second sign-in step (after the password).

Runs on the server with OpenCV's YuNet face detector and SFace recogniser (Apache-2.0
models in face_models/). A face is reduced to a 128-number "face code" (embedding);
no photos are kept. Codes are encrypted at rest by the caller.

Liveness, kept honest: every check takes several camera frames over about two
seconds while the person moves a little closer. We need exactly one face in every
frame, every frame must match, the frames can't be identical, and the face must grow
between the first and last frame. That stops a single photo or a replayed upload. It is
not a guarantee against a skilled spoof, which is why a face never replaces the
password: it is an extra check after it.
"""

import base64
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

MODELS = Path(__file__).with_name("face_models")
DETECTOR = MODELS / "face_detection_yunet_2023mar.onnx"
RECOGNISER = MODELS / "face_recognition_sface_2021dec_int8.onnx"

FRAMES = 3
MAX_FRAME_BYTES = 700_000
MAX_SIDE = 1280
MIN_FACE_SIDE = 80  # pixels: the face must fill a decent part of the picture
MATCH = 0.42  # cosine similarity; same person scores ~0.6-0.95, others ~0.0-0.3
MIN_GROWTH = 1.08  # the face must get at least 8% bigger ("move a little closer")
EMBEDDING_SIZE = 128


class FaceError(Exception):
    """A frame set that can't be used, with a message safe to show the person."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class FaceFrame:
    embedding: np.ndarray
    width: float  # face box width in pixels
    centre: tuple[float, float]


class _Engine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._detector: cv2.FaceDetectorYN | None = None
        self._recogniser: cv2.FaceRecognizerSF | None = None

    def _load(self) -> tuple[cv2.FaceDetectorYN, cv2.FaceRecognizerSF]:
        if self._detector is None or self._recogniser is None:
            self._detector = cv2.FaceDetectorYN.create(str(DETECTOR), "", (320, 320), 0.85)
            self._recogniser = cv2.FaceRecognizerSF.create(str(RECOGNISER), "")
        return self._detector, self._recogniser

    def frame(self, data: bytes) -> FaceFrame:
        if not data or len(data) > MAX_FRAME_BYTES:
            raise FaceError("FACE_FRAME_INVALID", "The camera picture couldn't be read.")
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FaceError("FACE_FRAME_INVALID", "The camera picture couldn't be read.")
        height, width = image.shape[:2]
        if max(height, width) > MAX_SIDE:
            scale = MAX_SIDE / max(height, width)
            image = cv2.resize(image, (int(width * scale), int(height * scale)))
            height, width = image.shape[:2]
        # OpenCV models aren't safe to share across threads: one at a time.
        with self._lock:
            detector, recogniser = self._load()
            detector.setInputSize((width, height))
            _, faces = detector.detect(image)
            if faces is None or len(faces) == 0:
                raise FaceError("FACE_NOT_FOUND", "We couldn't see your face. Look at the camera.")
            if len(faces) > 1:
                raise FaceError("FACE_TOO_MANY", "Only one person should be in the picture.")
            face = faces[0]
            if min(face[2], face[3]) < MIN_FACE_SIDE:
                raise FaceError("FACE_TOO_SMALL", "Come a little closer to the camera.")
            aligned = recogniser.alignCrop(image, face)
            embedding = recogniser.feature(aligned).flatten().astype(np.float32)
        norm = float(np.linalg.norm(embedding)) or 1.0
        return FaceFrame(
            embedding / norm,
            float(face[2]),
            (float(face[0] + face[2] / 2), float(face[1] + face[3] / 2)),
        )


ENGINE = _Engine()


def decode_frames(frames: list[str]) -> list[bytes]:
    if len(frames) != FRAMES:
        raise FaceError("FACE_FRAMES", "Please try again.")
    out = []
    for item in frames:
        raw = item.split(",", 1)[1] if item.startswith("data:") else item
        try:
            out.append(base64.b64decode(raw, validate=True))
        except ValueError:
            raise FaceError("FACE_FRAME_INVALID", "The camera picture couldn't be read.") from None
    return out


def live_frames(frames: list[bytes]) -> list[FaceFrame]:
    """Reads each frame and checks liveness. CPU work: call it in a thread."""
    if len(set(frames)) != len(frames):
        raise FaceError("FACE_NOT_LIVE", "Please use your live camera.")
    found = [ENGINE.frame(f) for f in frames]
    if found[-1].width < found[0].width * MIN_GROWTH:
        raise FaceError("FACE_NOT_LIVE", "Move a little closer to the camera while it checks.")
    # The same person throughout (no switching faces mid-check).
    for a, b in zip(found, found[1:], strict=False):
        if float(np.dot(a.embedding, b.embedding)) < MATCH:
            raise FaceError("FACE_NOT_LIVE", "Keep your face in the oval while it checks.")
    return found


def face_code(found: list[FaceFrame]) -> np.ndarray:
    mean = np.mean([f.embedding for f in found], axis=0).astype(np.float32)
    return mean / (float(np.linalg.norm(mean)) or 1.0)


def similarity(found: list[FaceFrame], code: np.ndarray) -> float:
    """The weakest frame's match against a saved face: every frame has to match."""
    return min(float(np.dot(f.embedding, code)) for f in found)


def pack(code: np.ndarray) -> str:
    return base64.b64encode(code.astype(np.float32).tobytes()).decode()


def unpack(value: str) -> np.ndarray:
    code = np.frombuffer(base64.b64decode(value), dtype=np.float32)
    if code.shape != (EMBEDDING_SIZE,):
        raise ValueError("bad face code")
    return code
