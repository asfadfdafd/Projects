#!/usr/bin/env python3
"""
Сборка превью-версии ролика ArchivAI (аниматик).

Зачем это нужно: Remotion рендерит через headless Chrome и требует npm install.
Этот скрипт собирает тот же монтаж средствами PIL + ffmpeg — без браузера и без
node_modules. Тайминги, порядок сцен и тексты совпадают с Remotion-проектом,
поэтому превью годится, чтобы утвердить структуру до финального рендера.

Отличие от финала: тексты в превью статичны (в Remotion они выезжают и
проявляются), а записи экрана и наезды камеры — настоящие.

Запуск:  python3 preview/build_preview.py
Выход:   out/archivai-preview.mp4
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
OUT = ROOT / "out"
# Промежуточные файлы держим во временной папке системы: сборку можно прервать
# и продолжить, а мусор не оседает в проекте. Чистится ключом --clean.
WORK = Path(tempfile.gettempdir()) / "archivai-preview-work"
WORK.mkdir(parents=True, exist_ok=True)

W, H = 1920, 1080
FPS = 30

# ── Палитра (снята пипеткой со скриншотов продукта) ──────────────────────────
NAVY = (17, 27, 49)
NAVY_MUTED = (65, 80, 110)
ORANGE = (232, 123, 53)
ORANGE_SOFT = (253, 238, 227)
BG = (242, 245, 249)
WHITE = (255, 255, 255)
INK = (22, 35, 60)
INK_MUTED = (107, 122, 147)
LINE = (223, 229, 238)
GREEN = (31, 157, 99)
GREEN_SOFT = (230, 245, 237)
GREEN_INK = (19, 122, 74)
BLUE = (47, 107, 216)
RED = (217, 83, 79)

FONT_DIR = "/usr/share/fonts/truetype/lato"
FONTS = {
    "black": f"{FONT_DIR}/Lato-Black.ttf",
    "bold": f"{FONT_DIR}/Lato-Bold.ttf",
    "semi": f"{FONT_DIR}/Lato-Semibold.ttf",
    "reg": f"{FONT_DIR}/Lato-Regular.ttf",
    "med": f"{FONT_DIR}/Lato-Medium.ttf",
}
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


SYMBOL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONTS[weight], size)
    return _font_cache[key]


def symbol(size: int) -> ImageFont.FreeTypeFont:
    """DejaVu — в нём есть ✓ и прочие знаки, которых нет в Lato."""
    key = ("sym", size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(SYMBOL_FONT, size)
    return _font_cache[key]


# ── Примитивы рисования ──────────────────────────────────────────────────────
def dr(im: Image.Image) -> ImageDraw.ImageDraw:
    """Обычная рисовалка. Для полупрозрачных фигур используйте translucent()."""
    return ImageDraw.Draw(im, "RGBA")


def translucent(im: Image.Image):
    """
    PIL не умеет смешивать полупрозрачные заливки поверх RGBA-картинки —
    он их просто затирает. Поэтому рисуем такие фигуры на отдельном слое
    и накладываем его alpha_composite'ом.

    Использование:
        with translucent(im) as d:
            d.rounded_rectangle(..., fill=(255, 255, 255, 14))
    """

    class _Layer:
        def __enter__(self):
            self.layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
            return ImageDraw.Draw(self.layer)

        def __exit__(self, *exc):
            im.alpha_composite(self.layer)
            return False

    return _Layer()


def over(color, alpha: float, base=(17, 27, 49)):
    """Плоское смешивание цвета с фоном — для текста поверх известной подложки."""
    return tuple(int(base[i] * (1 - alpha) + color[i] * alpha) for i in range(3))


def radial(size, center, radius, color, alpha):
    """Мягкое цветное свечение."""
    g = Image.radial_gradient("L").resize((radius * 2, radius * 2), Image.LANCZOS)
    g = Image.eval(g, lambda v: int(max(0, 255 - v) * alpha))
    layer = Image.new("RGBA", size, color + (0,))
    tint = Image.new("RGBA", (radius * 2, radius * 2), color + (255,))
    tint.putalpha(g)
    layer.alpha_composite(tint, (center[0] - radius, center[1] - radius))
    return layer


def dot_grid(size, color, alpha, step=38):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, 'RGBA')
    for y in range(0, size[1], step):
        for x in range(0, size[0], step):
            d.ellipse([x, y, x + 1.6, y + 1.6], fill=color + (alpha,))
    return layer


def backdrop(dark=False) -> Image.Image:
    base = Image.new("RGBA", (W, H), (NAVY if dark else BG) + (255,))
    base.alpha_composite(dot_grid((W, H), WHITE if dark else NAVY, 14 if dark else 14))
    base.alpha_composite(radial((W, H), (int(W * 0.80), int(H * 0.15)), 760, ORANGE, 0.20 if dark else 0.14))
    base.alpha_composite(
        radial((W, H), (int(W * 0.10), int(H * 0.90)), 700, BLUE if dark else NAVY, 0.18 if dark else 0.07)
    )
    return base


def shadow(box, radius, blur=34, spread=18, alpha=90):
    x, y, w, h = box
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, 'RGBA')
    d.rounded_rectangle(
        [x - spread // 3, y + spread, x + w + spread // 3, y + h + spread + 10],
        radius=radius,
        fill=NAVY + (alpha,),
    )
    return layer.filter(ImageFilter.GaussianBlur(blur))


def wrap(draw, text, fnt, max_w):
    """Перенос строк по фактической ширине глифов."""
    words, lines, cur = text.split(), [], ""
    for word in words:
        probe = f"{cur} {word}".strip()
        if draw.textlength(probe, font=fnt) <= max_w or not cur:
            cur = probe
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def text_block(d, xy, text, fnt, fill, max_w, line_h=None, spacing=0):
    x, y = xy
    lh = line_h or int(fnt.size * 1.32)
    for line in wrap(d, text, fnt, max_w):
        d.text((x, y), line, font=fnt, fill=fill)
        y += lh + spacing
    return y


def kicker(d, xy, text, color=ORANGE):
    x, y = xy
    f = font("black", 21)
    d.rounded_rectangle([x, y + 10, x + 34, y + 13], radius=2, fill=color)
    spaced = " ".join(text.upper())
    d.text((x + 48, y - 2), spaced, font=f, fill=color)
    return y + 38


def chip(d, xy, text, tone="light"):
    palette = {
        "light": (WHITE, INK, LINE),
        "navy": (NAVY, WHITE, NAVY),
        "orange": (ORANGE_SOFT, (182, 90, 25), (246, 217, 195)),
        "green": (GREEN_SOFT, GREEN_INK, (196, 232, 213)),
    }[tone]
    f = font("bold", 21)
    x, y = xy
    tw = d.textlength(text, font=f)
    box = [x, y, x + tw + 40, y + 46]
    d.rounded_rectangle(box, radius=23, fill=palette[0], outline=palette[2], width=1)
    d.text((x + 20, y + 10), text, font=f, fill=palette[1])
    return box[2] + 14


def feature_row(im, d, xy, w, title, note=None, dot=ORANGE, check=True, dark=False):
    x, y = xy
    h = 88 if note else 66
    if not dark:
        im.alpha_composite(shadow((x, y, w, h), 14, blur=18, spread=8, alpha=42))
    d.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=14,
        fill=(255, 255, 255, 13) if dark else WHITE + (255,),
        outline=(255, 255, 255, 28) if dark else LINE + (255,),
        width=1,
    )
    d.ellipse([x + 22, y + h // 2 - 6, x + 34, y + h // 2 + 6], fill=dot)
    ty = y + (18 if note else 18)
    d.text((x + 54, ty), title, font=font("bold", 25), fill=WHITE if dark else INK)
    if note:
        d.text(
            (x + 54, ty + 34),
            note,
            font=font("reg", 19),
            fill=(255, 255, 255, 160) if dark else INK_MUTED,
        )
    if check:
        # Галочки нет в Lato — берём её из DejaVu Sans
        d.text((x + w - 44, y + h // 2 - 14), "✓", font=symbol(24), fill=GREEN)
    return y + h + 16


def caption(im, d, text, accent=ORANGE, bottom=62):
    f = font("bold", 26)
    tw = d.textlength(text, font=f)
    w = tw + 88
    x = (W - w) / 2
    y = H - bottom - 64
    im.alpha_composite(shadow((int(x), int(y), int(w), 64), 32, blur=26, spread=12, alpha=110))
    d.rounded_rectangle([x, y, x + w, y + 64], radius=32, fill=NAVY)
    d.ellipse([x + 30, y + 27, x + 40, y + 37], fill=accent)
    d.text((x + 54, y + 17), text, font=f, fill=WHITE)


def browser_frame(im, d, rect, url):
    """Рисует рамку браузера и пробивает прозрачное окно под контент."""
    x, y, w, h = rect  # rect — область КОНТЕНТА (без шапки)
    bar = 46
    outer = (x, y - bar, w, h + bar)
    im.alpha_composite(shadow(outer, 18, blur=44, spread=22, alpha=110))
    d.rounded_rectangle(
        [outer[0], outer[1], outer[0] + outer[2], outer[1] + outer[3]],
        radius=18,
        fill=WHITE + (255,),
        outline=LINE + (255,),
        width=1,
    )
    d.rectangle([x, y - bar, x + w, y], fill=(247, 249, 252, 255))
    d.line([x, y, x + w, y], fill=LINE + (255,), width=1)
    for i, col in enumerate([(231, 117, 107), (233, 180, 76), (103, 192, 138)]):
        cx = x + 22 + i * 19
        d.ellipse([cx, y - bar // 2 - 6, cx + 11, y - bar // 2 + 5], fill=col)
    d.rounded_rectangle(
        [x + 92, y - bar // 2 - 13, x + 92 + 360, y - bar // 2 + 13],
        radius=13,
        fill=WHITE + (255,),
        outline=LINE + (255,),
        width=1,
    )
    d.text((x + 106, y - bar // 2 - 9), url, font=font("reg", 15), fill=INK_MUTED)
    # прозрачное окно — сюда ffmpeg подложит видео
    im.paste((0, 0, 0, 0), (x, y, x + w, y + h))


def pipeline(im, d, xy, steps, scale=1.0, dark=False):
    x, y = xy
    bw, bh, gap = int(214 * scale), int(84 * scale), int(34 * scale)
    for i, (label, note) in enumerate(steps):
        if not dark:
            im.alpha_composite(shadow((x, y, bw, bh), 14, blur=20, spread=8, alpha=40))
        d.rounded_rectangle(
            [x, y, x + bw, y + bh],
            radius=14,
            fill=(255, 255, 255, 15) if dark else WHITE + (255,),
            outline=(240, 205, 175, 255) if not dark else (255, 255, 255, 32),
            width=1,
        )
        d.ellipse([x + 22, y + 26, x + 32, y + 36], fill=ORANGE)
        d.text((x + 44, y + 18), label, font=font("bold", int(23 * scale)), fill=WHITE if dark else INK)
        if note:
            d.text(
                (x + 44, y + 46),
                note,
                font=font("reg", int(17 * scale)),
                fill=(255, 255, 255, 150) if dark else INK_MUTED,
            )
        if i < len(steps) - 1:
            d.rounded_rectangle(
                [x + bw + 4, y + bh // 2 - 2, x + bw + gap - 4, y + bh // 2 + 1],
                radius=2,
                fill=ORANGE,
            )
        x += bw + gap
    return y + bh


def kpi(im, d, xy, value, label, w=316, h=150):
    x, y = xy
    im.alpha_composite(shadow((x, y, w, h), 16, blur=24, spread=10, alpha=48))
    d.rounded_rectangle([x, y, x + w, y + h], radius=16, fill=WHITE + (255,), outline=LINE + (255,), width=1)
    d.text((x + 28, y + 22), str(value), font=font("black", 62), fill=INK)
    d.text((x + 28, y + 104), label, font=font("bold", 19), fill=INK_MUTED)


def paste_photo(im, path, box, rotate=0.0, radius=14, border=True):
    """Вклеивает картинку в скруглённую карточку (для скана в сцене «Проблема»)."""
    x, y, w, h = box
    src = Image.open(PUBLIC / path).convert("RGBA")
    src = src.resize((w, h), Image.LANCZOS)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=radius, fill=255)
    src.putalpha(mask)
    if border:
        card = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
        ImageDraw.Draw(card).rounded_rectangle([0, 0, w + 1, h + 1], radius=radius + 1, fill=LINE + (255,))
        card.alpha_composite(src, (1, 1))
        src = card
    if rotate:
        src = src.rotate(rotate, expand=True, resample=Image.BICUBIC)
        x -= (src.width - w) // 2
        y -= (src.height - h) // 2
    im.alpha_composite(shadow((x, y, src.width, src.height), radius, blur=40, spread=20, alpha=120))
    im.alpha_composite(src, (x, y))


def wordmark(d, xy, size, dark=False, tagline=True):
    x, y = xy
    f = font("black", size)
    d.text((x, y), "Archiv", font=f, fill=WHITE if dark else NAVY)
    w1 = d.textlength("Archiv", font=f)
    d.text((x + w1, y), "AI", font=f, fill=ORANGE)
    if tagline:
        d.text(
            (x + 3, y + int(size * 1.16)),
            "open-source archive intelligence",
            font=font("med", int(size * 0.19)),
            fill=(255, 255, 255, 150) if dark else INK_MUTED,
        )


# ── Геометрия ────────────────────────────────────────────────────────────────
SPLIT = dict(x=80, y=290, w=980, h=546, tx=1130, tw=710)          # рамка слева
SPLIT_R = dict(x=900, y=301, w=940, h=524, tx=90, tw=700)          # рамка справа
HERO = dict(x=345, y=242, w=1230, h=686)                           # рамка по центру
ENT = dict(x=840, y=281, w=1010, h=563)
AGENT = dict(x=1024, y=218, w=800, h=690)
CTRL = dict(x=906, y=301, w=940, h=524)


# ── Сегменты монтажа ─────────────────────────────────────────────────────────
@dataclass
class Segment:
    name: str
    seconds: float
    overlay: str                      # имя PNG-оверлея
    media: str | None = None          # клип или скриншот
    rect: dict | None = None          # куда его класть
    zoom: tuple[float, float] = (1.02, 1.09)
    focus: tuple[float, float] = (0.5, 0.35)
    dark: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def scene(self) -> str:
        """Сегменты одной сцены называются scene_a, scene_b — склеиваются встык."""
        return self.name.split("_")[0]

    # заполняется в main(): растворение только на границах СЦЕН, не подрезок
    fade_in: str | None = None
    fade_out: str | None = None


SEGMENTS: list[Segment] = []


def add(**kw):
    SEGMENTS.append(Segment(**kw))


# ══════════════════════════════════════════════════════════════════════════════
#  ОВЕРЛЕИ СЦЕН
# ══════════════════════════════════════════════════════════════════════════════
def sc_intro():
    im = backdrop()
    scan = Image.open(PUBLIC / "shots/scan_source.png").convert("RGBA")
    scan = scan.resize((700, 1050), Image.LANCZOS).rotate(6, expand=True, resample=Image.BICUBIC)
    scan.putalpha(scan.getchannel("A").point(lambda v: int(v * 0.16)))
    im.alpha_composite(scan, (1330, -60))
    d = dr(im)
    x = 150
    chip(d, (x, 250), "РАБОТАЕТ НА ВАШЕМ СЕРВЕРЕ · РУССКИЙ И КАЗАХСКИЙ", "orange")
    wordmark(d, (x, 330), 104, tagline=False)
    f = font("black", 74)
    d.text((x, 500), "Архив, который можно ", font=f, fill=INK)
    off = d.textlength("Архив, который можно ", font=f)
    d.text((x + off, 500), "спросить", font=f, fill=ORANGE)
    d.text((x + off + d.textlength("спросить", font=f), 500), ".", font=f, fill=INK)
    text_block(
        d, (x, 620),
        "Сканы XX века превращаются в текст, имена, даты и места — и документы "
        "наконец можно искать обычными словами.",
        font("reg", 30), INK_MUTED, 880, line_h=44,
    )
    cx = x
    for t in ["Распознавание текста", "Поиск по смыслу", "Связи между делами",
              "Настройка без программиста"]:
        cx = chip(d, (cx, 760), t)
    return im


def sc_problem():
    im = backdrop()
    d = dr(im)
    y = kicker(d, (90, 96), "Проблема", NAVY_MUTED)
    text_block(d, (90, y + 18), "Оцифровали — но пользоваться всё равно нельзя", font("black", 60), INK, 1400, line_h=70)
    paste_photo(im, "shots/scan_source.png", (100, 300, 420, 630), rotate=-2.2)
    d = dr(im)
    f = font("bold", 20)
    label = "скан.jpg · текста внутри нет"
    tw = d.textlength(label, font=f)
    d.rounded_rectangle([470, 810, 470 + tw + 44, 862], radius=26, fill=NAVY)
    d.text((492, 823), label, font=f, fill=WHITE)
    ry = 350
    for title, note in [
        ("Скан — это картинка", "Внутри файла нет текста: найти документ по содержанию невозможно"),
        ("Вход только через опись", "Найти можно лишь то, что кто-то заранее описал вручную"),
        ("Описание — это месяцы работы", "Имена, даты и организации выписываются от руки по каждому делу"),
    ]:
        ry = feature_row(im, dr(im), (610, ry), 1210, title, note, dot=RED, check=False)
    return im


def sc_how():
    im = backdrop()
    d = dr(im)
    y = kicker(d, (90, 150), "Как это работает")
    y = text_block(d, (90, y + 16), "От скана до ответа — один процесс", font("black", 58), INK, 1400, line_h=68)
    y = text_block(
        d, (90, y + 14),
        "Вы загружаете скан. Дальше система сама распознаёт текст, определяет вид "
        "документа, выписывает имена, даты и места — и дело становится доступным для поиска.",
        font("reg", 27), INK_MUTED, 1120, line_h=40,
    )
    y = pipeline(im, dr(im), (90, y + 50), [
        ("Скан", "фото или PDF"), ("Распознавание", "рус · каз"), ("Разбор", "вид · дата · суть"),
        ("Имена и даты", "люди · места"), ("Проверка", "архивистом"), ("Поиск", "обычными словами"),
    ], scale=0.98)
    d = dr(im)
    cx = 90
    for t, tone in [("Всё на вашем сервере", "navy"), ("Интернет для работы не нужен", "light"),
                    ("Без подписок и лицензий", "light")]:
        cx = chip(d, (cx, y + 54), t, tone)
    d.text(
        (90, y + 118),
        "Для технической службы: n8n, PostgreSQL и языковые модели — "
        "всё с открытым кодом, ставится одной командой.",
        font=font("reg", 20),
        fill=INK_MUTED,
    )
    caption(im, dr(im), "Документы никуда не отправляются — они не покидают учреждение", GREEN)
    return im


def _split_text(im, cfg, kick, title, rows, top=236):
    d = dr(im)
    y = kicker(d, (cfg["tx"], top), kick)
    y = text_block(d, (cfg["tx"], y + 16), title, font("black", 50), INK, cfg["tw"], line_h=58)
    y += 30
    for title_, note in rows:
        y = feature_row(im, dr(im), (cfg["tx"], y), cfg["tw"], title_, note)
    return im


def sc_upload():
    im = backdrop()
    browser_frame(im, dr(im), (SPLIT["x"], SPLIT["y"], SPLIT["w"], SPLIT["h"]), "archivai.local/upload")
    return _split_text(im, SPLIT, "Шаг 1 · Загрузка", "Положите сканы — дальше система сама", [
        ("Фото, JPG, PNG, TIFF", "Многостраничное дело собирается в один документ"),
        ("Хоть вся папка целиком", "Или система сама заберёт сканы из указанного хранилища"),
        ("Файлы остаются у вас", "Хранятся на вашем сервере, посторонним они недоступны"),
    ], top=250)


def sc_process(done: bool):
    im = backdrop()
    browser_frame(im, dr(im), (SPLIT_R["x"], SPLIT_R["y"], SPLIT_R["w"], SPLIT_R["h"]),
                  "archivai.local/documents/stenogramma1931")
    d = dr(im)
    badge = "Готово" if done else "Обработка…"
    f = font("bold", 21)
    tw = d.textlength(badge, font=f) + (26 if done else 0)
    bx, by = SPLIT_R["x"] + 26, SPLIT_R["y"] + SPLIT_R["h"] - 78
    d.rounded_rectangle([bx, by, bx + tw + 44, by + 52], radius=26, fill=GREEN if done else NAVY)
    if done:
        d.text((bx + 22, by + 14), "✓", font=symbol(20), fill=WHITE)
    d.text((bx + 22 + (26 if done else 0), by + 13), badge, font=f, fill=WHITE)
    y = kicker(d, (90, 190), "Шаг 2 · Обработка")
    y = text_block(d, (90, y + 16), "Распознаёт текст и сразу разбирает дело", font("black", 50), INK, 700, line_h=58)
    y = text_block(
        d, (90, y + 16),
        "Система читает скан, определяет язык и вид документа, составляет короткое "
        "описание и выписывает людей, организации, места и даты.",
        font("reg", 24), INK_MUTED, 700, line_h=36,
    )
    y = pipeline(im, dr(im), (90, y + 42),
                 [("Распознавание", None), ("Язык", None), ("Вид дела", None)], scale=0.72)
    y = pipeline(im, dr(im), (90, y + 16),
                 [("Описание", None), ("Имена и даты", None), ("Поиск", None)], scale=0.72)
    if done:
        d = dr(im)
        d.rounded_rectangle([90, y + 40, 790, y + 148], radius=14, fill=GREEN_SOFT, outline=(196, 232, 213), width=1)
        text_block(
            d, (114, y + 60),
            "Ничего не берётся из воздуха: видно, из какого места документа взято "
            "каждое поле, и любое из них можно поправить.",
            font("reg", 22), (19, 99, 65), 650, line_h=32,
        )
    return im


def sc_verify(cap_text, accent):
    im = backdrop()
    d = dr(im)
    y = kicker(d, (HERO["x"], 74), "Шаг 3 · Проверка человеком")
    text_block(d, (HERO["x"], y + 12), "Последнее слово — за архивистом", font("black", 46), INK, 1230, line_h=54)
    browser_frame(im, dr(im), (HERO["x"], HERO["y"], HERO["w"], HERO["h"]), "archivai.local/documents")
    caption(im, dr(im), cap_text, accent, bottom=48)
    return im


def sc_search(cap_text, accent):
    im = backdrop()
    d = dr(im)
    y = kicker(d, (HERO["x"], 74), "Шаг 4 · Поиск")
    text_block(d, (HERO["x"], y + 12), "Спрашивайте словами, а не шифром дела", font("black", 46), INK, 1230, line_h=54)
    browser_frame(im, dr(im), (HERO["x"], HERO["y"], HERO["w"], HERO["h"]), "archivai.local/search")
    caption(im, dr(im), cap_text, accent, bottom=48)
    return im


def sc_ask(show_callout: bool):
    im = backdrop()
    browser_frame(im, dr(im), (SPLIT["x"], SPLIT["y"], SPLIT["w"], SPLIT["h"]), "archivai.local/chat")
    im = _split_text(im, SPLIT, "Шаг 5 · Вопрос архиву", "Ответ — только из ваших документов", [
        ("Каждый ответ со ссылкой", "Нажмите на источник — откроется нужный скан"),
        ("Ничего не выдумывает", "Нет данных в архиве — так и скажет"),
        ("Любой язык вопроса", "Русский, казахский, английский — в одном диалоге"),
        ("Диалог сохраняется", "Можно уточнять и возвращаться к прошлым вопросам"),
    ], top=220)
    if show_callout:
        d = dr(im)
        label = "(1) архив.jpg — ссылка открывает сам документ"
        f = font("bold", 21)
        tw = d.textlength(label, font=f)
        bx, by = SPLIT["x"] + 40, SPLIT["y"] + SPLIT["h"] + 12
        im.alpha_composite(shadow((bx, by, int(tw + 48), 56), 28, blur=24, spread=10, alpha=110))
        d = dr(im)
        d.rounded_rectangle([bx, by, bx + tw + 48, by + 56], radius=28, fill=NAVY)
        d.text((bx + 24, by + 15), label, font=f, fill=WHITE)
    return im


def sc_entities():
    im = backdrop()
    browser_frame(im, dr(im), (ENT["x"], ENT["y"], ENT["w"], ENT["h"]), "archivai.local/entities")
    d = dr(im)
    y = kicker(d, (90, 250), "Шаг 5 · Связи")
    y = text_block(d, (90, y + 16), "Люди, места, организации — и связи между ними",
                   font("black", 50), INK, 700, line_h=58)
    y = text_block(
        d, (90, y + 16),
        "Разные написания одной фамилии сводятся автоматически. По схеме видно, "
        "кто с кем встречается в делах и через какие документы.",
        font("reg", 24), INK_MUTED, 690, line_h=36,
    )
    cx = 90
    for t, tone in [("Люди", "navy"), ("Организации", "light"), ("Места", "light"),
                    ("Даты", "light"), ("Выгрузка в таблицу", "green")]:
        cx = chip(d, (cx, y + 32), t, tone)
    d.rounded_rectangle([90, y + 116, 93, y + 208], radius=2, fill=ORANGE)
    text_block(
        d, (112, y + 118),
        "«МЕНДЕШЕВ» и «МЕН ЕШЕВ» собираются в одну карточку — при этом написание "
        "из самого документа сохраняется.",
        font("reg", 22), INK_MUTED, 620, line_h=32,
    )
    return im


def sc_agent():
    im = backdrop()
    browser_frame(im, dr(im), (AGENT["x"], AGENT["y"], AGENT["w"], AGENT["h"]), "archivai.local/agent")
    d = dr(im)
    y = kicker(d, (90, 176), "Шаг 6 · Настройка")
    y = text_block(d, (90, y + 16), "Настройка системы — обычными словами", font("black", 50), INK, 780, line_h=58)
    y = text_block(
        d, (90, y + 16),
        "Не нужно звать программиста. Напишите обычной фразой, как система должна "
        "работать, — она перенастроится и покажет, что именно изменилось.",
        font("reg", 24), INK_MUTED, 760, line_h=36,
    )
    y += 26
    for p in ["Ищи больше по смыслу, чем по отдельным словам",
              "Покажи, как менялось число приказов по годам",
              "Добавь вид документа «протокол» и перепроверь дела",
              "Объедини одинаковые фамилии"]:
        f = font("med", 22)
        tw = d.textlength(p, font=f)
        d.rounded_rectangle([90, y, 90 + tw + 44, y + 56], radius=14, fill=NAVY)
        d.rectangle([90, y, 98, y + 8], fill=NAVY)
        d.text((112, y + 15), p, font=f, fill=WHITE)
        y += 68
    cx = 90
    for dchip in ["Поиск: больше по смыслу", "Показывать 10 дел вместо 5", "Добавлен вид: протокол"]:
        cx = chip(d, (cx, y + 14), dchip, "green")
    caption(im, dr(im),
            "Каждое изменение видно в списке настроек и возвращается обратно одной кнопкой",
            GREEN, bottom=40)
    return im


def sc_control(url):
    im = backdrop()
    browser_frame(im, dr(im), (CTRL["x"], CTRL["y"], CTRL["w"], CTRL["h"]), url)
    d = dr(im)
    y = kicker(d, (90, 216), "Контроль")
    y = text_block(d, (90, y + 16), "Одна сводка — и полный журнал действий", font("black", 50), INK, 760, line_h=58)
    y = text_block(
        d, (90, y + 16),
        "Все цифры считаются одинаково, поэтому сводка на экране и выгруженный "
        "отчёт всегда сходятся между собой.",
        font("reg", 23), INK_MUTED, 700, line_h=34,
    )
    y += 26
    for i, (v, lab) in enumerate([(7, "Документов обработано"), (19, "Имён, мест и дат найдено"),
                                  (11, "Людей определено"), (70, "Обращений к документам")]):
        kpi(im, dr(im), (90 + (i % 2) * 336, y + (i // 2) * 166), v, lab)
    d = dr(im)
    y2 = y + 356
    d.rounded_rectangle([90, y2, 93, y2 + 62], radius=2, fill=ORANGE)
    text_block(d, (112, y2), "Кто искал, что открывал, кто входил — включая неудачные попытки входа.",
               font("reg", 22), INK_MUTED, 640, line_h=32)
    return im


def sc_why():
    im = backdrop(dark=True)
    d = dr(im)
    y = kicker(d, (96, 180), "Почему ArchivAI")
    y = text_block(d, (96, y + 16), "Архив остаётся вашим — целиком", font("black", 56), WHITE, 1300, line_h=66)
    y += 44
    tiles = [
        ("Без подписок и лицензий", "Открытый код: не нужно платить за каждое рабочее место и продлевать доступ."),
        ("Работает на вашем сервере", "Документы не покидают учреждение, для работы не нужен интернет."),
        ("Русский и казахский", "Печатный и рукописный текст XX века, в том числе смешанные документы."),
        ("Меняется без программиста", "Настройки задаются обычными фразами, порядок обработки можно перестроить."),
    ]
    tw_, th = 730, 178
    with translucent(im) as dl:
        for i in range(len(tiles)):
            tx = 96 + (i % 2) * (tw_ + 22)
            ty = y + (i // 2) * (th + 22)
            dl.rounded_rectangle([tx, ty, tx + tw_, ty + th], radius=18,
                                 fill=(255, 255, 255, 14), outline=(255, 255, 255, 30), width=1)
    d = dr(im)
    for i, (t, note) in enumerate(tiles):
        tx = 96 + (i % 2) * (tw_ + 22)
        ty = y + (i // 2) * (th + 22)
        d.ellipse([tx + 32, ty + 40, tx + 44, ty + 52], fill=ORANGE)
        d.text((tx + 60, ty + 28), t, font=font("black", 30), fill=WHITE)
        text_block(d, (tx + 32, ty + 86), note, font("reg", 22), over(WHITE, 0.66), tw_ - 64, line_h=32)
    return im


def sc_outro():
    im = backdrop(dark=True)
    d = dr(im)
    f = font("black", 118)
    total = d.textlength("ArchivAI", font=f)
    x = (W - total) / 2
    wordmark(d, (x, 300), 118, dark=True, tagline=False)
    tag = "open-source archive intelligence"
    ft = font("med", 24)
    d.text(((W - d.textlength(tag, font=ft)) / 2, 452), tag, font=ft, fill=over(WHITE, 0.58))
    d.rounded_rectangle([W / 2 - 150, 528, W / 2 + 150, 530], radius=1, fill=ORANGE)
    for i, line in enumerate(["Ставится на ваш сервер. Открытый код.",
                              "Готовы показать на ваших документах."]):
        fl = font("med", 29)
        d.text(((W - d.textlength(line, font=fl)) / 2, 578 + i * 46), line, font=fl, fill=over(WHITE, 0.78))
    lab = "Р А З Р А Б О Т А Н О"
    fl = font("bold", 17)
    d.text(((W - d.textlength(lab, font=fl)) / 2, 790), lab, font=fl, fill=over(WHITE, 0.42))
    logo = Image.open(PUBLIC / "logo/ji_studio_light.png").convert("RGBA")
    lh = 52
    logo = logo.resize((int(logo.width * lh / logo.height), lh), Image.LANCZOS)
    im.alpha_composite(logo, (int((W - logo.width) / 2), 830))
    return im


# ══════════════════════════════════════════════════════════════════════════════
#  МОНТАЖНЫЙ ЛИСТ (тайминги совпадают с src/timeline.ts)
# ══════════════════════════════════════════════════════════════════════════════
def build_plan():
    add(name="intro", seconds=8, overlay=sc_intro())
    add(name="problem", seconds=10, overlay=sc_problem())
    add(name="how", seconds=9, overlay=sc_how())

    add(name="upload_clip", seconds=6.0, overlay=sc_upload(), media="clips/02_upload.mp4", rect=SPLIT)
    add(name="upload_still", seconds=8.0, overlay=sc_upload(), media="shots/upload_ready.png",
        rect=SPLIT, zoom=(1.02, 1.10), focus=(0.5, 0.6))

    add(name="process_a", seconds=6.3, overlay=sc_process(False), media="shots/doc_processing.png",
        rect=SPLIT_R, zoom=(1.02, 1.07), focus=(0.62, 0.35))
    add(name="process_b", seconds=6.7, overlay=sc_process(True), media="shots/doc_done.png",
        rect=SPLIT_R, zoom=(1.02, 1.08), focus=(0.66, 0.34))

    add(name="verify_a", seconds=4.85,
        overlay=sc_verify("Скан, короткое описание и выписанные имена — на одном экране", ORANGE),
        media="clips/06_verify.mp4", rect=HERO)
    add(name="verify_b", seconds=5.15,
        overlay=sc_verify("Фамилия распознана с ошибкой — архивист правит её прямо в карточке", BLUE),
        media="clips/05_doc_detail.mp4", rect=HERO)
    add(name="verify_c", seconds=5.0,
        overlay=sc_verify("Отметка «Проверено» — дело прошло через специалиста; правки видны в журнале", GREEN),
        media="clips/05_doc_detail.mp4", rect=HERO, extra={"seek": 5.15})

    add(name="search_type", seconds=5.3,
        overlay=sc_search("«документы с упоминанием москвы» — обычная фраза, а не поисковый код", ORANGE),
        media="clips/04a_search_type.mp4", rect=HERO)
    add(name="search_results", seconds=8.3,
        overlay=sc_search("Ищет и по смыслу, и по словам — на русском, казахском и английском", BLUE),
        media="clips/04b_search_results.mp4", rect=HERO)
    add(name="search_score", seconds=4.4,
        overlay=sc_search("Рядом с каждым делом — насколько оно подходит под запрос", GREEN),
        media="shots/search_results.png", rect=HERO, zoom=(1.12, 1.34), focus=(0.44, 0.14))

    # Сцена «Вопрос архиву» в монтаж не входит: в записи ответ ассистента
    # построен на шумном распознавании и в кадре читается плохо.
    # Функция sc_ask() и клипы 07/08 оставлены — вернуть можно одной строкой.

    add(name="entities", seconds=13, overlay=sc_entities(), media="shots/entity_graph_crop.png",
        rect=ENT, zoom=(1.02, 1.12), focus=(0.5, 0.5))
    add(name="agent", seconds=16, overlay=sc_agent(), media="shots/agent.png",
        rect=AGENT, zoom=(1.0, 1.09), focus=(0.5, 0.22))

    add(name="control_a", seconds=6.7, overlay=sc_control("archivai.local/dashboard"),
        media="shots/dashboard_crop.png", rect=CTRL, zoom=(1.0, 1.06), focus=(0.5, 0.3))
    add(name="control_b", seconds=5.3, overlay=sc_control("archivai.local/usage"),
        media="shots/usage.png", rect=CTRL, zoom=(1.02, 1.09), focus=(0.5, 0.3))

    add(name="why", seconds=11, overlay=sc_why(), dark=True)
    add(name="outro", seconds=8, overlay=sc_outro(), dark=True)


# ══════════════════════════════════════════════════════════════════════════════
#  РЕНДЕР
# ══════════════════════════════════════════════════════════════════════════════
def run(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(" ".join(str(c) for c in cmd[:12]), "...", file=sys.stderr)
        print(res.stderr[-2500:], file=sys.stderr)
        raise SystemExit(f"ffmpeg упал на: {cmd[-1]}")


def prep_still(path: Path, rect: dict, focus) -> Path:
    """Кадрирует скриншот под окно рамки и увеличивает для запаса на зуме."""
    im = Image.open(path).convert("RGB")
    target_ar = rect["w"] / rect["h"]
    src_ar = im.width / im.height
    if src_ar > target_ar:  # шире — режем по бокам
        nw = int(im.height * target_ar)
        cx = int(im.width * focus[0])
        x0 = max(0, min(im.width - nw, cx - nw // 2))
        im = im.crop((x0, 0, x0 + nw, im.height))
    else:                   # выше — режем сверху/снизу
        nh = int(im.width / target_ar)
        cy = int(im.height * focus[1])
        y0 = max(0, min(im.height - nh, cy - nh // 2))
        im = im.crop((0, y0, im.width, y0 + nh))
    im = im.resize((rect["w"] * 2, rect["h"] * 2), Image.LANCZOS)
    out = WORK / f"still_{path.stem}_{rect['w']}x{rect['h']}_{int(focus[0]*100)}_{int(focus[1]*100)}.png"
    im.save(out)
    return out


def fade_chain(seg: Segment, dur: float) -> str:
    """
    Растворение только на стыках сцен и обязательно в цвет соседней сцены,
    а не в чёрный — иначе на каждом стыке моргает тёмный кадр.
    Подрезки внутри одной сцены склеиваются встык: подписи и заголовок
    остаются на месте, меняется только картинка в рамке.
    """
    parts = []
    if seg.fade_in:
        parts.append(f"fade=t=in:st=0:d=0.34:color={seg.fade_in}")
    if seg.fade_out:
        parts.append(f"fade=t=out:st={max(0.0, dur - 0.34):.2f}:d=0.34:color={seg.fade_out}")
    return ("," + ",".join(parts)) if parts else ""


def render_segment(seg: Segment, idx: int) -> Path:
    dur = seg.seconds
    frames = max(2, int(round(dur * FPS)))
    ov = WORK / f"ov_{idx:02d}.png"
    seg.overlay.save(ov)
    out = WORK / f"seg_{idx:02d}.mp4"
    fades = fade_chain(seg, dur)

    if seg.media is None:
        cmd = [
            "ffmpeg", "-v", "error", "-y",
            "-loop", "1", "-t", f"{dur}", "-i", str(ov),
            "-filter_complex",
            f"[0:v]scale={W}:{H},fps={FPS},format=yuv420p{fades}[v]",
            "-map", "[v]", "-c:v", "libx264", "-crf", "19", "-preset", "medium",
            "-pix_fmt", "yuv420p", str(out),
        ]
        run(cmd)
        return out

    rect = seg.rect or SPLIT
    media = PUBLIC / seg.media
    bgc = "0x111B31" if seg.dark else "0xF2F5F9"

    if seg.media.endswith(".mp4"):
        media_filter = f"[1:v]scale={rect['w']}:{rect['h']},setsar=1,fps={FPS}[m]"
        seek = seg.extra.get("seek")
        inputs = (["-ss", f"{seek}"] if seek else []) + ["-i", str(media)]
    else:
        still = prep_still(media, rect, seg.focus)
        z0, z1 = seg.zoom
        step = (z1 - z0) / frames
        media_filter = (
            f"[1:v]scale={rect['w']*2}:{rect['h']*2},"
            f"zoompan=z='min({z0}+on*{step:.6f},{z1})':d={frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={rect['w']}x{rect['h']}:fps={FPS},"
            f"setsar=1[m]"
        )
        inputs = ["-loop", "1", "-t", f"{dur}", "-i", str(still)]

    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-t", f"{dur}", "-i", f"color=c={bgc}:s={W}x{H}:r={FPS}",
        *inputs,
        "-loop", "1", "-t", f"{dur}", "-i", str(ov),
        "-filter_complex",
        f"{media_filter};"
        f"[0:v][m]overlay={rect['x']}:{rect['y']}:shortest=1[base];"
        f"[2:v]scale={W}:{H}[ovr];"
        f"[base][ovr]overlay=0:0,format=yuv420p{fades}[v]",
        "-map", "[v]", "-t", f"{dur}",
        "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
        str(out),
    ]
    run(cmd)
    return out


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Сборка превью-ролика ArchivAI")
    ap.add_argument("--from", dest="start", type=int, default=0, help="с какого сегмента начать")
    ap.add_argument("--to", dest="end", type=int, default=None, help="на каком закончить (не включая)")
    ap.add_argument("--concat-only", action="store_true", help="только склеить уже отрендеренное")
    ap.add_argument("--clean", action="store_true", help="удалить промежуточные файлы после склейки")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    build_plan()

    # Расставляем растворения: только на границах сцен и в цвет соседней сцены.
    BGC, NAVYC = "0xF2F5F9", "0x111B31"
    for i, seg in enumerate(SEGMENTS):
        prev = SEGMENTS[i - 1] if i else None
        nxt = SEGMENTS[i + 1] if i + 1 < len(SEGMENTS) else None
        if prev is None:
            seg.fade_in = BGC
        elif prev.scene != seg.scene:
            seg.fade_in = NAVYC if prev.dark else BGC
        if nxt is None:
            seg.fade_out = "black"          # финальное затемнение
        elif nxt.scene != seg.scene:
            seg.fade_out = NAVYC if nxt.dark else BGC

    total = sum(s.seconds for s in SEGMENTS)
    scenes = len({s.scene for s in SEGMENTS})
    print(f"Сцен: {scenes}   Сегментов: {len(SEGMENTS)}   "
          f"Хронометраж: {total:.1f} с  ({int(total // 60)}:{int(total % 60):02d})")

    if not args.concat_only:
        end = args.end if args.end is not None else len(SEGMENTS)
        for i in range(args.start, min(end, len(SEGMENTS))):
            seg = SEGMENTS[i]
            print(f"  [{i + 1:2d}/{len(SEGMENTS)}] {seg.name:<16} {seg.seconds:5.2f} с", flush=True)
            render_segment(seg, i)

    parts = [WORK / f"seg_{i:02d}.mp4" for i in range(len(SEGMENTS))]
    missing = [p.name for p in parts if not p.exists()]
    if missing:
        print(f"Ещё не отрендерено: {', '.join(missing)}")
        return

    # Прерванный рендер оставляет файл без moov-атома: склейка молча
    # обрежет ролик на этом месте. Поэтому проверяем каждый сегмент.
    broken = []
    for i, (p, seg) in enumerate(zip(parts, SEGMENTS)):
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
            capture_output=True, text=True,
        )
        got = probe.stdout.strip()
        if probe.returncode != 0 or not got or abs(float(got) - seg.seconds) > 0.2:
            broken.append(f"{p.name} ({seg.name})")
    if broken:
        print("Битые или недорендеренные сегменты — перезапустите их:")
        for b in broken:
            print(f"    {b}")
        print(f"    python3 preview/build_preview.py --from N --to N+1")
        return

    listfile = WORK / "concat.txt"
    listfile.write_text("".join(f"file '{p}'\n" for p in parts))
    final = OUT / "archivai-preview.mp4"
    # Все сегменты закодированы одинаково, поэтому склейка идёт без перекодирования.
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
         "-c", "copy", "-movflags", "+faststart", str(final)])
    print(f"\nГотово: {final}")
    if args.clean:
        shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
