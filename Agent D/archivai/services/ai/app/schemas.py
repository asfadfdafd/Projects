"""Pydantic contracts shared between the AI service and n8n / the web app.

The extraction schema mirrors what Agent D surfaces per document:
type, date, language, sender, recipient, AI summary, and categorized entities
(People, Organizations, Dates, Places, Quantities).
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

EntityType = Literal["person", "organization", "date", "place", "quantity"]


class ImageInput(BaseModel):
    # Provide either a reachable URL (MinIO) or base64 image data.
    image_url: Optional[str] = None
    image_b64: Optional[str] = None
    # Page text that is already known — the text layer of a digital PDF. When set,
    # this page skips OCR entirely (the text is exact; OCR could only make it worse).
    text: Optional[str] = None          # reading order — search, embeddings, LLM
    layout_text: Optional[str] = None   # same page, physical layout kept — display only


class OCRRequest(BaseModel):
    pages: List[ImageInput] = Field(default_factory=list)


class OCRPageResult(BaseModel):
    page_no: int
    text: str
    confidence: float = 0.0
    source: str = "ocr"                 # ocr | pdf_text — where the page text came from
    layout_text: Optional[str] = None   # layout-preserving variant, when available


class OCRResponse(BaseModel):
    pages: List[OCRPageResult]
    backend: str


# ---------------------------------------------------------------------------
# PDF ingest (rasterize + text layer). The web app calls /pdf/split so page
# images get their own object-storage URLs before ingest starts.
# ---------------------------------------------------------------------------
class PDFPage(BaseModel):
    page_no: int
    image_b64: str                      # rendered page, base64 JPEG
    text: Optional[str] = None          # text layer in reading order, if usable
    layout_text: Optional[str] = None   # same text with columns/indentation kept
    text_mode: Optional[str] = None     # default | raw — which extraction won
    has_text_layer: bool = False


class PDFSplitRequest(BaseModel):
    pdf_url: Optional[str] = None       # reachable URL (MinIO)
    pdf_b64: Optional[str] = None       # or the file inline
    dpi: Optional[int] = None           # override PDF_DPI
    max_pages: Optional[int] = None     # override PDF_MAX_PAGES


class PDFSplitResponse(BaseModel):
    page_count: int                     # pages in the file
    rendered: int                       # pages actually returned (<= PDF_MAX_PAGES)
    truncated: bool = False
    text_layer_pages: int = 0
    raw_order_pages: int = 0            # pages rescued by drawing-order extraction
    format: str = "jpeg"
    pages: List[PDFPage] = Field(default_factory=list)


class Party(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None


class Entity(BaseModel):
    name: str
    type: EntityType
    role: Optional[str] = None          # short description / role, LLM-enriched
    surface_form: Optional[str] = None  # exact text as it appeared


class Extraction(BaseModel):
    document_type: Optional[str] = None
    date_text: Optional[str] = None
    language: Optional[str] = None      # Russian | Kazakh | Mixed
    sender: Party = Field(default_factory=Party)
    recipient: Party = Field(default_factory=Party)
    summary: Optional[str] = None
    entities: List[Entity] = Field(default_factory=list)


class TaxonomyType(BaseModel):
    id: str
    label: Optional[str] = None


class ProcessRequest(BaseModel):
    """One-shot: OCR + extraction for a (possibly multi-page) document."""
    pages: List[ImageInput] = Field(default_factory=list)
    # Agent-managed document-type taxonomy (global config); constrains classification.
    taxonomy: Optional[List[TaxonomyType]] = None


class TextChunk(BaseModel):
    """One embedding-sized slice of the document (see chunking.py)."""
    chunk_no: int
    text: str
    page_from: Optional[int] = None
    page_to: Optional[int] = None


class ProcessResponse(BaseModel):
    full_text: str
    confidence: float
    extraction: Extraction
    ocr_backend: str
    extract_backend: str
    page_texts: List[OCRPageResult] = Field(default_factory=list)
    # One vector per chunk: a long document is otherwise a single averaged vector
    # that matches no specific query.
    chunks: List[TextChunk] = Field(default_factory=list)


class ChatContext(BaseModel):
    ref: int                            # citation number shown to the model
    document_id: Optional[str] = None
    filename: Optional[str] = None
    text: str                           # the grounding passage


class AnswerRequest(BaseModel):
    question: str
    contexts: List[ChatContext] = Field(default_factory=list)
    history: List[dict] = Field(default_factory=list)   # [{role, content}] optional
    style: Optional[str] = None                          # concise | detailed (user config)


class Citation(BaseModel):
    ref: int
    document_id: Optional[str] = None
    filename: Optional[str] = None


class AnswerResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    grounded: bool = True               # False when no context supported an answer


class AgentAction(BaseModel):
    """One validated-shape config change the agent wants to apply.
    Semantics are re-validated in Postgres (set_config) — the LLM never writes SQL."""
    key: str                                 # search | dashboard | taxonomy | chat
    patch: dict                              # fields to change (arrays replace wholesale)
    reason: Optional[str] = None


class AgentCommand(BaseModel):
    """One operator command (Phase 5.5). Executed by Postgres agent_run() /
    fanned out by n8n — never by this service."""
    tool: str                                # resolve_entities | recompute_stats | reprocess_documents | open_search
    params: dict = Field(default_factory=dict)
    reason: Optional[str] = None


class AgentRequest(BaseModel):
    message: str
    history: List[dict] = Field(default_factory=list)    # [{role, content}]
    current_config: dict = Field(default_factory=dict)   # get_all_config(user)
    capabilities: dict = Field(default_factory=dict)     # agent_capabilities()
    tools: dict = Field(default_factory=dict)            # agent_tools()


class AgentResponse(BaseModel):
    reply: str
    actions: List[AgentAction] = Field(default_factory=list)
    commands: List[AgentCommand] = Field(default_factory=list)


class EmbedRequest(BaseModel):
    texts: List[str]


class EmbedResponse(BaseModel):
    model: str
    dim: int
    vectors: List[List[float]]
