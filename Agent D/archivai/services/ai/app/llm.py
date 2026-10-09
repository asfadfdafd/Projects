"""Thin client for the open-source model server (Ollama-compatible API)
plus image-loading helpers. Everything runs locally; no external APIs."""
import base64
import io
import json
import logging
import time
from typing import List, Optional

import httpx
from PIL import Image

from .config import settings
from .schemas import ImageInput

# Model calls are the slow part of every request — and when the model server stalls
# there is otherwise nothing in the log between "request in" and the timeout. Each
# call announces itself and reports how long it took.
log = logging.getLogger("archivai.llm")


# ----------------------------------------------------------------------------
# Image helpers
# ----------------------------------------------------------------------------
def load_image_b64(img: ImageInput) -> str:
    """Return raw base64 (no data: prefix) for an ImageInput."""
    if img.image_b64:
        return _strip_data_prefix(img.image_b64)
    if img.image_url:
        with httpx.Client(timeout=settings.REQUEST_TIMEOUT) as c:
            r = c.get(img.image_url)
            r.raise_for_status()
            return base64.b64encode(r.content).decode()
    raise ValueError("ImageInput requires image_url or image_b64")


def _strip_data_prefix(b64: str) -> str:
    return b64.split(",", 1)[1] if b64.startswith("data:") else b64


def normalize_image_b64(b64: str, max_side: int = 2000) -> str:
    """Downscale very large scans to keep the vision model fast."""
    raw = base64.b64decode(b64)
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    if max(im.size) > max_side:
        ratio = max_side / max(im.size)
        im = im.resize((int(im.width * ratio), int(im.height * ratio)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


# ----------------------------------------------------------------------------
# Ollama calls
# ----------------------------------------------------------------------------
def chat(model: str, system: str, user: str,
         images_b64: Optional[List[str]] = None,
         json_mode: bool = False,
         num_predict: Optional[int] = None) -> str:
    """Call /api/chat. `images_b64` attaches images to the user message
    (vision models). `num_predict` caps the answer length — pass it for structured
    output; leave it None for transcription, which must be free to run long.
    Returns the assistant message content."""
    msg = {"role": "user", "content": user}
    if images_b64:
        msg["images"] = images_b64
    options = {"temperature": 0.1, "num_ctx": settings.LLM_NUM_CTX}
    if num_predict:
        options["num_predict"] = num_predict
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, msg],
        "stream": False,
        "options": options,
    }
    if json_mode:
        payload["format"] = "json"
    log.info("chat → %s (%s) prompt=%d chars, images=%d, num_ctx=%d, "
             "num_predict=%s, timeout=%ss",
             model, settings.LLM_ENDPOINT, len(user), len(images_b64 or []),
             settings.LLM_NUM_CTX, num_predict or "∞", settings.REQUEST_TIMEOUT)
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=settings.REQUEST_TIMEOUT) as c:
            r = c.post(f"{settings.LLM_ENDPOINT}/api/chat", json=payload)
            r.raise_for_status()
            out = r.json()["message"]["content"]
    except Exception as e:
        log.error("chat ✗ %s after %.1fs: %s", model, time.monotonic() - t0, e)
        raise
    log.info("chat ✓ %s in %.1fs → %d chars", model, time.monotonic() - t0, len(out))
    return out


def embed(model: str, texts: List[str]) -> List[List[float]]:
    vectors: List[List[float]] = []
    t0 = time.monotonic()
    log.info("embed → %s, %d text(s), %d chars total",
             model, len(texts), sum(len(t) for t in texts))
    try:
        with httpx.Client(timeout=settings.REQUEST_TIMEOUT) as c:
            for t in texts:
                r = c.post(f"{settings.LLM_ENDPOINT}/api/embeddings",
                           json={"model": model, "prompt": t})
                r.raise_for_status()
                vectors.append(r.json()["embedding"])
    except Exception as e:
        log.error("embed ✗ %s after %.1fs: %s", model, time.monotonic() - t0, e)
        raise
    log.info("embed ✓ %s in %.1fs", model, time.monotonic() - t0)
    return vectors


def parse_json_lenient(raw: str) -> dict:
    """Extract the first JSON object from a model response, tolerating fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)
