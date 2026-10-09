"""Runtime configuration, read from environment (see .env.example)."""
import os


class Settings:
    # Model backends
    OCR_BACKEND: str = os.getenv("OCR_BACKEND", "qwen_vl")          # qwen_vl | tesseract | surya
    EXTRACT_BACKEND: str = os.getenv("EXTRACT_BACKEND", "qwen_vl")  # qwen_vl | ollama_text

    # Open-source model server (Ollama-compatible API)
    LLM_ENDPOINT: str = os.getenv("LLM_ENDPOINT", "http://ollama:11434")
    VISION_MODEL: str = os.getenv("VISION_MODEL", "qwen2.5vl:7b")
    TEXT_MODEL: str = os.getenv("TEXT_MODEL", "qwen2.5:7b-instruct")
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "bge-m3")
    EMBED_DIM: int = int(os.getenv("EMBED_DIM", "1024"))

    # Ollama defaults to a 4k context and unlimited generation. A long transcript
    # then overflows the context, and in JSON mode a small model can keep generating
    # until it fills what is left — which looks exactly like a hung request. Both
    # limits are therefore set explicitly on every call.
    LLM_NUM_CTX: int = int(os.getenv("LLM_NUM_CTX", "8192"))
    # Cap for structured extraction answers (JSON: fields + summary + entities).
    # OCR is deliberately left uncapped — a dense page can be a long transcript.
    EXTRACT_NUM_PREDICT: int = int(os.getenv("EXTRACT_NUM_PREDICT", "1536"))

    TESSERACT_LANGS: str = os.getenv("TESSERACT_LANGS", "rus+kaz")

    # OCR preprocessing for aged scans (measure changes with scripts/ocr_eval.py)
    OCR_FILTER_INK: bool = os.getenv("OCR_FILTER_INK", "1") == "1"   # whiten red edits / blue stamps
    OCR_DESKEW: bool = os.getenv("OCR_DESKEW", "1") == "1"
    OCR_BINARIZE: bool = os.getenv("OCR_BINARIZE", "1") == "1"       # Otsu for faded type
    # Tesseract page-segmentation mode ("" = auto/psm 3). For uniform typewriter
    # pages try 4 (single column) or 6 (uniform block) — benchmark with ocr_eval.
    TESSERACT_PSM: str = os.getenv("TESSERACT_PSM", "")
    # OCR engine mode ("" = default 3; 1 = LSTM only, often better on typewriting)
    TESSERACT_OEM: str = os.getenv("TESSERACT_OEM", "")
    # Penalize language passes that sprinkle a FEW Kazakh-only letters into an
    # otherwise Russian page (kaz pack noise: "тов"→"тоз", "МЕНДЕШЕВ"→"МЕҢДЕШЕВ").
    # A genuinely Kazakh page has many such letters and keeps its score.
    OCR_SCRIPT_PENALTY: bool = os.getenv("OCR_SCRIPT_PENALTY", "1") == "1"
    # Domain wordlist (era terms, org abbreviations) passed to tesseract.
    TESSERACT_USER_WORDS: str = os.getenv(
        "TESSERACT_USER_WORDS",
        os.path.join(os.path.dirname(__file__), "data", "user_words_ru_kz.txt"))
    # Optional LLM pass that fixes OCR-level errors in page text (opt-in: one
    # extra model call per page; pages keep the RAW text, full_text gets the fix).
    OCR_LLM_CORRECT: bool = os.getenv("OCR_LLM_CORRECT", "0") == "1"

    # How many page images the one-shot vision call may carry. Beyond this the
    # model starts losing pages, so long documents (typical for PDFs) are OCR'd
    # page by page and the fields are extracted from the transcript instead.
    VISION_ONESHOT_MAX_PAGES: int = int(os.getenv("VISION_ONESHOT_MAX_PAGES", "4"))

    # Longest transcript handed to the extraction model. Beyond the model's context
    # window the prompt is silently truncated and the answer comes back empty — a
    # 12-page PDF is enough to hit that. We clip explicitly instead: head + tail,
    # which is where document_type/sender/date/signature live. 0 = no limit.
    EXTRACT_MAX_CHARS: int = int(os.getenv("EXTRACT_MAX_CHARS", "12000"))

    # ---------- Chunking for embeddings ----------
    # A document is embedded chunk by chunk (page boundaries first). One vector for
    # a whole 12-page file matches nothing in particular; search and RAG both score
    # the best chunk, so smaller units make long documents findable.
    CHUNK_MAX_CHARS: int = int(os.getenv("CHUNK_MAX_CHARS", "1800"))
    CHUNK_MIN_CHARS: int = int(os.getenv("CHUNK_MIN_CHARS", "400"))   # merge below this
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "200"))       # carry-over on a cut
    CHUNK_MAX_COUNT: int = int(os.getenv("CHUNK_MAX_COUNT", "200"))   # cost ceiling per doc

    # ---------- PDF ingest ----------
    # PDFs are rendered to one image per page (poppler), so the rest of the
    # pipeline treats them exactly like scans. 200 dpi is the sweet spot for
    # OCR of typewritten pages; higher mostly costs time.
    PDF_DPI: int = int(os.getenv("PDF_DPI", "200"))
    PDF_MAX_PAGES: int = int(os.getenv("PDF_MAX_PAGES", "100"))
    PDF_MAX_SIDE: int = int(os.getenv("PDF_MAX_SIDE", "2000"))     # downscale before OCR
    PDF_JPEG_QUALITY: int = int(os.getenv("PDF_JPEG_QUALITY", "85"))
    # Use the PDF's own text layer instead of OCR when it has one (digital PDFs:
    # exact text, no model call). Scanned PDFs have none and fall back to OCR.
    PDF_TEXT_LAYER: bool = os.getenv("PDF_TEXT_LAYER", "1") == "1"
    # Below this many characters a "text layer" is just page numbers/stamps → OCR.
    PDF_TEXT_MIN_CHARS: int = int(os.getenv("PDF_TEXT_MIN_CHARS", "120"))
    # Some PDFs (journal/report templates) draw overlapping text runs — an unfilled
    # template layer under the real one. Poppler's block analysis shreds those into
    # fragments, while drawing order (`-raw`) keeps lines whole. Extract both and
    # keep the page whose lines are longer by at least PDF_RAW_MARGIN.
    PDF_TEXT_AUTO_RAW: bool = os.getenv("PDF_TEXT_AUTO_RAW", "1") == "1"
    PDF_RAW_MARGIN: float = float(os.getenv("PDF_RAW_MARGIN", "1.25"))

    # When true, models are not called; deterministic stub output is returned.
    # Lets the pipeline + contracts be tested without GPU/models present.
    STUB: bool = os.getenv("AI_STUB", "0") in ("1", "true", "True")

    REQUEST_TIMEOUT: float = float(os.getenv("AI_REQUEST_TIMEOUT", "180"))


settings = Settings()
