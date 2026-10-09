"""ArchivAI AI service — OCR + structured extraction + embeddings.

n8n calls these endpoints; nothing here touches the database directly
(the database is written by n8n), keeping this service stateless and swappable.
"""
from fastapi import FastAPI, HTTPException

from .config import settings
from .schemas import (
    OCRRequest, OCRResponse,
    ProcessRequest, ProcessResponse,
    EmbedRequest, EmbedResponse,
    AnswerRequest, AnswerResponse,
    AgentRequest, AgentResponse,
    PDFSplitRequest, PDFSplitResponse, ImageInput,
)
from . import ocr, extract, embed, answer, agent, pdfdoc, chunking

app = FastAPI(title="ArchivAI AI Service", version="0.1.0")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "stub": settings.STUB,
        "ocr_backend": settings.OCR_BACKEND,
        "extract_backend": settings.EXTRACT_BACKEND,
        "vision_model": settings.VISION_MODEL,
        "text_model": settings.TEXT_MODEL,
        "embed_model": settings.EMBED_MODEL,
        "pdf": {"dpi": settings.PDF_DPI, "max_pages": settings.PDF_MAX_PAGES,
                "text_layer": settings.PDF_TEXT_LAYER},
    }


@app.post("/ocr", response_model=OCRResponse)
def do_ocr(req: OCRRequest):
    if not req.pages:
        raise HTTPException(400, "no pages provided")
    pages = ocr.run_ocr(req.pages)
    # Apply the same optional proofreading as /process, so scripts/ocr_eval.py
    # benchmarks exactly what the pipeline will store.
    if settings.OCR_LLM_CORRECT and not settings.STUB:
        for p, fixed in zip(pages, extract._correct_ocr_texts(pages)):
            p.text = fixed
    return OCRResponse(pages=pages, backend=settings.OCR_BACKEND)


@app.post("/process", response_model=ProcessResponse)
def do_process(req: ProcessRequest):
    if not req.pages:
        raise HTTPException(400, "no pages provided")
    full_text, conf, extraction, page_texts = extract.process_document(req.pages, req.taxonomy)
    # n8n embeds and stores these one row per chunk (upsert_embedding).
    chunks = chunking.build_chunks(page_texts, full_text)
    return ProcessResponse(
        full_text=full_text,
        confidence=conf,
        extraction=extraction,
        ocr_backend=settings.OCR_BACKEND,
        extract_backend=settings.EXTRACT_BACKEND,
        page_texts=page_texts,
        chunks=chunks,
    )


@app.post("/pdf/split", response_model=PDFSplitResponse)
def do_pdf_split(req: PDFSplitRequest):
    """Rasterize a PDF into page images (+ its text layer when it has one).

    The web app calls this at upload time and stores each page image in object
    storage, so ingest, the viewer and reprocessing all see a normal multi-page
    document. No model is involved — this works in stub mode too.
    """
    if not req.pdf_url and not req.pdf_b64:
        raise HTTPException(400, "pdf_url or pdf_b64 required")
    try:
        raw = pdfdoc.load_bytes(ImageInput(image_url=req.pdf_url, image_b64=req.pdf_b64))
    except Exception as e:
        raise HTTPException(400, f"cannot read PDF: {e}")
    if not pdfdoc.is_pdf_bytes(raw):
        raise HTTPException(400, "file is not a PDF")
    try:
        pages = pdfdoc.split(raw, dpi=req.dpi, max_pages=req.max_pages)
    except Exception as e:
        raise HTTPException(422, f"PDF split failed: {e}")

    total = pdfdoc.page_count(raw) or len(pages)
    return PDFSplitResponse(
        page_count=total,
        rendered=len(pages),
        truncated=total > len(pages),
        text_layer_pages=sum(1 for p in pages if p.has_text_layer),
        raw_order_pages=sum(1 for p in pages if p.text_mode == "raw"),
        pages=pages,
    )


@app.post("/embed", response_model=EmbedResponse)
def do_embed(req: EmbedRequest):
    if not req.texts:
        raise HTTPException(400, "no texts provided")
    vectors = embed.embed_texts(req.texts)
    return EmbedResponse(model=settings.EMBED_MODEL, dim=settings.EMBED_DIM, vectors=vectors)


@app.post("/answer", response_model=AnswerResponse)
def do_answer(req: AnswerRequest):
    if not req.question.strip():
        raise HTTPException(400, "no question provided")
    text, citations, grounded = answer.answer_question(req)
    return AnswerResponse(answer=text, citations=citations, grounded=grounded)


@app.post("/agent", response_model=AgentResponse)
def do_agent(req: AgentRequest):
    """Phase 5 configuration agent: NL request -> {reply, actions[]}.
    Stateless; n8n applies the actions via Postgres agent_apply()."""
    if not req.message.strip():
        raise HTTPException(400, "no message provided")
    return agent.run_agent(req)
