"""OCR backends. Default is the open vision-LLM (Qwen2.5-VL) via Ollama;
Tesseract (rus+kaz) is a deterministic fallback for typed pages / GPU-less hosts."""
import base64
import io
from typing import List

from .config import settings
from .schemas import ImageInput, OCRPageResult
from . import llm, pdfdoc
from .prompts import OCR_SYSTEM


def _ocr_qwen(pages: List[ImageInput]) -> List[OCRPageResult]:
    out: List[OCRPageResult] = []
    for i, p in enumerate(pages, start=1):
        b64 = llm.normalize_image_b64(llm.load_image_b64(p))
        text = llm.chat(settings.VISION_MODEL, OCR_SYSTEM,
                        "Transcribe this page.", images_b64=[b64])
        out.append(OCRPageResult(page_no=i, text=text.strip(), confidence=0.9))
    return out


def _ocr_tesseract(pages: List[ImageInput]) -> List[OCRPageResult]:
    import os
    import pytesseract           # imported lazily; only needed for this backend
    from PIL import Image
    from .preproc import preprocess_for_ocr

    # Domain wordlist (era terms/abbreviations) nudges recognition toward the
    # vocabulary that becomes entities downstream.
    cfg_parts = []
    uw = settings.TESSERACT_USER_WORDS
    if uw and os.path.exists(uw):
        cfg_parts.append(f'--user-words "{uw}"')
    if settings.TESSERACT_PSM.strip().isdigit():
        cfg_parts.append(f"--psm {settings.TESSERACT_PSM.strip()}")
    if settings.TESSERACT_OEM.strip().isdigit():
        cfg_parts.append(f"--oem {settings.TESSERACT_OEM.strip()}")
    tess_cfg = " ".join(cfg_parts)

    def preprocess(im):
        return preprocess_for_ocr(im,
                                  filter_ink=settings.OCR_FILTER_INK,
                                  do_deskew=settings.OCR_DESKEW,
                                  binarize=settings.OCR_BINARIZE)

    def run_pass(im, langs):
        data = pytesseract.image_to_data(im, lang=langs, config=tess_cfg,
                                         output_type=pytesseract.Output.DICT)
        confs = [int(c) for c in data["conf"]
                 if str(c).lstrip("-").isdigit() and int(c) >= 0]
        conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        text = pytesseract.image_to_string(im, lang=langs, config=tess_cfg)
        return text.strip(), round(conf, 3)

    # Run each language set separately and keep the most confident pass:
    # the kaz model hallucinates Kazakh letters (ө, қ …) on pure-Russian
    # typewriter pages, which also fools language classification downstream.
    candidates: List[str] = []
    for langs in (settings.TESSERACT_LANGS, "rus", "kaz"):
        if langs and langs not in candidates:
            candidates.append(langs)

    out: List[OCRPageResult] = []
    for i, p in enumerate(pages, start=1):
        raw = base64.b64decode(llm.load_image_b64(p))
        im = preprocess(Image.open(io.BytesIO(raw)))
        best_text, best_conf, best_score = "", -1.0, -1.0
        for langs in candidates:
            try:
                text, conf = run_pass(im, langs)
            except Exception:
                continue  # e.g. language pack missing — try the next one
            score = conf - (_kaz_noise_penalty(text)
                            if settings.OCR_SCRIPT_PENALTY else 0.0)
            if score > best_score:
                best_text, best_conf, best_score = text, conf, score
        out.append(OCRPageResult(page_no=i, text=best_text,
                                 confidence=max(best_conf, 0.0)))
    return out


# Kazakh-only Cyrillic letters. A sprinkling of them in an otherwise Russian page
# is the classic `kaz` language-pack artifact ("тов"→"тоз", "МЕНДЕШЕВ"→"МЕҢДЕШЕВ");
# a genuinely Kazakh page carries them densely and keeps its score.
_KAZ_ONLY = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")


def _kaz_noise_penalty(text: str, low: float = 0.005, high: float = 0.03,
                       penalty: float = 0.2) -> float:
    """Penalty (0..penalty) for implausibly sparse Kazakh-specific letters."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 50:
        return 0.0
    frac = sum(1 for c in letters if c in _KAZ_ONLY) / len(letters)
    if frac <= low:          # none at all → clean Russian, no penalty
        return 0.0
    if frac >= high:         # dense → really Kazakh, no penalty
        return 0.0
    return penalty           # in between → language-pack noise


def _ocr_stub(pages: List[ImageInput]) -> List[OCRPageResult]:
    return [OCRPageResult(page_no=i,
                          text=f"[stub OCR text for page {i}]",
                          confidence=0.5)
            for i, _ in enumerate(pages, start=1)]


def _dispatch(pages: List[ImageInput]) -> List[OCRPageResult]:
    if settings.STUB:
        return _ocr_stub(pages)
    backend = settings.OCR_BACKEND
    if backend == "tesseract":
        return _ocr_tesseract(pages)
    if backend == "surya":
        # Surya integration hook (optional, GPU). Falls back to Qwen if unavailable.
        try:
            from .ocr_surya import ocr_surya  # user-provided optional module
            return ocr_surya(pages)
        except Exception:
            return _ocr_qwen(pages)
    return _ocr_qwen(pages)


def run_ocr(pages: List[ImageInput]) -> List[OCRPageResult]:
    """OCR every page, except pages that already carry exact text (PDF text layer).

    A raw .pdf handed to us is expanded into its pages first, so callers never
    have to know whether they are dealing with a scan or a PDF.
    """
    pages = pdfdoc.expand_inputs(pages)

    results: List[OCRPageResult] = [None] * len(pages)     # type: ignore[list-item]
    todo = [(i, p) for i, p in enumerate(pages) if not (p.text or "").strip()]

    for i, p in enumerate(pages):
        if (p.text or "").strip():
            results[i] = OCRPageResult(page_no=i + 1, text=p.text.strip(),
                                       confidence=1.0, source="pdf_text",
                                       layout_text=p.layout_text)

    if todo:
        got = _dispatch([p for _, p in todo])
        for (i, _), r in zip(todo, got):
            r.page_no = i + 1                              # keep document page order
            results[i] = r
    return results
