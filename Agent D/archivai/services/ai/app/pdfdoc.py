"""PDF ingest: rasterize pages (poppler) and reuse a digital text layer if present.

Everything downstream — OCR, extraction, the scan viewer — works on ONE IMAGE PER
PAGE, so a PDF is turned into page images as early as possible and the rest of the
pipeline never learns it was a PDF.

Two kinds of PDF arrive in an archive:
  * scanned  — pages are photos; they need the normal OCR pass
  * digital  — pages carry a text layer (born-digital files, or a scan that was
               already OCR'd elsewhere). That text is exact and free, so we use it
               instead of OCR while still keeping the rendered image for the viewer.

poppler (pdftoppm/pdftotext) and pdf2image ship in the AI service image; nothing
here calls a model, so PDF splitting works in stub mode too.
"""
import base64
import io
import subprocess
from typing import List, Optional

import httpx

from .config import settings
from .schemas import ImageInput, PDFPage

_PDF_MAGIC = b"%PDF-"
# base64 of "%PDF" — lets us spot a PDF sent as image_b64 without decoding it all
_PDF_MAGIC_B64 = "JVBERi0"


# ----------------------------------------------------------------------------
# Detection
# ----------------------------------------------------------------------------
def is_pdf_bytes(raw: bytes) -> bool:
    """True for real PDF bytes (a few writers prepend whitespace/junk)."""
    return _PDF_MAGIC in (raw[:1024] if raw else b"")


def is_pdf_url(url: Optional[str]) -> bool:
    if not url:
        return False
    return url.split("?", 1)[0].rstrip("/").lower().endswith(".pdf")


def is_pdf_b64(b64: Optional[str]) -> bool:
    if not b64:
        return False
    b = b64.split(",", 1)[1] if b64.startswith("data:") else b64
    return b.lstrip()[:8].startswith(_PDF_MAGIC_B64)


def looks_like_pdf(img: ImageInput) -> bool:
    """Cheap check used before downloading — never fetches the object."""
    return is_pdf_url(img.image_url) or is_pdf_b64(img.image_b64)


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def load_bytes(img: ImageInput) -> bytes:
    if img.image_b64:
        b = img.image_b64.split(",", 1)[1] if img.image_b64.startswith("data:") else img.image_b64
        return base64.b64decode(b)
    if img.image_url:
        with httpx.Client(timeout=settings.REQUEST_TIMEOUT, follow_redirects=True) as c:
            r = c.get(img.image_url)
            r.raise_for_status()
            return r.content
    raise ValueError("ImageInput requires image_url or image_b64")


def page_count(raw: bytes) -> int:
    """Total pages in the file (may exceed how many we render — see PDF_MAX_PAGES)."""
    try:
        from pdf2image import pdfinfo_from_bytes
        info = pdfinfo_from_bytes(raw, userpw=None, poppler_path=None)
        return int(info.get("Pages") or 0)
    except Exception:
        return 0


# ----------------------------------------------------------------------------
# Rasterization + text layer
# ----------------------------------------------------------------------------
def render_pages(raw: bytes, dpi: Optional[int] = None,
                 max_pages: Optional[int] = None) -> List[str]:
    """Render pages to base64 JPEG, downscaled to PDF_MAX_SIDE (vision models and
    the browser both choke on 600-dpi full-size scans)."""
    from pdf2image import convert_from_bytes
    from PIL import Image

    dpi = int(dpi or settings.PDF_DPI)
    last = max(int(max_pages or settings.PDF_MAX_PAGES), 1)

    images = convert_from_bytes(raw, dpi=dpi, first_page=1, last_page=last, fmt="ppm")
    out: List[str] = []
    for im in images:
        im = im.convert("RGB")
        side = settings.PDF_MAX_SIDE
        if side and max(im.size) > side:
            ratio = side / max(im.size)
            im = im.resize((max(int(im.width * ratio), 1), max(int(im.height * ratio), 1)),
                           Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=settings.PDF_JPEG_QUALITY)
        out.append(base64.b64encode(buf.getvalue()).decode())
    return out


def text_layer(raw: bytes, max_pages: Optional[int] = None,
               layout: bool = False, raw_order: bool = False) -> List[str]:
    """Per-page text via `pdftotext` (page separator = form feed).

    layout=False   → reading order: poppler groups the page into blocks and reads
                     them in order (a two-column page reads column by column).
    layout=True    → `-layout`: columns and indentation kept as spaces, for display.
    raw_order=True → `-raw`: content-stream order. Rescues files that draw text in
                     overlapping runs (template PDFs with an unfilled layer under
                     the real one): block analysis shreds those into fragments,
                     while the drawing order keeps every line whole.

    Returns [] when the tool is missing or the file has no text layer, which is
    the normal case for scanned archives — the caller then falls back to OCR.
    """
    if not settings.PDF_TEXT_LAYER:
        return []
    last = max(int(max_pages or settings.PDF_MAX_PAGES), 1)
    cmd = ["pdftotext", "-q", "-f", "1", "-l", str(last)]
    if layout:
        cmd.append("-layout")
    elif raw_order:
        cmd.append("-raw")
    try:
        proc = subprocess.run(cmd + ["-", "-"], input=raw,
                              capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0 and not proc.stdout:
        return []
    text = proc.stdout.decode("utf-8", errors="replace")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()                       # pdftotext ends the last page with \f
    return [p.strip() for p in pages]


def mean_line_length(text: str) -> float:
    """Average length of a non-empty line — a cheap "is this shredded?" measure.

    Overlapping text runs make block analysis emit many 5–20 character fragments;
    intact prose lines are 40–90. Cheap, language-independent, no heuristics about
    the content itself.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return 0.0
    return sum(len(ln) for ln in lines) / len(lines)


def split(raw: bytes, dpi: Optional[int] = None,
          max_pages: Optional[int] = None) -> List[PDFPage]:
    """PDF bytes -> one PDFPage per rendered page (image + text layer if usable)."""
    if not is_pdf_bytes(raw):
        raise ValueError("not a PDF file")
    images = render_pages(raw, dpi=dpi, max_pages=max_pages)
    texts = text_layer(raw, max_pages=max_pages)                    # reading order
    layouts = text_layer(raw, max_pages=max_pages, layout=True)     # for display
    # Drawing-order fallback, compared per page below. Same cost as any pdftotext
    # run (milliseconds) and only used when it is clearly less shredded.
    raws = (text_layer(raw, max_pages=max_pages, raw_order=True)
            if settings.PDF_TEXT_AUTO_RAW else [])

    pages: List[PDFPage] = []
    for i, img_b64 in enumerate(images):
        t = texts[i].strip() if i < len(texts) else ""
        lay = layouts[i].strip() if i < len(layouts) else ""
        mode = "default"
        if i < len(raws):
            r = raws[i].strip()
            if (mean_line_length(r)
                    > mean_line_length(t) * settings.PDF_RAW_MARGIN):
                t, mode = r, "raw"
        # A sprinkling of characters (page numbers, a stamp caption) is not a text
        # layer — those pages go to OCR like any other scan.
        usable = len(t) >= settings.PDF_TEXT_MIN_CHARS
        pages.append(PDFPage(page_no=i + 1, image_b64=img_b64,
                             text=t if usable else None,
                             layout_text=(lay or None) if usable else None,
                             text_mode=mode if usable else None,
                             has_text_layer=usable))
    return pages


# ----------------------------------------------------------------------------
# Pipeline entry point
# ----------------------------------------------------------------------------
def expand_inputs(pages: List[ImageInput]) -> List[ImageInput]:
    """Replace every PDF entry with one ImageInput per page.

    Non-PDF entries pass through untouched and are never downloaded here (the OCR
    backend fetches them itself). Used as a safety net: the web app normally
    splits PDFs at upload time so page images get their own URLs in object
    storage, but any caller may hand us a raw .pdf and it still works.
    """
    if not pages:
        return pages
    if not any(looks_like_pdf(p) for p in pages):
        return pages

    out: List[ImageInput] = []
    for p in pages:
        if not looks_like_pdf(p):
            out.append(p)
            continue
        try:
            raw = load_bytes(p)
            split_pages = split(raw)
        except Exception:
            out.append(p)                 # unreadable PDF: let the OCR backend report it
            continue
        for sp in split_pages:
            out.append(ImageInput(image_b64=sp.image_b64, text=sp.text,
                                  layout_text=sp.layout_text))
    return out
