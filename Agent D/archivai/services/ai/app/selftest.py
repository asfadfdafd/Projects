"""Offline smoke test of the AI service contract (no models required).

Run:  AI_STUB=1 python -m app.selftest
It exercises the /process and /embed logic in stub mode and validates the
shape n8n depends on. Exits non-zero on failure.
"""
import base64
import os
import sys

os.environ.setdefault("AI_STUB", "1")

from .schemas import (                                        # noqa: E402
    ImageInput, AnswerRequest, ChatContext, AgentRequest, TaxonomyType,
)
from . import extract, embed, llm, answer, agent, ocr         # noqa: E402


def check(cond, msg):
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"ok: {msg}")


def settings_chunk_max():
    from .config import settings
    return settings.CHUNK_MAX_CHARS


def _tiny_pdf(pages_lines) -> bytes:
    """A minimal multi-page PDF with a real text layer — fixture for the PDF checks
    (keeps the repo free of binary test files)."""
    n = len(pages_lines)
    page_ids = [4 + 2 * i for i in range(n)]
    content_ids = [5 + 2 * i for i in range(n)]
    kids = b" ".join(b"%d 0 R" % p for p in page_ids)
    objs = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % n),
        (3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ]
    for i, lines in enumerate(pages_lines):
        # Left text block + a right-margin column (archive stamp), so the fixture
        # has a real two-column layout: `pdftotext -layout` keeps them side by side,
        # reading order lists them one after the other.
        body = ("BT /F1 12 Tf 50 760 Td 16 TL\n"
                + "".join("(%s) Tj T*\n" % ln for ln in lines)
                + "ET\n"
                + "BT /F1 12 Tf 430 760 Td 16 TL\n"
                + "(Arch. N 17) Tj T*\n(sheet %d) Tj T*\n" % (i + 1)
                + "ET").encode("latin-1")
        objs.append((page_ids[i],
                     b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources "
                     b"<< /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content_ids[i]))
        objs.append((content_ids[i],
                     b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"))

    out, offsets = bytearray(b"%PDF-1.4\n"), {}
    for num, body in sorted(objs):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    xref, top = len(out), max(offsets) + 1
    out += b"xref\n0 %d\n" % top + b"0000000000 65535 f \n"
    for i in range(1, top):
        out += b"%010d 00000 n \n" % offsets.get(i, 0)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (top, xref)
    return bytes(out)


def main():
    pages = [ImageInput(image_b64="ZmFrZQ=="), ImageInput(image_b64="ZmFrZQ==")]
    full, conf, ex, page_texts = extract.process_document(pages)

    check(isinstance(full, str) and full, "process returns full_text")
    check(0.0 <= conf <= 1.0, "confidence in [0,1]")
    check(ex.document_type, "extraction has document_type")
    check(ex.language in ("Russian", "Kazakh", "Mixed"), "language valid")
    check(len(ex.entities) > 0, "entities extracted")
    check(all(e.type in {"person", "organization", "date", "place", "quantity"}
              for e in ex.entities), "entity types valid")
    check(len(page_texts) == 2, "page_texts per page")

    vecs = embed.embed_texts(["привет", "сәлем"])
    check(len(vecs) == 2, "embed returns one vector per text")
    check(len(vecs[0]) == 1024, "embedding dim = 1024")

    parsed = llm.parse_json_lenient('```json\n{"a": 1, "b": [2,3]}\n```')
    check(parsed == {"a": 1, "b": [2, 3]}, "lenient JSON parser handles fences")

    # RAG chat answer (stub): cites the context and stays grounded
    req = AnswerRequest(question="Кто такой Абай?", contexts=[
        ChatContext(ref=1, document_id="d1", filename="10.png", text="Абай Кунанбаев — поэт."),
    ])
    a_text, a_cites, grounded = answer.answer_question(req)
    check(isinstance(a_text, str) and a_text, "answer returns text")
    check(grounded and len(a_cites) == 1 and a_cites[0].ref == 1, "answer is grounded + cited")

    empty = answer.answer_question(AnswerRequest(question="?", contexts=[]))
    check(empty[2] is False, "no-context answer is flagged not grounded")

    # Taxonomy-constrained extraction (stub classifies as the first taxonomy id)
    tax = [TaxonomyType(id="protokol", label="Протокол"),
           TaxonomyType(id="report", label="Отчёт")]
    _, _, ex_tax, _ = extract.process_document(pages, tax)
    check(ex_tax.document_type == "protokol", "stub extraction honors taxonomy[0].id")
    check(extract._snap_type("decreet", [TaxonomyType(id="decree"),
                                         TaxonomyType(id="report")]) == "decree",
          "near-miss document_type snaps to taxonomy id (decreet → decree)")
    check(extract._snap_type("сводка", [TaxonomyType(id="decree")]) == "сводка",
          "unknown-and-not-close type passes through unchanged")

    # Phase 5 agent (stub rules → structured actions, never SQL)
    base_cfg = {
        "search": {"vector_weight": 0.7, "keyword_weight": 0.3},
        "dashboard": {"widgets": ["kpi_cards", "entity_distribution", "top_entities",
                                  "language_distribution", "recent_activity", "timeline"],
                      "top_n": 5},
        "taxonomy": {"document_types": [{"id": "official_correspondence",
                                         "label": "Официальная переписка"},
                                        {"id": "decree",
                                         "label": "Приказ / постановление"}]},
        "chat": {"retrieve_k": 6, "style": "concise"},
        "custom_widgets": {"widgets": []},
    }
    r = agent.run_agent(AgentRequest(message="сделай поиск более семантическим",
                                     current_config=base_cfg))
    check(len(r.actions) == 1 and r.actions[0].key == "search"
          and r.actions[0].patch.get("vector_weight") == 0.9,
          "agent: semantic request → search weights action")

    r = agent.run_agent(AgentRequest(message="убери таймлайн с дашборда",
                                     current_config=base_cfg))
    check(len(r.actions) == 1 and r.actions[0].key == "dashboard"
          and "timeline" not in r.actions[0].patch.get("widgets", ["timeline"]),
          "agent: hide request → dashboard widgets without timeline")

    r = agent.run_agent(AgentRequest(message="добавь тип документа «протокол»",
                                     current_config=base_cfg))
    check(len(r.actions) == 1 and r.actions[0].key == "taxonomy"
          and r.actions[0].patch["document_types"][0]["id"] == "protokol",
          "agent: add-type request → taxonomy prepends transliterated id")

    r = agent.run_agent(AgentRequest(message="отвечай в чате подробнее",
                                     current_config=base_cfg))
    check(len(r.actions) == 1 and r.actions[0].key == "chat"
          and r.actions[0].patch.get("style") == "detailed",
          "agent: detailed request → chat style action")

    # Phase 5.5: custom widget from NL (label «приказ…» → document_type=decree)
    r = agent.run_agent(AgentRequest(message="добавь виджет: динамика приказов по годам",
                                     current_config=base_cfg))
    check(len(r.actions) == 1 and r.actions[0].key == "custom_widgets"
          and r.actions[0].patch["widgets"][0]["template"] == "doc_timeline"
          and r.actions[0].patch["widgets"][0]["params"].get("document_type") == "decree"
          and r.actions[0].patch["widgets"][0]["params"].get("granularity") == "year",
          "agent: widget request → doc_timeline spec with taxonomy-matched type")

    # Phase 5.5: operator commands (compound)
    r = agent.run_agent(AgentRequest(message="слей дубликаты и пересчитай статистику",
                                     current_config=base_cfg))
    tools = [c.tool for c in r.commands]
    check(tools == ["resolve_entities", "recompute_stats"],
          "agent: compound operator request → two commands")

    r = agent.run_agent(AgentRequest(message="переклассифицируй документы",
                                     current_config=base_cfg))
    check(len(r.commands) == 1 and r.commands[0].tool == "reprocess_documents"
          and r.commands[0].params.get("limit") == 2,
          "agent: reprocess request → reprocess_documents command (stub limit 2)")

    r = agent.run_agent(AgentRequest(message="найди документы про Абая Кунанбаева",
                                     current_config=base_cfg))
    check(len(r.commands) == 1 and r.commands[0].tool == "open_search"
          and "абая" in r.commands[0].params.get("query", ""),
          "agent: find request → open_search command with query")

    r = agent.run_agent(AgentRequest(message="какая погода в Алматы?",
                                     current_config=base_cfg))
    check(r.actions == [] and r.commands == [] and r.reply,
          "agent: off-scope request → honest no-op reply")

    check(agent.slug("протокол") == "protokol", "translit slug protokol")
    check(agent.slug("Іс қағазы") == "is_qagazy", "translit slug handles Kazakh letters")

    # Small-model accommodation: single-new-item taxonomy patch → additive merge
    from .schemas import AgentAction
    acts = [AgentAction(key="taxonomy",
                        patch={"document_types": [{"id": "protokol", "label": "Протокол"}]})]
    fixed = agent._merge_additive_taxonomy(acts, base_cfg)
    check(len(fixed[0].patch["document_types"]) == 3
          and fixed[0].patch["document_types"][0]["id"] == "protokol"
          and [t["id"] for t in fixed[0].patch["document_types"][1:]]
              == ["official_correspondence", "decree"],
          "additive merge: new-only taxonomy patch gets current types appended")
    acts = [AgentAction(key="taxonomy",
                        patch={"document_types": [{"id": "official_correspondence",
                                                   "label": "Переписка"}]})]
    fixed = agent._merge_additive_taxonomy(acts, base_cfg)
    check(len(fixed[0].patch["document_types"]) == 1,
          "additive merge: overlapping ids = intentional replacement, untouched")

    # Small-model accommodation: tool emitted as a config action → moved to commands
    acts = [AgentAction(key="reprocess_documents", patch={"limit": 5}),
            AgentAction(key="search", patch={"vector_weight": 0.8, "keyword_weight": 0.2})]
    keep, cmds = agent._rescue_misplaced_tools(acts, [], {"reprocess_documents": {}})
    check(len(keep) == 1 and keep[0].key == "search"
          and len(cmds) == 1 and cmds[0].tool == "reprocess_documents"
          and cmds[0].params.get("limit") == 5,
          "misplaced tool action rescued into commands, real actions kept")

    # OCR preprocessing (needs real Pillow; skipped under offline shims)
    try:
        from PIL import Image as _Img
        have_pil = hasattr(_Img, "new")
    except Exception:
        have_pil = False
    if have_pil:
        from PIL import Image, ImageDraw
        from . import preproc

        im = Image.new("RGB", (200, 100), (235, 225, 200))   # yellowed paper
        d = ImageDraw.Draw(im)
        d.rectangle([20, 40, 180, 48], fill=(30, 30, 30))    # "typed" line
        d.rectangle([60, 10, 120, 22], fill=(200, 30, 30))   # red hand edit
        out = preproc.suppress_color_ink(im)
        check(out.getpixel((90, 16))[0] > 240 and out.getpixel((100, 44))[0] < 60,
              "preproc: red ink whitened, black type preserved")

        gray = Image.new("L", (100, 100), 200)
        dg = ImageDraw.Draw(gray)
        dg.rectangle([10, 45, 90, 55], fill=60)
        bw = preproc.binarize_otsu(gray)
        check(set(bw.getdata()) <= {0, 255} and bw.getpixel((50, 50)) == 0
              and bw.getpixel((5, 5)) == 255, "preproc: Otsu binarization separates text")

        page = Image.new("L", (400, 300), 255)
        dp = ImageDraw.Draw(page)
        for y in range(40, 280, 40):
            dp.rectangle([30, y, 370, y + 6], fill=0)
        skewed = page.rotate(-2.0, resample=Image.Resampling.BICUBIC,
                             expand=True, fillcolor=255)
        est = preproc.estimate_skew(skewed)
        check(abs(est - 2.0) <= 0.6, f"preproc: skew estimated ({est:+.2f}° for a -2° page)")
    else:
        print("ok: preproc image checks skipped (Pillow shim)")

    # Kazakh-noise penalty: sparse kaz letters in Russian text = language-pack noise
    from . import ocr as ocr_mod
    ru = ("Товарищи темой доклада сегодняшнего дня являются события года в Казахстане "
          "председатель разрешите заседание посвященное восстанию считать открытым ") * 4
    # realistic pack noise: a handful of kaz glyphs across a long Russian page
    noisy = ru.replace("Казахстане", "Қазақстане", 2)
    kaz = "Қазақстан Республикасының мемлекеттік мұрағаты құжаттарды сақтау және "
    check(ocr_mod._kaz_noise_penalty(ru) == 0.0, "script penalty: clean Russian → 0")
    check(ocr_mod._kaz_noise_penalty(noisy) > 0.0, "script penalty: sparse kaz letters → penalized")
    check(ocr_mod._kaz_noise_penalty(kaz * 3) == 0.0, "script penalty: real Kazakh → 0")

    # ---------------------------------------------------------------- PDF ingest
    # Needs poppler (shipped in the AI service image); skipped on bare hosts.
    from . import pdfdoc
    pdf_bytes = _tiny_pdf([
        ["ArchivAI PDF ingest selftest, page one.",
         "Sender: Domkov. Recipient: comrade Kulpov.",
         "Long enough on its own to count as a real text layer."],
        ["Page two of the fixture, also carrying plenty of text.",
         "Protokol No 17, 19 February 1941, Alma-Ata region.",
         "Both pages stay above PDF_TEXT_MIN_CHARS on purpose."],
    ])
    check(pdfdoc.is_pdf_bytes(pdf_bytes), "PDF magic bytes detected")
    check(pdfdoc.is_pdf_url("http://minio:9000/scans/a.PDF?x=1")
          and not pdfdoc.is_pdf_url("http://minio:9000/scans/a.png"),
          "PDF URLs detected, image URLs left alone")
    b64 = base64.b64encode(pdf_bytes).decode()
    check(pdfdoc.is_pdf_b64(b64), "PDF detected inside base64 payload")

    try:
        pdf_pages = pdfdoc.split(pdf_bytes)
    except Exception as e:                       # poppler missing → not a failure
        pdf_pages = None
        print(f"ok: PDF split checks skipped (poppler unavailable: {e})")

    if pdf_pages is not None:
        check(len(pdf_pages) == 2, "PDF split into one entry per page")
        check(all(p.image_b64 for p in pdf_pages), "every page rendered to an image")
        check(base64.b64decode(pdf_pages[0].image_b64)[:3] == b"\xff\xd8\xff",
              "rendered page is a JPEG")
        check(all(p.has_text_layer for p in pdf_pages)
              and "Domkov" in (pdf_pages[0].text or ""),
              "digital PDF hands over its text layer")
        check(all((p.layout_text or "").strip() for p in pdf_pages)
              and "Domkov" in (pdf_pages[0].layout_text or ""),
              "layout-preserving variant extracted alongside the reading order text")
        lay0 = pdf_pages[0].layout_text or ""
        check(lay0 != pdf_pages[0].text and "   " in lay0,
              "layout variant keeps column spacing (differs from reading order)")
        check("Arch. N 17" in lay0 and "Arch. N 17" in (pdf_pages[0].text or ""),
              "both variants carry the full page content")
        check(len(pdfdoc.split(pdf_bytes, max_pages=1)) == 1, "PDF_MAX_PAGES cap honored")

        expanded = pdfdoc.expand_inputs([ImageInput(image_b64=b64)])
        check(len(expanded) == 2 and all(e.image_b64 and e.text for e in expanded),
              "expand_inputs turns one PDF into per-page inputs")
        images_only = [ImageInput(image_url="http://minio:9000/scans/a.png")]
        check(pdfdoc.expand_inputs(images_only) is images_only,
              "non-PDF page lists pass through untouched")
        check(len(pdfdoc.expand_inputs([ImageInput(image_url="http://127.0.0.1:1/x.pdf")])) == 1,
              "unreachable PDF degrades to the original entry instead of crashing")

        mixed = ocr.run_ocr([ImageInput(image_b64="ZmFrZQ=="), ImageInput(image_b64=b64)])
        check([p.page_no for p in mixed] == [1, 2, 3],
              "page numbering stays 1..N when a PDF expands mid-list")
        check(mixed[0].source == "ocr" and mixed[1].source == "pdf_text"
              and mixed[1].confidence == 1.0,
              "text-layer pages skip OCR, image pages still run it")

        check((mixed[1].layout_text or "").strip(),
              "layout variant survives into the OCR result rows")

        full_pdf, _, ex_pdf, pt_pdf = extract.process_document([ImageInput(image_b64=b64)])
        check(len(pt_pdf) == 2 and ex_pdf.document_type,
              "process_document handles a raw PDF end to end")

    if pdf_pages is not None:
        # Template PDFs draw an unfilled layer under the real text; block analysis
        # shreds those pages into fragments, drawing order keeps lines whole.
        overlapped = _tiny_pdf([["Lecturers in Indonesia face the challenge of "
                                 "presenting interesting lectures for students."]])
        overlapped = overlapped.replace(
            b"(Lecturers in Indonesia face the challenge of "
            b"presenting interesting lectures for students.) Tj",
            b"(Lecturers in Indonesia face the challenge of "
            b"presenting interesting lectures for students.) Tj\nET\n"
            b"BT /F1 12 Tf 120 757 Td\n"
            b"(that can do is integrate gamification elements in the process) Tj")
        default_txt = pdfdoc.text_layer(overlapped)[0]
        raw_txt = pdfdoc.text_layer(overlapped, raw_order=True)[0]
        check(pdfdoc.mean_line_length(raw_txt) > pdfdoc.mean_line_length(default_txt),
              "overlapping text runs: drawing order beats block analysis")
        picked = pdfdoc.split(overlapped)[0]
        check(picked.text_mode == "raw" and "presenting interesting lectures" in (picked.text or ""),
              "split auto-picks the drawing-order text for a shredded page")
        check(pdfdoc.split(pdf_bytes)[0].text_mode == "default",
              "a normal page keeps the reading-order extraction")

    # Chunking: a long document must become several embeddable pieces, because
    # search and RAG score the BEST chunk — one vector per document finds nothing.
    from . import chunking
    from .schemas import OCRPageResult as _Page
    pages_in = [_Page(page_no=1, text="Короткая страница с печатью."),
                _Page(page_no=2, text=("Абзац про восстание 1916 года. " * 150).strip()),
                _Page(page_no=3, text="")]
    chunks = chunking.build_chunks(pages_in, full_text="полный текст")
    check(len(chunks) >= 2, f"long document splits into several chunks (got {len(chunks)})")
    check([c.chunk_no for c in chunks] == list(range(len(chunks))),
          "chunk numbers are contiguous from 0 (the DB key)")
    check(all(len(c.text) <= settings_chunk_max() for c in chunks),
          "no chunk exceeds CHUNK_MAX_CHARS")
    check(all(c.text.strip() for c in chunks), "no empty chunk is embedded")
    check(any(c.page_from == 2 for c in chunks), "chunks carry the page they came from")

    one_page = chunking.build_chunks([_Page(page_no=1, text="Короткое письмо от 1941 года.")])
    check(len(one_page) == 1 and one_page[0].chunk_no == 0,
          "a short document stays a single chunk (unchanged behaviour)")
    no_pages = chunking.build_chunks([], full_text=("Сплошной текст без страниц. " * 200))
    check(len(no_pages) >= 2, "vision one-shot output (no page texts) is chunked from full_text")
    check(chunking.build_chunks([], full_text="") == [], "an empty document produces no chunks")

    # Entity types outside the schema are mapped, not silently dropped
    check(extract.normalize_type("Author") == "person"
          and extract.normalize_type("university") == "organization"
          and extract.normalize_type("year") == "date"
          and extract.normalize_type("city") == "place"
          and extract.normalize_type("percentage") == "quantity",
          "entity type synonyms map onto the schema")
    check(extract.normalize_type("person") == "person"
          and extract.normalize_type("  DATE. ") == "date",
          "schema types survive case/punctuation noise")
    check(extract.normalize_type("kahoot") is None, "unknown types stay unmapped (and get logged)")
    mapped = extract._coerce({"entities": [
        {"name": "Yekti Wirani", "type": "author"},
        {"name": "Nurul Fikri College", "type": "institution"},
        {"name": "2021", "type": "year"},
        {"name": "нечто", "type": "kahoot"},
    ]})
    check([e.type for e in mapped.entities] == ["person", "organization", "date"],
          "_coerce keeps mapped entities and drops only the unmappable one")

    # The schema is a request, not a guarantee — small models answer in whatever
    # shape they like. None of these may crash the pipeline (they used to: a list
    # of bare strings raised AttributeError and failed the whole document).
    bare = extract._coerce({"entities": ["gamification", "Kahoot"],
                            "sender": "Домков", "recipient": None,
                            "summary": ["Строка один.", "Строка два."],
                            "document_type": "decree"})
    check(bare.sender.name == "Домков" and bare.recipient.name is None,
          "sender given as a plain string is accepted")
    check(bare.summary == "Строка один., Строка два.", "summary given as a list is joined")
    check(bare.entities == [], "typeless bare-string entities are dropped, not fatal")
    grouped = extract._coerce({"entities": {
        "person": ["Домков", {"name": "Кулпов", "role": "секретарь"}],
        "organization": "КП(б)К",
        "kahoot": ["мусор"],
    }})
    check(sorted((e.name, e.type) for e in grouped.entities)
          == [("Домков", "person"), ("КП(б)К", "organization"), ("Кулпов", "person")],
          "entities grouped by type (dict of lists) are understood")
    alt = extract._coerce({"entities": [{"entity": "Алма-Ата", "category": "city"}]})
    check([(e.name, e.type) for e in alt.entities] == [("Алма-Ата", "place")],
          "alternative key names (entity/category) are understood")
    check(extract._coerce({}).entities == [] and extract._coerce({}).sender.name is None,
          "an answer with no fields at all yields an empty extraction")

    # The text-mode prompt must NOT ask for full_text: we already have the
    # transcript, and re-transcribing a long document eats the whole answer budget
    # and truncates the JSON (this silently regressed once via an exact-string replace).
    from .prompts import EXTRACT_SYSTEM as _VIS, EXTRACT_TEXT_SYSTEM as _TXT
    check('"full_text"' in _VIS and '"full_text"' not in _TXT,
          "text-mode prompt drops the transcription field the vision prompt asks for")
    check("flat ARRAY OF OBJECTS" in _TXT and "transcribed document text" in _TXT,
          "text-mode prompt keeps the entity-shape rule and its own framing")

    # A model answer that is not usable JSON must not fail the document
    salvaged = extract._extraction_from("this is not json at all", None)
    check(salvaged.entities == [] and salvaged.summary is None,
          "unparseable model output degrades to empty fields (document survives)")
    ok_json = extract._extraction_from('{"document_type": "decreet", "summary": "s"}',
                                       [TaxonomyType(id="decree")])
    check(ok_json.document_type == "decree" and ok_json.summary == "s",
          "valid output still parses and snaps to the taxonomy")

    # Long documents: the extraction prompt is clipped instead of silently
    # overflowing the model context (which returns empty fields).
    long_text = ("строка документа " * 4000)
    clipped = extract.clip_for_model(long_text, 500)
    check(len(clipped) <= 520 and "[…]" in clipped, "long transcript clipped to the limit")
    check(clipped.startswith(long_text[:50]) and clipped.endswith(long_text[-50:]),
          "clip keeps the head and the tail (sender/date … signature)")
    check(extract.clip_for_model("короткий текст", 500) == "короткий текст",
          "short transcript passes through unclipped")
    check(extract.clip_for_model(long_text, 0) == long_text, "limit 0 = no clipping")

    print("\nALL CONTRACT CHECKS PASSED")


if __name__ == "__main__":
    main()
