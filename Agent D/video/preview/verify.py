#!/usr/bin/env python3
"""
Проверка целостности проекта перед рендером.

Что смотрит:
  1. Все ассеты, на которые ссылается код, существуют.
  2. Сцены не просят у клипов больше кадров, чем в них есть
     (иначе в конце отрезка будет чёрный кадр).
  3. Импорты между модулями ведут в существующие экспорты.
  4. Сумма длительностей сцен и общий хронометраж.

Запуск:  python3 preview/verify.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PUBLIC = ROOT / "public"
FPS = 30

problems: list[str] = []


def head(title: str):
    print(f"\n\033[1m{title}\033[0m")


def check(cond: bool, msg: str):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        problems.append(msg)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out) if out else 0.0


# ── 1. Ассеты ────────────────────────────────────────────────────────────────
head("Ассеты")
refs: set[str] = set()
for f in SRC.rglob("*.tsx"):
    txt = f.read_text()
    refs |= set(re.findall(r"staticFile\(['\"]([^'\"]+)['\"]\)", txt))
    refs |= set(re.findall(r"src=['\"]((?:clips|shots|logo|audio)/[^'\"]+)['\"]", txt))
for r in sorted(refs):
    check((PUBLIC / r).exists(), f"{r}")

# ── 2. Кадры ─────────────────────────────────────────────────────────────────
head("Длительности клипов")
frames = {p.name: round(duration(p) * FPS) for p in sorted((PUBLIC / "clips").glob("*.mp4"))}
for name, fr in frames.items():
    print(f"    {name:<24} {fr:>4} кадров  ({fr / FPS:.2f} с)")

timeline = (SRC / "timeline.ts").read_text()
block = timeline.split("SCENE_SECONDS")[1].split("}")[0]
scene_secs = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+),", block)}
# Считаем только те сцены, что реально стоят в ORDER: часть заготовок лежит «на полке».
# Осторожно: в объявлении есть «SceneId[]», поэтому режем именно по «= [ ... ];».
order_block = re.search(r"export const ORDER[^=]*=\s*\[(.*?)\];", timeline, re.S)
order = re.findall(r"'(\w+)'", order_block.group(1) if order_block else "")
shelved = [s for s in scene_secs if s not in order]
total = sum(scene_secs[s] for s in order)

head("Хватает ли клипов на отрезки сцен")


def const(scene_file: str, name: str) -> int:
    src = (SRC / "scenes" / scene_file).read_text()
    m = re.search(rf"const {name} = (?:\w+ \+ )?(\d+)", src)
    if not m:
        raise SystemExit(f"не нашёл константу {name} в {scene_file}")
    return int(m.group(1))


up = const("S04Upload.tsx", "CLIP_UPLOAD")
check(up <= frames["02_upload.mp4"], f"upload: клип {up} ≤ {frames['02_upload.mp4']} кадров")
print(f"    после клипа {scene_secs['upload'] * FPS - up} кадров держим стоп-кадр upload_ready.png")

cv = const("S06Verify.tsx", "CLIP_VERIFY")
rest6 = scene_secs["verify"] * FPS - cv
check(cv <= frames["06_verify.mp4"], f"verify: первый клип {cv} ≤ {frames['06_verify.mp4']}")
check(rest6 <= frames["05_doc_detail.mp4"], f"verify: второй клип {rest6} ≤ {frames['05_doc_detail.mp4']}")

te = const("S07Search.tsx", "TYPE_END")
rs = const("S07Search.tsx", "RESULTS_END")
check(te <= frames["04a_search_type.mp4"], f"search: набор {te} ≤ {frames['04a_search_type.mp4']}")
check(rs <= frames["04b_search_results.mp4"], f"search: выдача {rs} ≤ {frames['04b_search_results.mp4']}")
check(scene_secs["search"] * FPS - (te + rs) >= 0, "search: сцена длиннее суммы клипов")

ae = const("S08Ask.tsx", "ASK_END")
rest8 = scene_secs["ask"] * FPS - (60 + ae)
check(ae <= frames["07_ask.mp4"], f"ask: вопрос {ae} ≤ {frames['07_ask.mp4']}")
check(rest8 <= frames["08_answer.mp4"], f"ask: ответ {rest8} ≤ {frames['08_answer.mp4']}")

# ── 3. Импорты ───────────────────────────────────────────────────────────────
head("Импорты между модулями")
exports: dict[str, set[str]] = {}
for f in SRC.rglob("*.ts*"):
    txt = f.read_text()
    exports[f.as_posix()] = (
        set(re.findall(r"export const (\w+)", txt))
        | set(re.findall(r"export (?:type|interface) (\w+)", txt))
        | set(re.findall(r"export function (\w+)", txt))
    )

bad = 0
for f in SRC.rglob("*.ts*"):
    for names, spec in re.findall(r"import\s*\{([^}]+)\}\s*from\s*'(\.[^']+)'", f.read_text()):
        target = None
        for ext in (".ts", ".tsx"):
            cand = Path(str((f.parent / spec).resolve()) + ext)
            if cand.exists():
                target = cand.as_posix()
        if target is None:
            print(f"  ✗ {f.name}: модуль {spec} не найден")
            bad += 1
            continue
        for n in (x.strip().split(" as ")[0] for x in names.split(",") if x.strip()):
            if n not in exports.get(target, set()):
                print(f"  ✗ {f.name}: «{n}» не экспортируется из {spec}")
                bad += 1
check(bad == 0, f"все импорты разрешаются ({len(list(SRC.rglob('*.ts*')))} файлов)")

# ── 4. Скобки ────────────────────────────────────────────────────────────────
head("Синтаксис (баланс скобок)")
unbalanced = 0
for f in sorted(SRC.rglob("*.ts*")):
    txt = f.read_text()
    for o, c in (("{", "}"), ("(", ")"), ("[", "]")):
        if txt.count(o) != txt.count(c):
            print(f"  ✗ {f.name}: {o}{c} — {txt.count(o)} / {txt.count(c)}")
            unbalanced += 1
check(unbalanced == 0, "скобки сбалансированы во всех файлах")

# ── Итог ─────────────────────────────────────────────────────────────────────
head("Итог")
check(len(order) > 0, f"сцен в монтаже: {len(order)}")
if shelved:
    print(f"    На полке (не в ORDER): {', '.join(shelved)}")
print(f"    Хронометраж: {total} с = {total * FPS} кадров = {total // 60}:{total % 60:02d}")
if problems:
    print(f"\n\033[31mПроблем: {len(problems)}\033[0m")
    sys.exit(1)
print("\n\033[32mВсё сходится — можно рендерить.\033[0m")
