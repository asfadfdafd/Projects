"""Grounded RAG answering for the 'Ask ArchivAI' chat assistant.

Stateless: n8n does retrieval (pgvector) + persistence; this module only turns a
question + retrieved contexts into a cited answer using the open LLM.
"""
import re
from typing import List, Tuple

from .config import settings
from .schemas import AnswerRequest, Citation
from . import llm
from .prompts import ANSWER_SYSTEM


def _build_user_prompt(req: AnswerRequest) -> str:
    lines = ["Context passages:"]
    for c in req.contexts:
        src = c.filename or (c.document_id or "")
        lines.append(f"[{c.ref}] ({src}) {c.text}")
    lines.append("")
    lines.append(f"Question: {req.question}")
    lines.append("Answer (cite sources with [ref]):")
    return "\n".join(lines)


def _collect_citations(answer: str, req: AnswerRequest) -> List[Citation]:
    refs = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    by_ref = {c.ref: c for c in req.contexts}
    return [Citation(ref=r, document_id=by_ref[r].document_id, filename=by_ref[r].filename)
            for r in sorted(refs) if r in by_ref]


def _stub_answer(req: AnswerRequest) -> Tuple[str, bool]:
    if not req.contexts:
        return "В архиве не найдено релевантных документов по этому запросу.", False
    first = req.contexts[0]
    return (f"[stub] По имеющимся документам: {first.text[:80]} [{first.ref}].", True)


def answer_question(req: AnswerRequest) -> Tuple[str, List[Citation], bool]:
    if not req.contexts:
        text, grounded = _stub_answer(req) if settings.STUB else (
            "No relevant documents were found in the archive for this question.", False)
        return text, [], grounded

    if settings.STUB:
        text, grounded = _stub_answer(req)
        return text, _collect_citations(text, req), grounded

    system = ANSWER_SYSTEM
    if req.style == "detailed":
        system += (" Answer in detail: a thorough paragraph or two, still fully "
                   "grounded in the cited context.")
    user = _build_user_prompt(req)
    text = llm.chat(settings.TEXT_MODEL, system, user).strip()
    citations = _collect_citations(text, req)
    return text, citations, bool(citations)
