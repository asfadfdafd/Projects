"""Phase 5 — the ArchivAI configuration agent (stateless).

One LLM call turns a natural-language request ("сделай поиск более семантическим")
into structured actions [{key, patch, reason}]. This module never touches the
database: n8n applies the actions via Postgres agent_apply()/set_config(), which
re-validate every field against the capability manifest.

Stub mode is deterministic keyword rules so `make smoke` exercises the full loop
with no models. The JS port of these rules lives in
scripts/simulate_stub_pipeline.py (keep the two in sync).
"""
import re
from typing import List, Optional, Tuple

from .config import settings
from .schemas import AgentRequest, AgentResponse, AgentAction, AgentCommand
from . import llm
from .prompts import AGENT_SYSTEM

# --- stub helpers -----------------------------------------------------------

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    # Kazakh Cyrillic extras
    "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u", "ү": "u",
    "һ": "h", "і": "i",
}


def slug(word: str) -> str:
    """Latin snake_case id from a (possibly Cyrillic) label; matches ^[a-z0-9_]{2,40}$."""
    out = "".join(_TRANSLIT.get(ch, ch) for ch in word.lower())
    out = re.sub(r"[^a-z0-9]+", "_", out).strip("_")[:40]
    return out


_HIDE_WORDS = ("убери", "убрать", "скрой", "скрыть", "спрячь", "hide", "remove")
_WIDGET_SYNONYMS = {
    "timeline": ("таймлайн", "timeline", "хронолог"),
    "recent_activity": ("активност", "recent"),
    "language_distribution": ("язык", "language"),
    "entity_distribution": ("распределение", "донат", "donut"),
    "kpi_cards": ("kpi", "карточк"),
    "top_entities": ("топ сущ", "top entities"),
}


def _stub_agent(req: AgentRequest) -> AgentResponse:
    """Deterministic rules covering the demo phrases; everything else → honest no-op."""
    msg = req.message.lower()
    cfg = req.current_config or {}
    actions: List[AgentAction] = []
    said: List[str] = []

    # search: more semantic / more keyword
    if "семантич" in msg or "вектор" in msg:
        actions.append(AgentAction(key="search",
                                   patch={"vector_weight": 0.9, "keyword_weight": 0.1},
                                   reason="user asked for more semantic search"))
        said.append("вес семантического поиска повышен до 0.9")
    elif "ключев" in msg or "точн" in msg:
        actions.append(AgentAction(key="search",
                                   patch={"vector_weight": 0.4, "keyword_weight": 0.6},
                                   reason="user asked for more exact/keyword search"))
        said.append("вес точного поиска повышен до 0.6")

    # dashboard: hide a widget
    if any(w in msg for w in _HIDE_WORDS):
        current = list((cfg.get("dashboard") or {}).get("widgets") or [])
        for wid, syns in _WIDGET_SYNONYMS.items():
            if any(s in msg for s in syns) and wid in current:
                new = [w for w in current if w != wid]
                actions.append(AgentAction(key="dashboard", patch={"widgets": new},
                                           reason=f"hide widget {wid}"))
                said.append(f"виджет «{wid}» скрыт с дашборда")
                break

    # dashboard: top-N size
    m = re.search(r"топ[\s\-–]*(\d+)", msg)
    if m:
        n = max(3, min(10, int(m.group(1))))
        actions.append(AgentAction(key="dashboard", patch={"top_n": n},
                                   reason="user asked for a different top size"))
        said.append(f"топ-списки показывают {n} позиций")

    # taxonomy: add a document type (prepended → stub extraction picks it up)
    if "тип" in msg and ("добав" in msg or "add" in msg):
        qm = re.search(r"[«\"„']([^»\"“']{2,40})[»\"“']", req.message)
        word = qm.group(1).strip() if qm else None
        if not word:
            tail = re.search(r"тип(?:\s+документа)?\s+([а-яёәғқңөұүһіa-z0-9_ -]{2,40})",
                             msg)
            word = tail.group(1).strip() if tail else None
        if word:
            tid = slug(word)
            types = list((cfg.get("taxonomy") or {}).get("document_types") or [])
            if tid and all(t.get("id") != tid for t in types):
                new_types = [{"id": tid, "label": word.capitalize()}] + types
                actions.append(AgentAction(key="taxonomy",
                                           patch={"document_types": new_types},
                                           reason=f"add document type {tid}"))
                said.append(f"тип документа «{word}» (id: {tid}) добавлен в таксономию")

    # chat: answer style
    if "подробн" in msg:
        actions.append(AgentAction(key="chat", patch={"style": "detailed"},
                                   reason="user asked for detailed answers"))
        said.append("ассистент будет отвечать подробнее")
    elif "кратк" in msg or "коротк" in msg:
        actions.append(AgentAction(key="chat", patch={"style": "concise"},
                                   reason="user asked for concise answers"))
        said.append("ассистент будет отвечать кратко")

    # custom widget: «добавь виджет: динамика приказов по годам»
    commands: List[AgentCommand] = []
    if "виджет" in msg and "добав" in msg:
        types = (cfg.get("taxonomy") or {}).get("document_types") or []
        dt = None
        for tt in types:
            words = (tt.get("label") or tt.get("id") or "").lower().split()
            word = words[0].strip() if words else ""
            if len(word) >= 4 and word in msg:
                dt = tt.get("id")
                break
        if "год" in msg or "динамик" in msg or "врем" in msg:
            template, params = "doc_timeline", {"granularity": "year"}
            title = "Динамика документов"
        else:
            template, params = "doc_count", {"group_by": "document_type"}
            title = "Документы по типам"
        if dt:
            params["document_type"] = dt
        wid = "w_" + template + "_" + (dt or "all")
        widgets = list((cfg.get("custom_widgets") or {}).get("widgets") or [])
        if all(x.get("id") != wid for x in widgets):
            widgets.append({"id": wid, "title": title, "template": template,
                            "params": params})
            actions.append(AgentAction(key="custom_widgets",
                                       patch={"widgets": widgets},
                                       reason="add custom widget"))
            said.append(f"виджет «{title}» добавлен на дашборд")

    # operator commands
    if "дубл" in msg and ("сл" in msg or "объедин" in msg or "убер" in msg):
        commands.append(AgentCommand(tool="resolve_entities", params={},
                                     reason="merge duplicate entities"))
        said.append("запущено слияние дубликатов")
    if "пересчит" in msg and "статист" in msg:
        commands.append(AgentCommand(tool="recompute_stats", params={},
                                     reason="recompute dashboard stats"))
        said.append("статистика пересчитывается")
    if "переклассифиц" in msg or "переобработ" in msg:
        # stub keeps the blast radius tiny (2 newest docs = this test run's own);
        # the real model chooses limit per request (agent_run caps at 20)
        commands.append(AgentCommand(tool="reprocess_documents",
                                     params={"limit": 2},
                                     reason="re-run documents through the pipeline"))
        said.append("документы отправлены на переобработку")
    ms = re.search(r"(?:найди|покажи)\s+(?:все\s+)?(?:документы\s+)?(?:про|о|об)\s+(.{2,80})",
                   msg)
    if ms:
        commands.append(AgentCommand(tool="open_search",
                                     params={"query": ms.group(1).strip().rstrip("?.!")},
                                     reason="open prepared search"))
        said.append("открываю поиск")

    if actions or commands:
        return AgentResponse(reply="[stub] Готово: " + "; ".join(said) + ".",
                             actions=actions, commands=commands)
    return AgentResponse(
        reply=("[stub] Это я сделать не могу. Доступно: поиск (веса, число "
               "результатов, сниппеты), дашборд (виджеты, топ-N, кастомные виджеты), "
               "таксономия типов документов, стиль ответов чата; операции: слияние "
               "дубликатов, пересчёт статистики, переобработка документов, поиск."),
        actions=[], commands=[])


# --- real model --------------------------------------------------------------

def _build_user_prompt(req: AgentRequest) -> str:
    import json
    lines = [
        "CAPABILITIES:",
        json.dumps(req.capabilities, ensure_ascii=False),
        "",
        "TOOLS:",
        json.dumps(req.tools, ensure_ascii=False),
        "",
        "CURRENT_CONFIG:",
        json.dumps(req.current_config, ensure_ascii=False),
    ]
    if req.history:
        lines += ["", "RECENT CONVERSATION:"]
        for h in req.history[-6:]:
            lines.append(f"{h.get('role', '?')}: {h.get('content', '')}")
    lines += ["", f"USER REQUEST: {req.message}", "", "JSON:"]
    return "\n".join(lines)


def _coerce(raw: dict) -> Tuple[str, List[AgentAction], List[AgentCommand]]:
    reply = str(raw.get("reply") or "").strip()
    actions: List[AgentAction] = []
    for a in raw.get("actions") or []:
        if not isinstance(a, dict):
            continue
        key = a.get("key")
        patch = a.get("patch")
        if isinstance(key, str) and key.strip() and isinstance(patch, dict) and patch:
            actions.append(AgentAction(key=key.strip(), patch=patch,
                                       reason=a.get("reason")))
    commands: List[AgentCommand] = []
    for c in raw.get("commands") or []:
        if not isinstance(c, dict):
            continue
        tool = c.get("tool")
        params = c.get("params")
        if isinstance(tool, str) and tool.strip():
            commands.append(AgentCommand(tool=tool.strip(),
                                         params=params if isinstance(params, dict) else {},
                                         reason=c.get("reason")))
    return reply, actions, commands


def _merge_additive_taxonomy(actions: List[AgentAction], current_config: dict) -> List[AgentAction]:
    """Small-model accommodation (seen live on qwen2.5:3b): the model sends ONLY the
    new type(s) instead of the full replacement array. When the patched list has zero
    id-overlap with the current taxonomy, treat it as additive: prepend the new items
    to the current list. Lists that share ids with the current taxonomy are taken as
    intentional replacements (e.g. removals) and pass through. PG still validates."""
    current = ((current_config or {}).get("taxonomy") or {}).get("document_types") or []
    cur_ids = {t.get("id") for t in current if isinstance(t, dict)}
    for a in actions:
        if a.key != "taxonomy" or not isinstance(a.patch.get("document_types"), list):
            continue
        items = [t for t in a.patch["document_types"] if isinstance(t, dict)]
        ids = {t.get("id") for t in items}
        if items and cur_ids and not (ids & cur_ids):
            a.patch["document_types"] = items + [t for t in current if t.get("id") not in ids]
    return actions


def _rescue_misplaced_tools(actions: List[AgentAction], commands: List[AgentCommand],
                            tools: dict) -> Tuple[List[AgentAction], List[AgentCommand]]:
    """Small-model accommodation (seen live on qwen2.5:3b): an operator tool emitted
    as a config ACTION (key='reprocess_documents'). Move it where it belongs."""
    keep: List[AgentAction] = []
    for a in actions:
        if a.key in (tools or {}):
            commands.append(AgentCommand(tool=a.key,
                                         params=a.patch if isinstance(a.patch, dict) else {},
                                         reason=a.reason))
        else:
            keep.append(a)
    return keep, commands


def run_agent(req: AgentRequest) -> AgentResponse:
    if settings.STUB:
        return _stub_agent(req)

    raw_txt = llm.chat(settings.TEXT_MODEL, AGENT_SYSTEM,
                       _build_user_prompt(req), json_mode=True)
    try:
        raw = llm.parse_json_lenient(raw_txt)
    except Exception:
        return AgentResponse(
            reply="Не удалось разобрать ответ модели — настройки не изменены. "
                  "Сформулируйте, пожалуйста, иначе.",
            actions=[])
    reply, actions, commands = _coerce(raw)
    actions, commands = _rescue_misplaced_tools(actions, commands, req.tools)
    actions = _merge_additive_taxonomy(actions, req.current_config)
    if not reply:
        reply = ("Выполняю." if (actions or commands) else
                 "Я не понял запрос. Доступно: поиск, дашборд и кастомные виджеты, "
                 "таксономия типов документов, стиль чата; операции: слияние "
                 "дубликатов, пересчёт статистики, переобработка, поиск.")
    return AgentResponse(reply=reply, actions=actions, commands=commands)
