"""Structured extraction: turn document image(s)/text into the Extraction schema.

Two backends:
  - qwen_vl:     one-shot vision call (OCR + fields together) — best for handwriting
  - ollama_text: run OCR first, then a text LLM over the transcript
"""
import logging
from typing import List, Optional

from .config import settings
from .schemas import ImageInput, Extraction, Party, Entity, OCRPageResult, TaxonomyType
from . import llm, ocr, pdfdoc
from .prompts import EXTRACT_SYSTEM, EXTRACT_TEXT_SYSTEM, OCR_CORRECT_SYSTEM, taxonomy_clause


def _correct_ocr_texts(page_texts: List[OCRPageResult]) -> List[str]:
    """Opt-in LLM proofreading pass (OCR_LLM_CORRECT=1). Pages keep the RAW OCR
    (provenance); the corrected text feeds full_text/extraction/search.

    MEASURED: on qwen2.5:3b this HURTS (CER 0.202 → 0.565) — small models rewrite
    instead of correcting. Hence the strict guards below and the default OFF;
    re-benchmark with scripts/ocr_eval.py before enabling on a bigger model.
    """
    import difflib

    out: List[str] = []
    for p in page_texts:
        t = p.text
        if (settings.OCR_LLM_CORRECT and not settings.STUB
                and len(t.strip()) >= 40):
            try:
                fixed = llm.chat(settings.TEXT_MODEL, OCR_CORRECT_SYSTEM,
                                 t[:6000]).strip()
                # Accept only a light touch-up: similar length AND high character
                # similarity. Anything that looks like a rewrite is discarded.
                ratio = len(fixed) / max(len(t), 1)
                sim = difflib.SequenceMatcher(None, t, fixed).ratio() if fixed else 0.0
                if fixed and 0.9 <= ratio <= 1.1 and sim >= 0.85:
                    t = fixed
            except Exception:
                pass  # correction is best-effort; raw text always survives
        out.append(t)
    return out

VALID_TYPES = {"person", "organization", "date", "place", "quantity"}

# Small models label entities with whatever word fits the document ("author" on a
# paper, "учреждение" on a decree). Those used to be dropped silently, leaving a
# document with a summary and zero entities. Map the near-misses; anything still
# unknown is dropped WITH a log line, so the next surprise is visible.
TYPE_SYNONYMS = {
    # → person
    "people": "person", "persons": "person", "human": "person", "individual": "person",
    "author": "person", "writer": "person", "signatory": "person", "official": "person",
    "человек": "person", "люди": "person", "автор": "person", "лицо": "person",
    "персона": "person", "фамилия": "person", "адам": "person",
    # → organization
    "org": "organization", "organisation": "organization", "organizations": "organization",
    "institution": "organization", "university": "organization", "college": "organization",
    "company": "organization", "publisher": "organization", "journal": "organization",
    "conference": "organization", "department": "organization", "ministry": "organization",
    "committee": "organization", "agency": "organization", "group": "organization",
    "организация": "organization", "учреждение": "organization", "ведомство": "organization",
    "министерство": "organization", "комитет": "organization", "ұйым": "organization",
    # → date
    "dates": "date", "year": "date", "years": "date", "time": "date", "datetime": "date",
    "period": "date", "дата": "date", "год": "date", "время": "date", "күн": "date",
    # → place
    "location": "place", "locations": "place", "city": "place", "country": "place",
    "region": "place", "geo": "place", "address": "place", "territory": "place",
    "место": "place", "город": "place", "страна": "place", "регион": "place",
    "местность": "place", "жер": "place",
    # → quantity
    "quantities": "quantity", "number": "quantity", "numbers": "quantity",
    "amount": "quantity", "percentage": "quantity", "percent": "quantity",
    "measure": "quantity", "measurement": "quantity", "money": "quantity",
    "количество": "quantity", "число": "quantity", "сумма": "quantity",
    "объем": "quantity", "объём": "quantity", "саны": "quantity",
}

log = logging.getLogger("archivai.extract")


def normalize_type(raw_type: str) -> Optional[str]:
    """Map a model-supplied entity type onto the schema, or None if it is unknown."""
    t = str(raw_type or "").lower().strip().rstrip(".")
    if t in VALID_TYPES:
        return t
    t = t.replace("-", "_").replace(" ", "_")
    if t in VALID_TYPES:
        return t
    return TYPE_SYNONYMS.get(t)


def clip_for_model(text: str, limit: Optional[int] = None) -> str:
    """Keep a long transcript inside the model's context window.

    Overflowing it does not raise — the prompt is silently cut and the model
    answers with empty JSON, which is how a 12-page PDF ends up with no summary
    and no entities. Keep the head (title, sender, date) and the tail (signature,
    date stamp) and drop the middle, marking the cut so it is visible in logs.
    """
    limit = settings.EXTRACT_MAX_CHARS if limit is None else limit
    if not limit or len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = limit - head
    log.warning("extraction input clipped: %d → %d chars (EXTRACT_MAX_CHARS)",
                len(text), limit)
    return text[:head] + "\n\n[…]\n\n" + text[-tail:]


def _text_field(v) -> Optional[str]:
    """A field the schema types as text, however the model chose to phrase it."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        parts = [_text_field(x) for x in v]
        joined = ", ".join(p for p in parts if p)
        return joined or None
    if isinstance(v, dict):                      # {"name": …} for a plain text field
        return _text_field(v.get("name") or v.get("value") or v.get("text"))
    return None


def _party(v) -> Party:
    """sender/recipient: an object, or just a name — both are seen in the wild."""
    if isinstance(v, dict):
        return Party(name=_text_field(v.get("name") or v.get("value")),
                     role=_text_field(v.get("role") or v.get("title")))
    return Party(name=_text_field(v))


def _entity_items(raw: dict) -> List[dict]:
    """Normalize the shapes small models actually emit for `entities`:

        [{"name": …, "type": …}]        the schema we ask for
        ["Домков", "КП(б)К"]           bare names, type left to us
        {"person": ["Домков"], …}      grouped by type
    """
    ents = raw.get("entities")
    out: List[dict] = []
    if isinstance(ents, dict):
        for group, value in ents.items():
            items = value if isinstance(value, list) else [value]
            for item in items:
                if isinstance(item, dict):
                    out.append({**item, "type": item.get("type") or group})
                elif item is not None:
                    out.append({"name": item, "type": group})
    elif isinstance(ents, list):
        for item in ents:
            if isinstance(item, dict):
                out.append(item)
            elif item is not None:
                out.append({"name": item, "type": None})
    return out


def _coerce(raw: dict) -> Extraction:
    """Validate/normalize a raw model output into an Extraction.

    Small models answer in whatever shape they feel like — the schema is a request,
    not a guarantee. Everything here tolerates the common variants and drops (with a
    log line) only what cannot be understood at all.
    """
    ents: List[Entity] = []
    dropped: List[str] = []
    items = _entity_items(raw)
    for e in items:
        name = _text_field(e.get("name") or e.get("entity") or e.get("value")
                           or e.get("text"))
        t = normalize_type(e.get("type") or e.get("category") or e.get("label")
                           or e.get("kind"))
        if not name:
            continue
        if not t:
            dropped.append(f"{name}:{e.get('type')}")
            continue
        ents.append(Entity(name=name, type=t, role=_text_field(e.get("role")),
                           surface_form=_text_field(e.get("surface_form")) or name))
    if dropped:
        log.warning("dropped %d entities with unmapped types: %s",
                    len(dropped), ", ".join(dropped[:10]))
    if items and not ents:
        log.warning("extraction listed %d entities, none usable", len(items))

    return Extraction(
        document_type=_text_field(raw.get("document_type") or raw.get("type")),
        date_text=_text_field(raw.get("date_text") or raw.get("date")),
        language=_text_field(raw.get("language")),
        sender=_party(raw.get("sender")),
        recipient=_party(raw.get("recipient")),
        summary=_text_field(raw.get("summary")),
        entities=_dedupe(ents),
    )


def _extraction_from(raw_txt: str, taxonomy: Optional[List[TaxonomyType]]) -> Extraction:
    """Parse + normalize a model answer; never let its shape fail the document.

    An archive would rather have a searchable document with empty fields than a
    failed one: the text, pages and embeddings are already earned by this point,
    and a human can fill the rest in the UI. The raw answer goes to the log so the
    prompt (or the model) can be fixed.
    """
    try:
        ex = _coerce(llm.parse_json_lenient(raw_txt))
    except Exception as e:
        log.error("extraction output unusable (%s) — keeping the text, fields left "
                  "empty. Model said: %s", e, (raw_txt or "")[:300].replace("\n", " "))
        return Extraction()
    ex.document_type = _snap_type(ex.document_type, taxonomy)
    return ex


def _dedupe(ents: List[Entity]) -> List[Entity]:
    seen = {}
    for e in ents:
        key = (e.type, e.name.casefold())
        if key not in seen:
            seen[key] = e
    return list(seen.values())


def _stub_extraction(full_text: str, taxonomy: Optional[List[TaxonomyType]] = None) -> Extraction:
    # Deterministic + assertable: with a custom taxonomy the stub classifies as its
    # FIRST type (the agent stub prepends newly added types), else the default.
    return Extraction(
        document_type=(taxonomy[0].id if taxonomy else "official_correspondence"),
        date_text="19/II 194г.",
        language="Mixed",
        sender=Party(name="Домков", role="Секретарь Д/П Обкома КП(б)К"),
        recipient=Party(name="тов. Кулпову", role="Секретарь ЦК КП(б)К"),
        summary="[stub] Официальное письмо. Тестовое резюме документа.",
        entities=[
            Entity(name="Домков", type="person", role="секретарь обкома"),
            Entity(name="КП(б)К", type="organization", role="Коммунистическая партия"),
            Entity(name="Казахстан", type="place", role=None),
            Entity(name="19/II 194г.", type="date", role=None),
        ],
    )


def _snap_type(doc_type: Optional[str],
               taxonomy: Optional[List[TaxonomyType]]) -> Optional[str]:
    """Small-model accommodation: snap near-miss document_type to a valid taxonomy
    id ('decreet' → 'decree'). Exact ids pass; unknown-and-not-close stays as-is."""
    if not taxonomy or not doc_type:
        return doc_type
    ids = [t.id for t in taxonomy]
    if doc_type in ids:
        return doc_type
    low = doc_type.lower().strip()
    for i in ids:
        if low.startswith(i) or i.startswith(low):
            return i
    return doc_type


def process_document(pages: List[ImageInput],
                     taxonomy: Optional[List[TaxonomyType]] = None
                     ) -> tuple[str, float, Extraction, List[OCRPageResult]]:
    """Returns (full_text, confidence, extraction, page_texts)."""
    # A raw .pdf becomes one entry per page here; digital PDFs also bring their
    # text layer along, so those pages never touch a model for transcription.
    pages = pdfdoc.expand_inputs(pages)

    if settings.STUB:
        page_texts = ocr.run_ocr(pages)
        full = "\n\n".join(p.text for p in page_texts)
        return full, 0.5, _stub_extraction(full, taxonomy), page_texts

    tax = taxonomy_clause(taxonomy)

    # Every page already has exact text (digital PDF) → skip the vision model and
    # extract fields from that text; the vision pass could only degrade it.
    has_full_text_layer = bool(pages) and all((p.text or "").strip() for p in pages)
    # One vision call can only carry a few page images before the model starts
    # dropping pages — and only page 1 would get a transcript anyway. Long documents
    # (the norm for PDFs) are OCR'd page by page, then the fields come from the text.
    one_shot_fits = len(pages) <= settings.VISION_ONESHOT_MAX_PAGES

    if settings.EXTRACT_BACKEND == "qwen_vl" and not has_full_text_layer and one_shot_fits:
        # One-shot vision: attach all page images, get transcript + fields together.
        imgs = [llm.normalize_image_b64(llm.load_image_b64(p)) for p in pages]
        raw_txt = llm.chat(settings.VISION_MODEL, EXTRACT_SYSTEM + tax,
                           "Extract the document.", images_b64=imgs, json_mode=True,
                           num_predict=settings.EXTRACT_NUM_PREDICT)
        try:
            full = llm.parse_json_lenient(raw_txt).get("full_text") or ""
        except Exception:
            full = ""                    # _extraction_from logs the bad answer below
        # The one-shot call returns ONE transcript for the whole document, but n8n
        # writes a `pages` row per entry here and the viewer needs every page image.
        # So: page 1 carries the transcript, the remaining pages are placeholders
        # that keep their image and position (full_text feeds search either way).
        # Matters most for PDFs, where multi-page is the norm.
        page_texts = [OCRPageResult(page_no=1, text=full, confidence=0.9,
                                    source="vision_oneshot")]
        page_texts += [OCRPageResult(page_no=i, text="", confidence=0.0,
                                     source="vision_oneshot")
                       for i in range(2, len(pages) + 1)]
        return full, 0.9, _extraction_from(raw_txt, taxonomy), page_texts

    # ollama_text (or a digital PDF): text first, then extraction over the transcript
    page_texts = ocr.run_ocr(pages)
    full = "\n\n".join(_correct_ocr_texts(page_texts))
    conf = sum(p.confidence for p in page_texts) / max(len(page_texts), 1)
    raw_txt = llm.chat(settings.TEXT_MODEL, EXTRACT_TEXT_SYSTEM + tax,
                       clip_for_model(full), json_mode=True,
                       num_predict=settings.EXTRACT_NUM_PREDICT)
    return full, round(conf, 3), _extraction_from(raw_txt, taxonomy), page_texts
