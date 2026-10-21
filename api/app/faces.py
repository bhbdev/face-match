"""Face detection + embedding, plus small image helpers shared by the API and scripts."""

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image, ImageOps

from . import config


@dataclass
class DetectedFace:
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    det_score: float
    embedding: np.ndarray  # L2-normalised, float32, shape (512,)

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> float:
        return max(self.width, 0.0) * max(self.height, 0.0)


class FaceEngine:
    """Wraps InsightFace so the model is loaded once per process."""

    def __init__(self) -> None:
        # Only the detector and the recognition model: skips landmark/age/gender models.
        self.app = FaceAnalysis(
            name=config.MODEL_NAME,
            allowed_modules=["detection", "recognition"],
            providers=["CPUExecutionProvider"],
        )
        self.app.prepare(
            ctx_id=-1,
            det_thresh=config.DET_THRESH,
            det_size=(config.DET_SIZE, config.DET_SIZE),
        )

    def analyze(self, img_bgr: np.ndarray, grayscale: bool | None = None) -> list[DetectedFace]:
        if grayscale is None:
            grayscale = config.GRAYSCALE
        img = to_gray_bgr(img_bgr) if grayscale else img_bgr
        found = self.app.get(img)
        return [
            DetectedFace(
                bbox=tuple(float(v) for v in f.bbox),
                det_score=float(f.det_score),
                embedding=np.asarray(f.normed_embedding, dtype=np.float32),
            )
            for f in found
        ]


# ---------------------------------------------------------------- image helpers


def load_image_bytes(data: bytes) -> np.ndarray | None:
    """Decode bytes into a BGR array, honouring EXIF rotation (phone photos)."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def load_image_path(path: Path) -> np.ndarray | None:
    try:
        return load_image_bytes(Path(path).read_bytes())
    except Exception:
        return None


def to_gray_bgr(img_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def limit_size(img_bgr: np.ndarray, max_side: int = config.MAX_QUERY_SIDE) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return img_bgr
    return cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def crop_face(
    img_bgr: np.ndarray,
    bbox: tuple[float, float, float, float],
    margin: float = 0.45,
    size: int = 256,
) -> np.ndarray:
    """Square crop centred on the face with some context (hair, ears), resized to `size`."""
    h, w = img_bgr.shape[:2]
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half = max(x2 - x1, y2 - y1) * (1 + margin) / 2
    left, top = int(max(cx - half, 0)), int(max(cy - half, 0))
    right, bottom = int(min(cx + half, w)), int(min(cy + half, h))
    crop = img_bgr[top:bottom, left:right]
    if crop.size == 0:
        crop = img_bgr
    ch, cw = crop.shape[:2]
    scale = size / max(ch, cw)
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(crop, (max(int(cw * scale), 1), max(int(ch * scale), 1)), interpolation=interp)


def encode_jpeg(img_bgr: np.ndarray, quality: int = 88) -> bytes:
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return buf.tobytes()


def jpeg_data_url(img_bgr: np.ndarray) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(encode_jpeg(img_bgr)).decode("ascii")
