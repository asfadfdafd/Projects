# Agent D — Demo Analysis

**Source:** `GMT20260304-173042_Recording…1920x1080.mp4` (Zoom recording, ~19 min, 1080p)
**Presenter/team:** "Chordify" (*Code. Create. Conquer.*) — screen-shared product demo with live Q&A
**Analyzed:** from the shared screen frame-by-frame.

> **Sources.** This analysis combines the on-screen walkthrough (frame-by-frame) **and the full timestamped transcript** of the spoken narration + Q&A (`GMT20260304-173042_Recording_Transcript_Timestamped.txt`). Section 6 below captures everything that was **said but not visible on screen** — including promised/roadmap features, the client's requirements, and deployment. The presenter is **Shomron Jacob** (Chordify).

---

## 1. What Agent D is

Agent D is an **AI-powered historical document archive**. It ingests scanned archival documents — handwritten and typed, in **Russian and Kazakh (mixed scripts)**, e.g. 1940s Soviet-Kazakhstan correspondence — and turns each scan into structured, searchable, verifiable records.

For every document it produces: OCR'd full text, a document-type classification, a date, a language tag, sender/recipient with their roles, an AI-written summary, and a set of **categorized, editable entities** (People, Organizations, Dates, Places, Quantities). It then links entities across documents into a **knowledge graph**, indexes everything for **semantic search**, and tracks a **human-verification** workflow. A dashboard reports analytics across the whole collection.

In one line: **upload a pile of old scans → get a clean, searchable, entity-linked, human-verifiable archive.**

---

## 2. The pipeline (as demonstrated / inferred)

1. **Ingest** — upload scanned images/PDFs; multi-page documents are handled ("Page X of Y").
2. **OCR / handwriting recognition** — multilingual (Russian + Kazakh, typed + handwritten, "Mixed").
3. **LLM structured extraction** per document:
   - document type (e.g. `official_correspondence`)
   - date (as written, e.g. "19/II 194г.", "31 мая 1940")
   - language (Russian / Mixed)
   - **sender** and **recipient**, each with an inferred role/title
   - an **AI summary** ("Quairy AI Summary")
   - **entities** by category, each with a role/description
4. **Entity normalization + linking** — entities are collected across documents, given descriptions, and connected by co-occurrence (shared documents) into a graph.
5. **Embedding + indexing** — for semantic search across documents, people, organizations, places.
6. **Human verification** — a reviewer confirms extraction → status flips to **"✓ Human Verified"**.
7. **Analytics aggregation** — dashboard stats, distributions, recent activity, timeline.

---

## 3. Screens & features (complete inventory)

### 3.1 Navigation shell
Dark navy left sidebar: **Dashboard · Documents · Search · Entities · Folders**, plus **Upload** (orange, top-right) and a user menu (shown as "Demo User" / logout). App title "Agent D".

### 3.2 Dashboard
- **Four KPI cards:** Documents Processed (7), People Identified (67), Organizations (15), Total Entities (124).
- **Entity Distribution** donut — Total Entities 196; People 108, Dates 29, Places 24, Quantities 18, Organizations 17.
- **Top Mentioned Entities** — two columns (People / Organizations) with mention counts.
- **Language Distribution** — Russian (5), Mixed (2).
- **Recent Processing Activity** — recent docs with thumbnail, date, and entity count (e.g. "11.png — 28/V с.г. — 13 entities").
- **Document Timeline** — chronological list keyed by document date + type.

*(Note: stat cards and the distribution donut disagree slightly — 67 vs 108 people, 124 vs 196 total — a rough edge in the demo, not a design feature.)*

### 3.3 Documents — "Document Archive"
Table/list of processed documents: thumbnail, name (e.g. `test_doc_5pages_page_1.png`), type tag, date, language, **status (Pending / Verified)**, extracted people/orgs, and row actions. Upload entry point and pagination.

### 3.4 Document Detail (the core screen)
Split view:
- **Left:** the scanned page with **zoom** ("Click to zoom") and multi-page navigation ("Page 1 of 1").
- **Right panel:**
  - Header chips: **type** (`official_correspondence`), **date** ("19/II 194г."), **language** ("Mixed"), **verification status** ("✓ Human Verified").
  - **SENDER** and **RECIPIENT**, each with name + inferred role (e.g. Sender "Домков — Секретарь Д/П Обкома КП(б)К"; Recipient "ТОВ.КУЛПОВУ — Секретарь ЦК КП(б)К").
  - **"Quairy AI Summary"** — an LLM paragraph summarizing the document's content and intent.
  - **Extracted Entities**, grouped and **editable** with per-group counts and a **"+ Add"** control:
    - **People** (blue pills) — e.g. Абай (Ибрагим) Кунанбаев, Амангельды Иманову, Домков, Н. Цивчинский
    - **Organizations** (green) — КП(б)К, ЦК КП(б)К, Южно-Казахстанский Областной Комитет
    - **Dates** (amber) — 19/II 194г.
    - **Places** (purple) — Казахстан, Южно-Казахстанский
    - **Quantities**
  - **Full Extracted Text** section (OCR output).
  - **"Mark as Verified"** action (drives the status chip).

### 3.5 Search
- Global search bar: "Search documents, people, organizations, places…"
- Returns **"Found N documents matching '<query>'"** with result cards (thumbnail, filename, year, snippet).
- Filter chips by content type: **Metadata / HTML / Text** — i.e. keyword + semantic search across different fields.

### 3.6 Entities — "Entity Relationships"
- **Knowledge-graph canvas** — nodes for **Person (blue)** and **Organization (green)**, edges = "connected through shared documents"; labeled nodes (Абай Кунанбаев, ЦК КП(б)К, …), zoom/reset controls, legend.
- Tabs: **All (76) · People (63) · Organizations (13)**, a **Filter entities** box, and **Export CSV**.
- **Entity table:** Entity Name · Type · Role / Description · Documents (count) · Actions (**View**). Rows **expand** to reveal the underlying documents (thumbnail, filename, year, snippet).
- Entities carry rich, world-knowledge descriptions (e.g. "Байрон — английский поэт", "Белинский — русский литературный критик"), showing the LLM enriches beyond the raw text.

### 3.7 Cross-cutting
- **Human-in-the-loop verification** (Pending → Human Verified).
- **Editable entities** (add/remove per document).
- **CSV export** of entities.
- **Auth** (user session, demo account).
- **Folders** for organizing documents.

---

## 4. Data model (reverse-engineered)

- **document**: id, filename, source image ref, page images, document_type, date_text, language, sender {name, role}, recipient {name, role}, ai_summary, full_text, status (pending/verified), verified_by, timestamps.
- **entity**: id, canonical_name, type (person / organization / date / place / quantity), role_description, document_count.
- **entity_mention**: entity_id ↔ document_id (which docs an entity appears in) — powers counts, graph edges, and expandable rows.
- **relationship (edge)**: entity_a ↔ entity_b via shared document (co-occurrence).
- **embedding**: vector per document/chunk for semantic search.
- **user / session**.

Entity types confirmed on screen: **People, Organizations, Dates, Places, Quantities**. Document type seen: **official_correspondence** (the classifier clearly supports more). Languages: **Russian, Mixed**.

---

## 5. Strengths & gaps (useful for building a competitor)

**Strengths:** strong OCR on hard handwritten/multilingual scans; clean structured extraction (sender/recipient/summary/entities); human verification loop; knowledge graph + semantic search; polished dashboard; CSV export.

**Gaps / opportunities to beat:**
- **Entity de-duplication** is imperfect — "Каз. Филиал Академии Наук СССР" vs "КазФилиал АН СССР", "Абай" vs "Абай Кунанбаев" vs "Абай (Ибрагим) Кунанбаев" appear as separate entities. A better entity-resolution step is an easy win.
- **Dashboard counts are inconsistent** — a single source of truth for stats avoids this.
- **No visible batch/bulk pipeline UI**, confidence scores, or provenance (which model produced what). Adding confidence + audit trail is a differentiator.
- Extraction is **prompt/LLM driven** — reproducible with any capable vision-LLM, which is exactly where an **n8n-orchestrated** pipeline shines (swap models, add steps, retry, human review) without rebuilding a monolith.

---

## 6. From the narration & Q&A (transcript) — what was *said*, incl. not-yet-built features

This is the material that isn't obvious from the screens. Several items are **promised/roadmap**, not demonstrated — important, because a true competitor must match the *pitch*, not just the current UI.

### 6.1 Confirmed / clarified capabilities
- **Entity types are exactly:** people, organizations, dates, places, quantities (verbatim). Extraction runs *per page*, and an **"all pages"** aggregated view combines entities + full text across the whole document (6-page example).
- **Handwriting is a headline feature.** Pages mix printed text, handwritten notes, handwritten signatures, and stamps; the AI extracts from all of it together ("best match"). Example: a handwritten "151" is picked up.
- **Human feedback loop is editable inline:** click any extracted value → fix spelling → save; **add** entities the AI missed (e.g. a missing organization) by typing them. Corrections are persisted and the AI "knows" the doc was verified.
- **Verification** = human-in-the-loop by design; "Mark as Verified" → green check on the list; rationale is that AI extraction needs human confirmation.
- **Document classification is configurable** — Chordify will agree the document-type taxonomy with the client (correspondence, report, etc.).
- **Download/export**: per-page extraction, all-pages, and entity lists.
- **Three navigation paths to a document:** from Search, from an Entity, or from the Document list — all cross-linked.
- **Knowledge graph** explicitly connects people ↔ organizations (↔ places) across documents to surface **hidden relations** a researcher "cannot see" otherwise.

### 6.2 Promised / roadmap features (spoken, not shown)
- **The agentic layer — the reason it's called "Agent D".** There is an underlying **AI agent** that lets a user **customize behavior in natural language, no code**: the user tells the agent how they want search (or the dashboard, or classification) to work, and the agent reconfigures it underneath and returns the result. A dedicated **input screen** for this is planned ("haven't extended it yet, but I can"). *This is the core differentiator.*
- **Semantic search** (client explicitly asked): free-flow natural-language questions, contextually relevant results, surfaces semantically related docs / hidden relations. (Current demo does keyword/contextual highlight; semantic is the promised upgrade.)
- **Per-user profiles + SSO/single sign-on:** each user has their own login, preferences, and personalized search behavior; **search history/chronology tracked per user**; AI searches per profile.
- **Compliance & usage analytics:** track searches, most-frequently-used documents, who is online, **user IP addresses**; dashboard can go deeper into usage. Explicitly framed as compliance.
- **Signature extraction** (optional model): draw a **bounding box** around a signature and export it as a cropped **image**; enables signature verification.
- **Stamp extraction** (optional): same bounding-box → image approach for stamps.
- **Learning / recommendations over time:** system learns usage and starts recommending ("most popular", "what's doing better").
- **AI archival-expert assistant** (client request): an assistant that provides archival/domain expertise about documents and **inventories**.
- **External/IoT data on the dashboard** (client request): e.g. real-time **temperature & humidity** monitoring of archival storage, surfaced via API.

### 6.3 Integration, deployment & footprint (spoken)
- **Minimal footprint / "connection layer":** the system only needs the client's **file storage + database**. It pulls files from storage, processes them, and pushes structured data back to the client DB — potentially removing the need for the legacy app.
- **Webhooks/APIs (bidirectional):** a webhook section exists but **isn't enabled yet**; it will connect to legacy systems to pull or push data. Client's legacy stack noted as old Java + very old PostgreSQL (v6/7).
- **Bulk ingestion:** rather than manual one-by-one upload, connect to file storage and **pull 50–100+ documents at once**; manual upload remains available.
- **Deployment options:** **on-premise**, **private cloud** (region-specific — e.g. Middle East / in-country for **data residency**), or a server. Client asked specifically about on-prem.

### 6.4 Stakeholders & context
- **Vendor:** Chordify — presenter **Shomron Jacob**.
- **Client:** an **archival institution** (talks of archives, inventories, storage temperature/humidity, researchers as end-users). The sample documents are 1940s South-Kazakhstan / Semipalatinsk records (Abai Kunanbayev 95th-anniversary correspondence), consistent with a **Kazakhstan state/regional archive**.
- **Primary user = researcher:** searches an event / place / person and expects back all related documents *plus* hidden semantic relations.
- **Stated next steps:** discovery workshop → capture needs, customizations, systems to integrate → propose plan + infrastructure → go live.
