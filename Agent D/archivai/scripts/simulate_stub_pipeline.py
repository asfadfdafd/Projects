#!/usr/bin/env python3
"""Mechanical stub-mode simulation of the ArchivAI n8n pipeline (no Docker needed).

Executes the REAL artifacts without a live stack:
  * runs every Code node's actual JS and every n8n expression under Node.js,
    inside a faithful mini-runtime ($json, $('Node').first()/.item, $input, $env);
  * feeds them the AI service's exact stub outputs (ported from services/ai);
  * checks every Postgres node call against the function signatures parsed
    from db/init/*.sql (name, placeholder count, argument count);
  * cross-checks the ingest payload keys against what ingest_extraction() reads;
  * validates workflow graph integrity (connections, reachability, credentials).

Usage:  python3 scripts/simulate_stub_pipeline.py     (requires node >= 14)
Exit code 0 = all checks pass.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF_DIR = os.path.join(ROOT, "n8n", "workflows")
SQL_FILES = sorted(
    os.path.join(ROOT, "db", "init", f)
    for f in os.listdir(os.path.join(ROOT, "db", "init"))
    if f.endswith(".sql") and not f.startswith("01_")
)

PASS, FAIL = [], []


def ok(msg):
    PASS.append(msg)
    print(f"  [ok]   {msg}")


def fail(msg):
    FAIL.append(msg)
    print(f"  [FAIL] {msg}")


def check(cond, msg):
    ok(msg) if cond else fail(msg)


def step(title):
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# 1. Load artifacts
# ---------------------------------------------------------------------------
def load_workflows():
    wfs = {}
    for fn in sorted(os.listdir(WF_DIR)):
        if fn.endswith(".json"):
            with open(os.path.join(WF_DIR, fn), encoding="utf-8") as f:
                wfs[fn] = json.load(f)
    return wfs


def parse_sql_functions():
    """name -> (required_args, total_args) parsed from CREATE OR REPLACE FUNCTION."""
    sig = {}
    src = ""
    for p in SQL_FILES:
        with open(p, encoding="utf-8") as f:
            src += f.read() + "\n"
    for m in re.finditer(r"CREATE OR REPLACE FUNCTION\s+(\w+)\s*\(([^)]*)\)", src, re.I):
        name, args = m.group(1), m.group(2).strip()
        if not args:
            sig[name] = (0, 0)
            continue
        parts = [a.strip() for a in args.split(",")]
        total = len(parts)
        required = len([a for a in parts if " DEFAULT " not in a.upper()])
        sig[name] = (required, total)
    reads = set(re.findall(r"(?<!\w)payload->>'(\w+)'", src))
    nested = re.findall(r"payload#>>'\{(\w+),(\w+)\}'", src)
    ent_reads = set(re.findall(r"\bent->>'(\w+)'", src))
    page_reads = set(re.findall(r"\bpg_item->>'(\w+)'", src))
    return sig, reads, nested, ent_reads, page_reads


def split_call_args(argstr):
    """Split SQL call arguments on top-level commas."""
    out, depth, cur = [], 0, ""
    for ch in argstr:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


# ---------------------------------------------------------------------------
# 2. Graph integrity
# ---------------------------------------------------------------------------
def check_graph(name, wf):
    nodes = {n["name"]: n for n in wf["nodes"]}
    conns = wf.get("connections", {})
    ok_graph = True
    for src, spec in conns.items():
        if src not in nodes:
            fail(f"{name}: connection from unknown node '{src}'")
            ok_graph = False
        for branch in spec.get("main", []):
            for tgt in branch or []:
                if tgt["node"] not in nodes:
                    fail(f"{name}: connection to unknown node '{tgt['node']}'")
                    ok_graph = False
    webhooks = [n for n in wf["nodes"] if n["type"].endswith(".webhook")]
    schedules = [n for n in wf["nodes"] if n["type"].endswith(".scheduleTrigger")]
    responders = [n for n in wf["nodes"] if n["type"].endswith(".respondToWebhook")]
    check(len(webhooks) <= 1 and len(webhooks) + len(schedules) >= 1,
          f"{name}: has trigger(s) (≤1 webhook + optional schedule)")
    if webhooks:
        check(len(responders) >= 1, f"{name}: has a Respond node")
    # reachability from ALL triggers (follow all output branches, incl. errors)
    seen, todo = set(), [t["name"] for t in webhooks + schedules]
    while todo:
        cur = todo.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for branch in conns.get(cur, {}).get("main", []):
            for tgt in branch or []:
                todo.append(tgt["node"])
    unreachable = set(nodes) - seen
    check(not unreachable, f"{name}: all nodes reachable" +
          ("" if not unreachable else f" (unreachable: {unreachable})"))
    for n in wf["nodes"]:
        if n["type"].endswith(".postgres"):
            cred = n.get("credentials", {}).get("postgres", {})
            if cred.get("id") != "archivai-pg" or cred.get("name") != "ArchivAI Postgres":
                fail(f"{name}/{n['name']}: postgres credential mismatch")
        if n["type"].endswith(".httpRequest"):
            url = n["parameters"].get("url", "")
            # allowed: env-driven targets (AI service, client webhook) or self-webhook fan-outs
            if ("$env.AI_SERVICE_URL" not in url and "$env.CLIENT_WEBHOOK_URL" not in url
                    and "127.0.0.1:5678/webhook" not in url):
                fail(f"{name}/{n['name']}: HTTP url not env-driven or self-webhook: {url!r}")
        if n["type"].endswith(".code"):
            if re.search(r"\$\((?:'|\")[^)]*\)\s*\.item\b", n["parameters"]["jsCode"]):
                fail(f"{name}/{n['name']}: Code node uses $('X').item (use .first())")
    if ok_graph:
        ok(f"{name}: graph integrity")


# ---------------------------------------------------------------------------
# 3. Postgres node contract checks (static side)
# ---------------------------------------------------------------------------
def check_pg_contracts(name, wf, sig):
    for n in wf["nodes"]:
        if not n["type"].endswith(".postgres"):
            continue
        q = n["parameters"]["query"]
        label = f"{name}/{n['name']}"
        placeholders = {int(x) for x in re.findall(r"\$(\d+)", q)}
        maxp = max(placeholders) if placeholders else 0
        check(placeholders == set(range(1, maxp + 1)), f"{label}: placeholders contiguous $1..${maxp}")
        m = re.search(r"(?:SELECT\s+\*\s+FROM|SELECT)\s+(\w+)\s*\(([^;]*)\)", q, re.I)
        if not m:
            fail(f"{label}: query is not a single function call: {q!r}")
            continue
        fn, argstr = m.group(1), m.group(2)
        if fn not in sig:
            fail(f"{label}: function {fn}() not found in db/init SQL")
            continue
        req, tot = sig[fn]
        nargs = len(split_call_args(argstr))
        check(req <= nargs <= tot,
              f"{label}: {fn}() called with {nargs} args (signature {req}..{tot})")
        qr = n["parameters"].get("options", {}).get("queryReplacement")
        if maxp == 0:
            check(qr is None, f"{label}: no stray queryReplacement")
            continue
        if not (isinstance(qr, str) and re.match(r"^=\{\{\s*\[[\s\S]*\]\s*\}\}$", qr.strip())):
            fail(f"{label}: queryReplacement must be a single array expression "
                 f"'={{{{ [a, b] }}}}' (comma-splitting breaks on vectors/JSON): {qr!r}")


# ---------------------------------------------------------------------------
# 4. Node.js harness: execute Code nodes + expressions with stub AI data
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const crypto = require('crypto');
const fs = require('fs');
const [wfPath] = process.argv.slice(2);
const WFS = JSON.parse(fs.readFileSync(wfPath, 'utf8'));
const ENV = { AI_SERVICE_URL: 'http://ai-service:8000' };
const R = { checks: [], data: {} };
const okc = (c, m) => R.checks.push({ ok: !!c, msg: m });

// ---- faithful ports of services/ai stub logic ----
function stubOcrPages(n) {
  const out = [];
  for (let i = 1; i <= n; i++) out.push({ page_no: i, text: `[stub OCR text for page ${i}]`, confidence: 0.5 });
  return out;
}
const STUB_EXTRACTION = {
  document_type: 'official_correspondence',
  date_text: '19/II 194г.',
  language: 'Mixed',
  sender: { name: 'Домков', role: 'Секретарь Д/П Обкома КП(б)К' },
  recipient: { name: 'тов. Кулпову', role: 'Секретарь ЦК КП(б)К' },
  summary: '[stub] Официальное письмо. Тестовое резюме документа.',
  entities: [
    { name: 'Домков', type: 'person', role: 'секретарь обкома', surface_form: 'Домков' },
    { name: 'КП(б)К', type: 'organization', role: 'Коммунистическая партия', surface_form: 'КП(б)К' },
    { name: 'Казахстан', type: 'place', role: null, surface_form: 'Казахстан' },
    { name: '19/II 194г.', type: 'date', role: null, surface_form: '19/II 194г.' }
  ]
};
const DEFAULT_TAXONOMY = [
  { id: 'official_correspondence', label: 'Официальная переписка' },
  { id: 'report', label: 'Отчёт' }, { id: 'decree', label: 'Приказ / постановление' },
  { id: 'article', label: 'Статья' }, { id: 'list', label: 'Список' }
];
function stubProcess(pages, taxonomy) {
  const pts = stubOcrPages(pages.length);
  const full = pts.map(p => p.text).join('\n\n');
  const extraction = Object.assign({}, STUB_EXTRACTION,
    taxonomy && taxonomy.length ? { document_type: taxonomy[0].id } : {});
  return { full_text: full, confidence: 0.5, extraction,
           ocr_backend: 'qwen_vl', extract_backend: 'qwen_vl', page_texts: pts };
}
// ---- port of services/ai/app/agent.py stub rules (keep in sync) ----
const TRANSLIT = { 'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
  'и':'i','й':'j','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
  'у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e',
  'ю':'yu','я':'ya','ә':'a','ғ':'g','қ':'q','ң':'n','ө':'o','ұ':'u','ү':'u','һ':'h','і':'i' };
function slug(word) {
  let out = [...word.toLowerCase()].map(ch => TRANSLIT[ch] !== undefined ? TRANSLIT[ch] : ch).join('');
  return out.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40);
}
function stubAgent(req) {
  const msg = req.message.toLowerCase();
  const cfg = req.current_config || {};
  const actions = [];
  if (msg.includes('семантич') || msg.includes('вектор')) {
    actions.push({ key: 'search', patch: { vector_weight: 0.9, keyword_weight: 0.1 }, reason: 'more semantic' });
  } else if (msg.includes('ключев') || msg.includes('точн')) {
    actions.push({ key: 'search', patch: { vector_weight: 0.4, keyword_weight: 0.6 }, reason: 'more keyword' });
  }
  if (['убери','убрать','скрой','скрыть','спрячь','hide','remove'].some(w => msg.includes(w))) {
    const current = ((cfg.dashboard || {}).widgets || []).slice();
    const syn = { timeline: ['таймлайн','timeline','хронолог'], recent_activity: ['активност','recent'],
      language_distribution: ['язык','language'], entity_distribution: ['распределение','донат','donut'],
      kpi_cards: ['kpi','карточк'], top_entities: ['топ сущ','top entities'] };
    for (const [wid, syns] of Object.entries(syn)) {
      if (syns.some(s => msg.includes(s)) && current.includes(wid)) {
        actions.push({ key: 'dashboard', patch: { widgets: current.filter(w => w !== wid) }, reason: 'hide ' + wid });
        break;
      }
    }
  }
  const m = msg.match(/топ[\s\-–]*(\d+)/);
  if (m) actions.push({ key: 'dashboard', patch: { top_n: Math.max(3, Math.min(10, parseInt(m[1], 10))) }, reason: 'top size' });
  if (msg.includes('тип') && (msg.includes('добав') || msg.includes('add'))) {
    const qm = req.message.match(/[«"„']([^»"“']{2,40})[»"“']/);
    const word = qm ? qm[1].trim() : null;
    if (word) {
      const tid = slug(word);
      const types = ((cfg.taxonomy || {}).document_types || []).slice();
      if (tid && !types.some(t => t.id === tid)) {
        actions.push({ key: 'taxonomy',
          patch: { document_types: [{ id: tid, label: word.charAt(0).toUpperCase() + word.slice(1) }].concat(types) },
          reason: 'add type ' + tid });
      }
    }
  }
  if (msg.includes('подробн')) actions.push({ key: 'chat', patch: { style: 'detailed' }, reason: 'detailed answers' });
  else if (msg.includes('кратк') || msg.includes('коротк')) actions.push({ key: 'chat', patch: { style: 'concise' }, reason: 'concise answers' });
  // Phase 5.5: custom widget + operator commands (port of app/agent.py rules)
  const commands = [];
  if (msg.includes('виджет') && msg.includes('добав')) {
    const types = ((cfg.taxonomy || {}).document_types || []);
    let dt = null;
    for (const tt of types) {
      const word = ((tt.label || tt.id || '').toLowerCase().split(/\s+/)[0] || '').trim();
      if (word.length >= 4 && msg.includes(word)) { dt = tt.id; break; }
    }
    let template, params, title;
    if (msg.includes('год') || msg.includes('динамик') || msg.includes('врем')) {
      template = 'doc_timeline'; params = { granularity: 'year' }; title = 'Динамика документов';
    } else {
      template = 'doc_count'; params = { group_by: 'document_type' }; title = 'Документы по типам';
    }
    if (dt) params.document_type = dt;
    const wid = 'w_' + template + '_' + (dt || 'all');
    const widgets = (((cfg.custom_widgets || {}).widgets) || []).slice();
    if (!widgets.some(x => x.id === wid)) {
      widgets.push({ id: wid, title, template, params });
      actions.push({ key: 'custom_widgets', patch: { widgets }, reason: 'add custom widget' });
    }
  }
  if (msg.includes('дубл') && (msg.includes('сл') || msg.includes('объедин') || msg.includes('убер'))) {
    commands.push({ tool: 'resolve_entities', params: {}, reason: 'merge duplicate entities' });
  }
  if (msg.includes('пересчит') && msg.includes('статист')) {
    commands.push({ tool: 'recompute_stats', params: {}, reason: 'recompute dashboard stats' });
  }
  if (msg.includes('переклассифиц') || msg.includes('переобработ')) {
    commands.push({ tool: 'reprocess_documents', params: { limit: 2 }, reason: 're-run documents' });
  }
  const ms = msg.match(/(?:найди|покажи)\s+(?:все\s+)?(?:документы\s+)?(?:про|о|об)\s+(.{2,80})/);
  if (ms) commands.push({ tool: 'open_search', params: { query: ms[1].trim().replace(/[?.!]+$/, '') }, reason: 'open prepared search' });
  return { reply: (actions.length || commands.length) ? '[stub] Готово.' : '[stub] Это я сделать не могу.', actions, commands };
}
function stubEmbed(texts) {
  const dim = 1024;
  return texts.map(t => {
    const h = crypto.createHash('sha256').update(Buffer.from(String(t), 'utf8')).digest();
    const seed = h.readBigUInt64BE(0);
    const vec = [];
    for (let i = 0; i < dim; i++) vec.push(Math.sin(Number((seed * BigInt(i + 1)) % 1000n) / 100.0));
    const norm = Math.sqrt(vec.reduce((s, v) => s + v * v, 0)) || 1.0;
    return vec.map(v => v / norm);
  });
}
function stubAnswer(req) {
  if (!req.contexts || !req.contexts.length) {
    return { answer: 'В архиве не найдено релевантных документов по этому запросу.', citations: [], grounded: false };
  }
  const first = req.contexts[0];
  const answer = `[stub] По имеющимся документам: ${String(first.text).slice(0, 80)} [${first.ref}].`;
  const refs = [...new Set([...answer.matchAll(/\[(\d+)\]/g)].map(m => parseInt(m[1], 10)))].sort();
  const byRef = Object.fromEntries(req.contexts.map(c => [c.ref, c]));
  const citations = refs.filter(r => byRef[r]).map(r => ({ ref: r, document_id: byRef[r].document_id, filename: byRef[r].filename }));
  return { answer, citations, grounded: true };
}

// ---- mini n8n runtime ----
function makeRuntime(outputs, inputItems) {
  const cur = inputItems && inputItems.length ? inputItems[0] : { json: {} };
  const $ = (name) => {
    const items = outputs[name];
    if (!items) throw new Error(`no output recorded for node '${name}'`);
    return { first: () => items[0], item: items[0], all: () => items };
  };
  const $input = { all: () => inputItems, first: () => inputItems[0] };
  return { $, $input, $json: cur.json, $env: ENV };
}
function runCode(node, outputs, inputItems) {
  const rt = makeRuntime(outputs, inputItems);
  const fn = new Function('$', '$input', '$json', '$env', node.parameters.jsCode);
  const res = fn(rt.$, rt.$input, rt.$json, rt.$env);
  if (!Array.isArray(res)) throw new Error(`${node.name}: Code node must return an items array`);
  return res.map(i => (i && i.json !== undefined ? i : { json: i }));
}
function evalExpr(str, outputs, inputItems) {
  if (typeof str !== 'string') return str;
  const m = str.trim().match(/^=\{\{([\s\S]*)\}\}$/);
  if (!m) return str.startsWith('=') ? str.slice(1) : str;
  const rt = makeRuntime(outputs, inputItems);
  const fn = new Function('$', '$input', '$json', '$env', `return ( ${m[1]} );`);
  return fn(rt.$, rt.$input, rt.$json, rt.$env);
}
const byName = (wf) => Object.fromEntries(wf.nodes.map(n => [n.name, n]));
function pgParams(node, outputs, items, label) {
  const qr = (node.parameters.options || {}).queryReplacement;
  if (qr === undefined) return [];
  const v = evalExpr(qr, outputs, items);
  okc(Array.isArray(v), `${label}: queryReplacement resolves to an array`);
  const maxp = Math.max(0, ...[...node.parameters.query.matchAll(/\$(\d+)/g)].map(m => parseInt(m[1], 10)));
  okc(Array.isArray(v) && v.length === maxp, `${label}: array length ${Array.isArray(v) ? v.length : '?'} == max placeholder $${maxp}`);
  return v;
}

// =========================== W1: ingest =====================================
(function () {
  const wf = WFS['1_ingest_and_process.json'];
  const N = byName(wf);
  const outputs = {};
  const webhookItem = { json: { body: {
    filename: 'smoke, комма-тест №1.png',
    original_url: 'http://minio:9000/scans/smoke.png',
    pages: [{ image_url: 'http://minio:9000/scans/smoke.png' }, { image_url: 'http://minio:9000/scans/smoke2.png' }]
  } } };
  outputs['Webhook: Ingest'] = [webhookItem];

  let p = pgParams(N['PG: Create Document'], outputs, outputs['Webhook: Ingest'], 'W1/create');
  okc(p[0] === webhookItem.json.body.filename, 'W1/create: $1 = filename (commas preserved)');
  okc(p[2] === 2, 'W1/create: $3 = page count 2');
  okc(p[3] === null, 'W1/create: $4 = doc_id null (fresh ingest, not a reprocess)');
  outputs['PG: Create Document'] = [{ json: { doc_id: '11111111-1111-4111-8111-111111111111',
                                              taxonomy: DEFAULT_TAXONOMY } }];

  // async contract: respond BEFORE the heavy work
  const acc = evalExpr(N['Respond: Accepted'].parameters.responseBody, outputs, outputs['PG: Create Document']);
  okc(acc.doc_id === '11111111-1111-4111-8111-111111111111' && acc.status === 'processing',
      'W1/respond-accepted: immediate {doc_id, status:processing}');
  okc((N['Respond: Accepted'].parameters.options || {}).responseCode === 202,
      'W1/respond-accepted: HTTP 202');

  const reqBody = evalExpr(N['AI: OCR + Extract'].parameters.jsonBody, outputs, outputs['PG: Create Document']);
  okc(Array.isArray(reqBody.pages) && reqBody.pages.length === 2 && !!reqBody.pages[0].image_url,
      'W1/process: request body = {pages:[{image_url}...]}');
  okc(Array.isArray(reqBody.taxonomy) && reqBody.taxonomy[0].id === 'official_correspondence',
      'W1/process: agent-managed taxonomy forwarded to /process');
  outputs['AI: OCR + Extract'] = [{ json: stubProcess(reqBody.pages, reqBody.taxonomy) }];

  outputs['Build Payload'] = runCode(N['Build Payload'], outputs, outputs['AI: OCR + Extract']);
  const bp = outputs['Build Payload'][0].json;
  R.data.payload = bp.payload;
  okc(bp.doc_id === '11111111-1111-4111-8111-111111111111', 'W1/payload: doc_id carried through');
  okc(bp.payload.entities.length === 4, 'W1/payload: 4 stub entities');
  okc(bp.payload.pages.length === 2 && bp.payload.pages[0].page_no === 1
      && bp.payload.pages[0].image_url === 'http://minio:9000/scans/smoke.png'
      && bp.payload.pages[0].ocr_text.includes('[stub OCR'),
      'W1/payload: pages[] merged (page_no + image_url + ocr_text)');
  okc(bp.payload.full_text.includes('page 1') && bp.payload.full_text.includes('page 2'),
      'W1/payload: full_text aggregates all pages');

  p = pgParams(N['PG: Ingest Extraction'], outputs, outputs['Build Payload'], 'W1/ingest_extraction');
  okc(typeof p[1] === 'string' && JSON.parse(p[1]).document_type === 'official_correspondence',
      'W1/ingest_extraction: $2 is valid JSON payload string');

  const embBody = evalExpr(N['AI: Embed'].parameters.jsonBody, outputs, outputs['Build Payload']);
  okc(Array.isArray(embBody.texts) && embBody.texts[0] === bp.full_text, 'W1/embed: request = {texts:[full_text]}');
  outputs['AI: Embed'] = [{ json: { model: 'bge-m3', dim: 1024, vectors: stubEmbed(embBody.texts) } }];

  outputs['Format Vector'] = runCode(N['Format Vector'], outputs, outputs['AI: Embed']);
  const fv = outputs['Format Vector'][0].json;
  okc(/^\[-?\d+(\.\d+)?(e[+-]?\d+)?(,-?\d+(\.\d+)?(e[+-]?\d+)?){1023}\]$/i.test(fv.vec),
      'W1/vector: pgvector literal, 1024 dims');
  p = pgParams(N['PG: Store Embedding'], outputs, outputs['Format Vector'], 'W1/upsert_embedding');
  okc(p[0] === bp.doc_id && p[1] === bp.full_text && p[2] === fv.vec, 'W1/upsert_embedding: params ordered (doc,text,vec)');

  pgParams(N['PG: Recompute Stats'], outputs, outputs['Format Vector'], 'W1/stats');

  // ---- error branch (background: mark_failed only, response already sent) ----
  const errItem = { json: { error: { message: 'no pages provided' } } };
  p = pgParams(N['PG: Mark Failed'], outputs, [errItem], 'W1/mark_failed');
  okc(p[0] === bp.doc_id && p[1] === 'no pages provided', 'W1/mark_failed: (doc_id, error message)');
  okc(N['AI: OCR + Extract'].onError === 'continueErrorOutput' && N['AI: Embed'].onError === 'continueErrorOutput',
      'W1: both AI nodes route errors to the error output');
})();

// =========================== W2: search =====================================
(function () {
  const wf = WFS['2_search.json'];
  const N = byName(wf);
  const outputs = {};
  outputs['Webhook: Search'] = [{ json: { body: { query: 'Домков, письмо' } } }];
  const emb = evalExpr(N['AI: Embed Query'].parameters.jsonBody, outputs, outputs['Webhook: Search']);
  okc(emb.texts[0].includes(','), 'W2/embed: comma-containing query intact');
  outputs['AI: Embed Query'] = [{ json: { model: 'bge-m3', dim: 1024, vectors: stubEmbed(emb.texts) } }];
  outputs['Format Query'] = runCode(N['Format Query'], outputs, outputs['AI: Embed Query']);
  const p = pgParams(N['PG: Search'], outputs, outputs['Format Query'], 'W2/search');
  okc(typeof p[0] === 'string' && p[0].startsWith('[') && p[1] === 'Домков, письмо'
      && p[2] === null && p[3] === null,
      'W2/search: (vector, query, user_id, ip) — config-aware + history-logging search');
  // rows found
  outputs['PG: Search'] = [{ json: { document_id: 'd1', filename: '10.png', document_type: 'official_correspondence',
                                     date_text: '19/II 194г.', score: 0.83, snippet: '[stub] ...' } }];
  outputs['Format Results'] = runCode(N['Format Results'], outputs, outputs['PG: Search']);
  let resp = evalExpr(N['Respond'].parameters.responseBody, outputs, outputs['Format Results']);
  okc(resp.count === 1 && resp.results[0].document_id === 'd1' && typeof resp.query === 'string',
      'W2/respond: {query, count, results[]}');
  // zero rows (alwaysOutputData yields one empty item)
  okc(N['PG: Search'].alwaysOutputData === true, 'W2: PG Search has alwaysOutputData (no zero-item hang)');
  outputs['PG: Search'] = [{ json: {} }];
  outputs['Format Results'] = runCode(N['Format Results'], outputs, outputs['PG: Search']);
  resp = evalExpr(N['Respond'].parameters.responseBody, outputs, outputs['Format Results']);
  okc(resp.count === 0 && Array.isArray(resp.results) && resp.results.length === 0,
      'W2/respond: empty archive -> {count:0, results:[]} (no hang)');
})();

// =========================== W3: chat ========================================
(function () {
  const wf = WFS['3_chat.json'];
  const N = byName(wf);
  const outputs = {};
  outputs['Webhook: Chat'] = [{ json: { body: { question: 'Кто, кому и о чём писал?', session_id: null, user_id: null } } }];
  const emb = evalExpr(N['AI: Embed Question'].parameters.jsonBody, outputs, outputs['Webhook: Chat']);
  outputs['AI: Embed Question'] = [{ json: { model: 'bge-m3', dim: 1024, vectors: stubEmbed(emb.texts) } }];
  outputs['Format Vector'] = runCode(N['Format Vector'], outputs, outputs['AI: Embed Question']);
  pgParams(N['PG: Retrieve Context'], outputs, outputs['Format Vector'], 'W3/rag_retrieve');
  okc(N['PG: Retrieve Context'].alwaysOutputData === true, 'W3: retrieve has alwaysOutputData');

  outputs['PG: Retrieve Context'] = [
    { json: { chunk_id: 'c1', document_id: 'd1', filename: '10.png', content: 'Домков писал Кулпову о юбилее Абая.', distance: 0.12, style: 'concise' } },
    { json: { chunk_id: 'c2', document_id: 'd2', filename: '11.png', content: 'Второй фрагмент.', distance: 0.2, style: 'concise' } }
  ];
  outputs['Build Contexts'] = runCode(N['Build Contexts'], outputs, outputs['PG: Retrieve Context']);
  const ctx = outputs['Build Contexts'][0].json;
  okc(ctx.contexts.length === 2 && ctx.contexts[0].ref === 1 && ctx.contexts[1].ref === 2
      && ctx.contexts[0].document_id === 'd1' && typeof ctx.contexts[0].text === 'string',
      'W3/contexts: [{ref,document_id,filename,text}] numbered 1..k');
  okc(ctx.style === 'concise', 'W3/contexts: chat style rides along from config');

  const ansBody = evalExpr(N['AI: Answer'].parameters.jsonBody, outputs, outputs['Build Contexts']);
  okc(ansBody.question === ctx.question && Array.isArray(ansBody.contexts) && ansBody.style === 'concise',
      'W3/answer: request = {question, contexts, style}');
  outputs['AI: Answer'] = [{ json: stubAnswer(ansBody) }];

  outputs['Prepare Log'] = runCode(N['Prepare Log'], outputs, outputs['AI: Answer']);
  const pl = outputs['Prepare Log'][0].json;
  okc(pl.session_id === null && pl.user_id === null, 'W3/log-prep: null session/user stay real null (not "null")');
  okc(typeof pl.citations === 'string' && JSON.parse(pl.citations)[0].ref === 1, 'W3/log-prep: citations JSON string');
  const p = pgParams(N['PG: Log Turn'], outputs, outputs['Prepare Log'], 'W3/log_chat_turn');
  okc(p[0] === null && p[2] === ctx.question && typeof p[4] === 'string', 'W3/log_chat_turn: 5 ordered params, $1 null');

  outputs['PG: Log Turn'] = [{ json: { session_id: '22222222-2222-4222-8222-222222222222' } }];
  const resp = evalExpr(N['Respond'].parameters.responseBody, outputs, outputs['PG: Log Turn']);
  okc(resp.session_id === '22222222-2222-4222-8222-222222222222' && resp.grounded === true
      && resp.citations.length === 1 && resp.answer.includes('[1]'),
      'W3/respond: {session_id, answer, citations, grounded}');

  // empty archive: one empty item from alwaysOutputData
  outputs['PG: Retrieve Context'] = [{ json: {} }];
  outputs['Build Contexts'] = runCode(N['Build Contexts'], outputs, outputs['PG: Retrieve Context']);
  const ctx0 = outputs['Build Contexts'][0].json;
  okc(ctx0.contexts.length === 0, 'W3/contexts: empty archive -> contexts []');
  const a0 = stubAnswer({ question: ctx0.question, contexts: ctx0.contexts });
  okc(a0.grounded === false && a0.citations.length === 0, 'W3/answer: honest not-found (grounded=false)');
})();

// =========================== W5: configuration agent ========================
(function () {
  const wf = WFS['5_agent.json'];
  const N = byName(wf);
  const outputs = {};
  outputs['Webhook: Agent'] = [{ json: { body: {
    message: 'сделай поиск более семантическим', session_id: null, user_id: null } } }];

  let p = pgParams(N['PG: Load Context'], outputs, outputs['Webhook: Agent'], 'W5/agent_context');
  okc(p[0] === null && p[1] === null, 'W5/agent_context: null user/session stay real null');
  const cfgAll = {
    search: { vector_weight: 0.7, keyword_weight: 0.3, limit: 20, snippet_source: 'summary' },
    dashboard: { widgets: ['kpi_cards','entity_distribution','top_entities','language_distribution','recent_activity','timeline'], top_n: 5 },
    taxonomy: { document_types: DEFAULT_TAXONOMY },
    chat: { retrieve_k: 6, style: 'concise' },
    custom_widgets: { widgets: [] }
  };
  const toolsAll = { resolve_entities: {}, recompute_stats: {}, reprocess_documents: {}, open_search: {} };
  outputs['PG: Load Context'] = [{ json: { config: cfgAll,
    capabilities: { search: {}, dashboard: {}, taxonomy: {}, chat: {}, custom_widgets: {} },
    history: [], tools: toolsAll } }];

  const agentBody = evalExpr(N['AI: Agent'].parameters.jsonBody, outputs, outputs['PG: Load Context']);
  okc(agentBody.message === 'сделай поиск более семантическим'
      && agentBody.current_config.search.vector_weight === 0.7
      && Array.isArray(agentBody.history) && typeof agentBody.capabilities === 'object'
      && typeof agentBody.tools === 'object',
      'W5/agent: request = {message, history, current_config, capabilities, tools}');
  outputs['AI: Agent'] = [{ json: stubAgent(agentBody) }];
  okc(outputs['AI: Agent'][0].json.actions.length === 1
      && outputs['AI: Agent'][0].json.actions[0].key === 'search'
      && outputs['AI: Agent'][0].json.actions[0].patch.vector_weight === 0.9
      && outputs['AI: Agent'][0].json.commands.length === 0,
      'W5/agent: stub → one search action (0.9/0.1), no commands');

  p = pgParams(N['PG: Apply Actions'], outputs, outputs['AI: Agent'], 'W5/agent_apply');
  okc(p[0] === null && typeof p[1] === 'string' && JSON.parse(p[1])[0].key === 'search',
      'W5/agent_apply: (user_id, actions JSON string)');
  const appliedRow = { applied: [{ key: 'search', ok: true,
    old: cfgAll.search,
    new: Object.assign({}, cfgAll.search, { vector_weight: 0.9, keyword_weight: 0.1 }) }] };
  outputs['PG: Apply Actions'] = [{ json: appliedRow }];

  p = pgParams(N['PG: Run Commands'], outputs, outputs['PG: Apply Actions'], 'W5/agent_run');
  okc(p[0] === null && p[1] === '[]',
      'W5/agent_run: (user_id, commands JSON string — empty for config-only turn)');
  outputs['PG: Run Commands'] = [{ json: { ran: [] } }];

  p = pgParams(N['PG: Log Turn'], outputs, outputs['PG: Run Commands'], 'W5/log_agent_turn');
  okc(p[0] === null && p[1] === null && p[2] === 'сделай поиск более семантическим'
      && typeof p[3] === 'string' && typeof p[4] === 'string' && JSON.parse(p[4])[0].ok === true,
      'W5/log_agent_turn: 5 ordered params, applied as JSON string');
  const newCfg = Object.assign({}, cfgAll, { search: appliedRow.applied[0].new });
  outputs['PG: Log Turn'] = [{ json: { session_id: '33333333-3333-4333-8333-333333333333', config: newCfg } }];

  const resp = evalExpr(N['Respond'].parameters.responseBody, outputs, outputs['PG: Log Turn']);
  okc(resp.session_id === '33333333-3333-4333-8333-333333333333'
      && typeof resp.reply === 'string' && resp.applied[0].ok === true
      && Array.isArray(resp.ran) && resp.config.search.vector_weight === 0.9,
      'W5/respond: {session_id, reply, applied[], ran[], config}');

  // config-only turn: Fan Reprocess emits zero items (nothing to re-ingest)
  outputs['Fan Reprocess'] = runCode(N['Fan Reprocess'], outputs, outputs['PG: Log Turn']);
  okc(outputs['Fan Reprocess'].length === 0, 'W5/fan: no reprocess command → zero fan-out items');

  // operator turn: reprocess command → agent_run returns docs → fan-out re-ingests
  const opBody = { message: 'переклассифицируй документы', history: [], current_config: cfgAll,
                   capabilities: {}, tools: toolsAll };
  const opRes = stubAgent(opBody);
  okc(opRes.commands.length === 1 && opRes.commands[0].tool === 'reprocess_documents'
      && opRes.commands[0].params.limit === 2,
      'W5/agent: reprocess request → reprocess_documents command (stub limit 2)');
  outputs['AI: Agent'] = [{ json: opRes }];
  p = pgParams(N['PG: Run Commands'], outputs, outputs['AI: Agent'], 'W5/agent_run(reprocess)');
  okc(JSON.parse(p[1])[0].tool === 'reprocess_documents', 'W5/agent_run: command serialized');
  outputs['PG: Run Commands'] = [{ json: { ran: [{ tool: 'reprocess_documents', ok: true,
    result: { count: 1, documents: [{ doc_id: '11111111-1111-4111-8111-111111111111',
      filename: 'smoke.png', original_url: 'http://minio:9000/scans/smoke.png',
      pages: [{ image_url: 'http://minio:9000/scans/smoke.png', page_no: 1 }] }] } }] } }];
  outputs['Fan Reprocess'] = runCode(N['Fan Reprocess'], outputs, outputs['PG: Run Commands']);
  okc(outputs['Fan Reprocess'].length === 1
      && outputs['Fan Reprocess'][0].json.doc_id === '11111111-1111-4111-8111-111111111111',
      'W5/fan: reprocess docs → one item per document with doc_id');
  const reBody = evalExpr(N['HTTP: Re-ingest'].parameters.jsonBody, outputs, outputs['Fan Reprocess']);
  okc(reBody.doc_id === '11111111-1111-4111-8111-111111111111'
      && Array.isArray(reBody.pages) && reBody.pages[0].image_url.includes('minio'),
      'W5/re-ingest: body carries doc_id + pages (in-place reprocess contract)');
  okc(N['HTTP: Re-ingest'].parameters.url.includes('127.0.0.1:5678/webhook/ingest'),
      'W5/re-ingest: self-webhook URL');

  // operator parity: compound + open_search + widget rule
  const cmp = stubAgent({ message: 'слей дубликаты и пересчитай статистику', current_config: cfgAll });
  okc(cmp.commands.map(c => c.tool).join(',') === 'resolve_entities,recompute_stats',
      'W5/agent: compound operator request → two commands');
  const srch = stubAgent({ message: 'найди документы про абая кунанбаева', current_config: cfgAll });
  okc(srch.commands.length === 1 && srch.commands[0].tool === 'open_search'
      && srch.commands[0].params.query.includes('абая'),
      'W5/agent: find request → open_search with query');
  const wg = stubAgent({ message: 'добавь виджет: динамика приказов по годам', current_config: cfgAll });
  okc(wg.actions.length === 1 && wg.actions[0].key === 'custom_widgets'
      && wg.actions[0].patch.widgets[0].template === 'doc_timeline'
      && wg.actions[0].patch.widgets[0].params.document_type === 'decree'
      && wg.actions[0].patch.widgets[0].params.granularity === 'year',
      'W5/agent: widget request → doc_timeline spec with taxonomy-matched type');

  // no-op path: off-scope request → empty actions, agent_apply returns []
  const noop = stubAgent({ message: 'какая погода в Алматы?', current_config: cfgAll });
  okc(noop.actions.length === 0 && noop.reply.length > 0, 'W5/agent: off-scope → honest no-op');

  // error branch wired
  okc(N['AI: Agent'].onError === 'continueErrorOutput', 'W5: AI node routes errors to the error output');
  const errResp = evalExpr(N['Respond: Error'].parameters.responseBody, outputs,
                           [{ json: { error: { message: 'boom' } } }]);
  okc(errResp.error === 'boom' && (N['Respond: Error'].parameters.options || {}).responseCode === 500,
      'W5/respond-error: HTTP 500 {error}');

  // stub-rule parity spot-checks (mirror app/agent.py)
  okc(slug('протокол') === 'protokol', 'W5/slug: протокол → protokol');
  const tax = stubAgent({ message: 'добавь тип документа «протокол»', current_config: cfgAll });
  okc(tax.actions.length === 1 && tax.actions[0].key === 'taxonomy'
      && tax.actions[0].patch.document_types[0].id === 'protokol'
      && tax.actions[0].patch.document_types.length === DEFAULT_TAXONOMY.length + 1,
      'W5/agent: add-type prepends transliterated id, keeps full array');
})();

// =========================== W6: connector pull =============================
(function () {
  const wf = WFS['6_connector_pull.json'];
  const N = byName(wf);
  const outputs = {};
  ENV.CONNECTOR_BUCKET = 'import';
  ENV.MINIO_ENDPOINT = 'http://minio:9000';
  outputs['S3: List Source Files'] = [
    { json: { Key: 'batch/a1.png', Size: 1234 } },
    { json: { Key: 'batch/a2.png', Size: 5678 } }
  ];
  outputs['Collect Files'] = runCode(N['Collect Files'], outputs, outputs['S3: List Source Files']);
  const cf = outputs['Collect Files'][0].json;
  okc(cf.files.length === 2 && cf.files[0].url === 'http://minio:9000/import/batch/a1.png',
      'W6/collect: S3 keys → {key,url,size} with bucket-prefixed urls');
  let p = pgParams(N['PG: Filter New'], outputs, outputs['Collect Files'], 'W6/filter_new');
  okc(typeof p[0] === 'string' && JSON.parse(p[0]).length === 2,
      'W6/filter_new: files serialized as one JSON param');
  outputs['PG: Filter New'] = [{ json: { new_files: [cf.files[0]] } }];
  const resp = evalExpr(N['Respond'].parameters.responseBody, outputs, outputs['PG: Filter New']);
  okc(resp.found === 2 && resp.dispatched === 1, 'W6/respond: {found, dispatched}');
  outputs['Fan Out New Files'] = runCode(N['Fan Out New Files'], outputs, outputs['PG: Filter New']);
  okc(outputs['Fan Out New Files'].length === 1
      && outputs['Fan Out New Files'][0].json.filename === 'a1.png'
      && outputs['Fan Out New Files'][0].json.pages[0].image_url.includes('/import/'),
      'W6/fan: one ingest item per new file (basename + pages[])');
  const ib = evalExpr(N['HTTP: Ingest File'].parameters.jsonBody, outputs, outputs['Fan Out New Files']);
  okc(ib.filename === 'a1.png' && Array.isArray(ib.pages), 'W6/ingest body: {filename, original_url, pages}');
  // empty bucket: alwaysOutputData placeholder → zero files, dispatched 0
  outputs['S3: List Source Files'] = [{ json: {} }];
  outputs['Collect Files'] = runCode(N['Collect Files'], outputs, outputs['S3: List Source Files']);
  okc(outputs['Collect Files'][0].json.files.length === 0, 'W6/collect: empty bucket → files []');
  okc(N['S3: List Source Files'].alwaysOutputData === true, 'W6: S3 list has alwaysOutputData');
})();

// =========================== W7: connector push =============================
(function () {
  const wf = WFS['7_connector_push.json'];
  const N = byName(wf);
  const outputs = {};
  ENV.CLIENT_WEBHOOK_URL = 'http://127.0.0.1:5678/webhook/client-sink';
  const row = { id: '44444444-4444-4444-8444-444444444444', document_id: 'd1',
                payload: { source: 'archivai', document_id: 'd1', entities: [] } };
  outputs['PG: Outbox Take'] = [{ json: row }];
  const resp = evalExpr(N['Respond'].parameters.responseBody, outputs, outputs['PG: Outbox Take']);
  okc(resp.taken === 1, 'W7/respond: {taken} from outbox batch');
  outputs['Fan Out Batch'] = runCode(N['Fan Out Batch'], outputs, outputs['PG: Outbox Take']);
  okc(outputs['Fan Out Batch'].length === 1 && outputs['Fan Out Batch'][0].json.id === row.id,
      'W7/fan: one item per outbox row');
  const pb = evalExpr(N['HTTP: Push to Client'].parameters.jsonBody, outputs, outputs['Fan Out Batch']);
  okc(pb.source === 'archivai', 'W7/push body = document payload');
  let p = pgParams(N['PG: Mark Sent'], outputs, outputs['Fan Out Batch'], 'W7/mark_sent');
  okc(p[0] === row.id, 'W7/mark_sent: outbox id via item pairing');
  p = pgParams(N['PG: Mark Failed'], outputs,
               [{ json: { error: { message: 'ECONNREFUSED' } } }], 'W7/mark_failed');
  okc(p[0] === row.id && p[1] === 'ECONNREFUSED', 'W7/mark_failed: (id, reason)');
  okc(N['HTTP: Push to Client'].onError === 'continueErrorOutput',
      'W7: push errors route to the failure branch');
  // empty outbox: placeholder row → taken 0, fan-out empty
  outputs['PG: Outbox Take'] = [{ json: {} }];
  const r0 = evalExpr(N['Respond'].parameters.responseBody, outputs, outputs['PG: Outbox Take']);
  okc(r0.taken === 0, 'W7/respond: empty outbox → taken 0');
  outputs['Fan Out Batch'] = runCode(N['Fan Out Batch'], outputs, outputs['PG: Outbox Take']);
  okc(outputs['Fan Out Batch'].length === 0, 'W7/fan: empty outbox → zero items');
  okc(N['PG: Outbox Take'].alwaysOutputData === true, 'W7: outbox take has alwaysOutputData');
})();

// =========================== W8: client sink ================================
(function () {
  const wf = WFS['8_client_sink.json'];
  const N = byName(wf);
  const outputs = {};
  outputs['Webhook: Client Sink'] = [{ json: { body: { source: 'archivai', document_id: 'd1' } } }];
  const p = pgParams(N['PG: Log Received Push'], outputs, outputs['Webhook: Client Sink'], 'W8/log_push');
  okc(typeof p[0] === 'string' && JSON.parse(p[0]).source === 'archivai',
      'W8/log_push: payload serialized to one JSON param');
  outputs['PG: Log Received Push'] = [{ json: {} }];
  const resp = evalExpr(N['Respond'].parameters.responseBody, outputs, outputs['PG: Log Received Push']);
  okc(resp.ok === true, 'W8/respond: {ok:true}');
})();

// =========================== W9: metrics intake =============================
(function () {
  const wf = WFS['9_metrics_intake.json'];
  const N = byName(wf);
  const outputs = {};
  outputs['Webhook: Metrics'] = [{ json: { body: { sensor: 's1', metrics: { temperature: 18.4, humidity: 46.5 } } } }];
  const p = pgParams(N['PG: Ingest Metric'], outputs, outputs['Webhook: Metrics'], 'W9/ingest_metric');
  okc(typeof p[0] === 'string' && JSON.parse(p[0]).metrics.temperature === 18.4,
      'W9/ingest_metric: readings serialized to one JSON param');
  outputs['PG: Ingest Metric'] = [{ json: { stored: 2 } }];
  const resp = evalExpr(N['Respond'].parameters.responseBody, outputs, outputs['PG: Ingest Metric']);
  okc(resp.stored === 2, 'W9/respond: {stored}');
})();

console.log(JSON.stringify(R));
"""


def run_harness(wfs):
    with tempfile.TemporaryDirectory() as td:
        wf_path = os.path.join(td, "wfs.json")
        js_path = os.path.join(td, "harness.js")
        with open(wf_path, "w", encoding="utf-8") as f:
            json.dump(wfs, f)
        with open(js_path, "w", encoding="utf-8") as f:
            f.write(HARNESS)
        proc = subprocess.run(["node", js_path, wf_path], capture_output=True, text=True)
        if proc.returncode != 0:
            fail(f"node harness crashed: {proc.stderr.strip()[:800]}")
            return None
        return json.loads(proc.stdout.strip().splitlines()[-1])


def main():
    step("1. Load artifacts")
    wfs = load_workflows()
    check(set(wfs) >= {"1_ingest_and_process.json", "2_search.json", "3_chat.json",
                       "4_resolve_entities.json", "5_agent.json", "6_connector_pull.json",
                       "7_connector_push.json", "8_client_sink.json", "9_metrics_intake.json"},
          f"9 workflows loaded: {sorted(wfs)}")
    sig, payload_reads, nested_reads, ent_reads, page_reads = parse_sql_functions()
    check(len(sig) >= 18, f"SQL function registry parsed ({len(sig)} functions: {sorted(sig)})")

    step("2. Workflow graph integrity")
    for name, wf in wfs.items():
        check_graph(name, wf)

    step("3. Postgres call contracts vs SQL signatures")
    for name, wf in wfs.items():
        check_pg_contracts(name, wf, sig)

    step("4. Execute Code nodes + expressions with stub AI data (node)")
    result = run_harness(wfs)
    if result:
        for c in result["checks"]:
            check(c["ok"], c["msg"])

        step("5. Payload keys vs ingest_extraction() reads")
        payload = result["data"].get("payload", {})
        missing = payload_reads - set(payload.keys()) - {"confidence"}
        check("confidence" in payload, "payload.confidence present")
        check(not missing, f"payload provides every top-level key SQL reads {sorted(payload_reads)}" +
              ("" if not missing else f" — MISSING {missing}"))
        for parent, child in nested_reads:
            check(isinstance(payload.get(parent), dict),
                  f"payload.{parent} object present (SQL reads {parent}.{child})")
        if payload.get("entities"):
            ent_keys = set(payload["entities"][0].keys())
            check(ent_reads <= ent_keys, f"entity objects carry {sorted(ent_reads)}")
        if payload.get("pages"):
            pkeys = set(payload["pages"][0].keys())
            check(page_reads <= pkeys, f"page objects carry {sorted(page_reads)}")

    print("\n====================================================")
    print(f" SIMULATION RESULT: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for m in FAIL:
            print(f"  FAILED: {m}")
        print("====================================================")
        sys.exit(1)
    print(" All mechanical checks green — stub pipeline contract holds.")
    print("====================================================")


if __name__ == "__main__":
    main()
