"""Split a document into embedding-sized chunks.

One vector per document loses long files: the embedder truncates at its window, and
the average of a 12-page paper points at nothing in particular — a query about one
paragraph matches it no better than any other document. The database has always
keyed embeddings by (document_id, chunk_no) and both search and RAG take the BEST
chunk per document, so the only missing piece was producing more than one.

Page boundaries are the natural cut: a page is a self-contained unit and a citation
can point at it. Long pages are split further on paragraph, then sentence
boundaries, with an overlap so a sentence sitting on the cut stays findable. Short
pages (a stamp, a cover sheet) are merged with their neighbours — embedding
hundreds of near-empty fragments only adds noise and cost.
"""
import re
from typing import List, Optional, Tuple

from .config import settings
from .schemas import OCRPageResult, TextChunk

# A unit of text plus the page range it came from.
Unit = Tuple[str, Optional[int], Optional[int]]

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?…])\s+|\n")


def _hard_split(text: str, limit: int) -> List[str]:
    """Last resort: cut a run of text that has no usable boundary at all."""
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def _split_long(text: str) -> List[str]:
    """Paragraph → sentence → character, packing pieces up to CHUNK_MAX_CHARS."""
    limit = settings.CHUNK_MAX_CHARS
    overlap = settings.CHUNK_OVERLAP

    parts: List[str] = []
    for para in _PARAGRAPH.split(text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= limit:
            parts.append(para)
            continue
        for sentence in _SENTENCE.split(para):
            sentence = sentence.strip()
            if not sentence:
                continue
            parts.extend([sentence] if len(sentence) <= limit
                         else _hard_split(sentence, limit))

    out: List[str] = []
    buf = ""
    for part in parts:
        candidate = (buf + "\n" + part).strip() if buf else part
        if len(candidate) <= limit:
            buf = candidate
            continue
        if buf:
            out.append(buf)
            # carry the tail over so a thought split across the cut is still findable
            tail = buf[-overlap:] if overlap else ""
            buf = (tail + "\n" + part).strip() if tail else part
        else:
            buf = part
    if buf:
        out.append(buf)
    return out


def _merge_short(units: List[Unit]) -> List[Unit]:
    """Glue neighbouring units that are too small to carry meaning on their own."""
    merged: List[Unit] = []
    for text, first, last in units:
        if merged:
            prev_text, prev_first, prev_last = merged[-1]
            if (len(prev_text) < settings.CHUNK_MIN_CHARS
                    and len(prev_text) + len(text) <= settings.CHUNK_MAX_CHARS):
                merged[-1] = (prev_text + "\n\n" + text,
                              prev_first,
                              last if last is not None else prev_last)
                continue
        merged.append((text, first, last))
    return merged


def build_chunks(page_texts: List[OCRPageResult],
                 full_text: str = "") -> List[TextChunk]:
    """Document text -> chunks to embed. Always returns at least one chunk when
    there is any text at all, so a document is never left unsearchable."""
    units: List[Unit] = []
    for p in page_texts or []:
        text = (p.text or "").strip()
        if not text:
            continue
        if len(text) <= settings.CHUNK_MAX_CHARS:
            units.append((text, p.page_no, p.page_no))
        else:
            units.extend((piece, p.page_no, p.page_no) for piece in _split_long(text))

    if not units:                       # vision one-shot, or pages without text
        whole = (full_text or "").strip()
        if not whole:
            return []
        units = [(piece, None, None) for piece in
                 ([whole] if len(whole) <= settings.CHUNK_MAX_CHARS else _split_long(whole))]

    units = _merge_short(units)[:settings.CHUNK_MAX_COUNT]
    return [TextChunk(chunk_no=i, text=t, page_from=a, page_to=b)
            for i, (t, a, b) in enumerate(units)]
