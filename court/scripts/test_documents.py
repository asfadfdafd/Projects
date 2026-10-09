# -*- coding: utf-8 -*-
"""
Проверка разбора форматов документов.

Тестовые файлы собираются здесь же, из текста демо-дела: так проверяется,
что загруженный docx, rtf или pdf даёт тот же текст, что и исходный txt,
и что дальше по конвейеру признаки извлекаются одинаково.

Отдельно проверяется встроенный разборщик PDF — он работает без внешних
библиотек и нужен там, где их нельзя установить.

Запуск:  python3 scripts/test_documents.py
"""
import io
import os
import sys
import zipfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.documents import (DocumentError, _parse_tounicode,  # noqa: E402
                            _pdf_builtin, extract_text)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "demo_cases", "case_03_trud", "01_iskovoe_zayavlenie.txt")

FAILURES = []


def check(condition, message, extra=""):
    print(("  ok   " if condition else "  FAIL ") + message + (
        ("  — " + extra) if extra else ""))
    if not condition:
        FAILURES.append(message)


# ---------------------------------------------------------------------------
def build_docx(text):
    paragraphs = "".join(
        '<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>'
        % line.replace("&", "&amp;").replace("<", "&lt;")
        for line in text.split("\n"))
    document = ('<?xml version="1.0" encoding="UTF-8"?><w:document '
                'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
                '2006/main"><w:body>%s</w:body></w:document>' % paragraphs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def build_rtf(text):
    body = r"\par ".join(text.split("\n"))
    return (r"{\rtf1\ansi\ansicpg1251 " + body + "}").encode("cp1251", "replace")


def build_pdf(lines):
    """PDF с кириллицей так, как её кодируют настоящие генераторы:
    шестнадцатеричные строки плюс таблица ToUnicode."""
    used = sorted({ch for line in lines for ch in line})
    codes = {ch: i + 1 for i, ch in enumerate(used)}

    content = "BT /F1 11 Tf 40 800 Td 14 TL\n"
    for line in lines:
        content += "<%s> Tj T*\n" % "".join("%04X" % codes[ch] for ch in line)
    content += "ET"
    stream = zlib.compress(content.encode("latin-1"))

    cmap = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            "1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
            "%d beginbfchar\n%s\nendbfchar\nendcmap end end"
            % (len(codes), "\n".join("<%04X> <%04X>" % (code, ord(ch))
                                     for ch, code in codes.items())))
    cmap_stream = zlib.compress(cmap.encode("latin-1"))

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream)
        + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /NotoSans /Encoding "
        b"/Identity-H /DescendantFonts [] /ToUnicode 6 0 R >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(cmap_stream)
        + cmap_stream + b"\nendstream",
    ]

    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, xref_at))
    return out


# ---------------------------------------------------------------------------
def main():
    with open(SOURCE, encoding="utf-8") as fh:
        source = fh.read()
    lines = [line for line in source.split("\n") if line.strip()][:18]
    markers = ("Мукашев", "2 340 000", "Оңтүстік")

    print("\n[1] DOCX")
    text, method, _ = extract_text("иск.docx", build_docx(source))
    check(all(m in text for m in markers), "текст, суммы и казахские буквы на месте",
          "%s, %d знаков" % (method, len(text)))
    check("\n" in text, "структура абзацев сохранена")

    print("\n[2] RTF")
    text, method, _ = extract_text("иск.rtf", build_rtf(source))
    check("Мукашев" in text and "2 340 000" in text,
          "текст и суммы на месте", "%s, %d знаков" % (method, len(text)))

    print("\n[3] PDF с кириллицей")
    pdf = build_pdf(lines)
    text, method, warning = extract_text("иск.pdf", pdf)
    check("Мукашев" in text, "кириллица распознана", "%s" % method)
    check("2 340 000" in text or "2 340 000" in text.replace(" ", " "),
          "сумма требований распознана")

    print("\n[4] Встроенный разборщик PDF (без внешних библиотек)")
    builtin = _pdf_builtin(pdf)
    check("Мукашев" in builtin, "кириллица распознана через ToUnicode",
          "%d знаков" % len(builtin))
    check("ИСКОВОЕ" in builtin.upper(), "заголовок документа распознан")

    print("\n[5] Таблица ToUnicode")
    mapping = _parse_tounicode(
        "beginbfchar\n<0003> <0410>\n<0004> <0411>\nendbfchar\n"
        "beginbfrange\n<0010> <0012> <0430>\nendbfrange")
    check(mapping.get(3) == "А" and mapping.get(4) == "Б", "разбор bfchar")
    check(mapping.get(0x10) == "а" and mapping.get(0x12) == "в", "разбор bfrange")

    print("\n[6] Конвейер целиком: docx даёт те же признаки, что txt")
    from core.extraction import RuleBasedExtractor
    from core.predictor import predict
    extractor = RuleBasedExtractor()

    def features_of(documents):
        result = extractor.extract(documents)
        return {k: v for k, v in result.features.items() if not k.startswith("_")}

    from_txt = features_of([{"name": "иск.txt", "text": source}])
    docx_text, _, _ = extract_text("иск.docx", build_docx(source))
    from_docx = features_of([{"name": "иск.docx", "text": docx_text}])
    differing = [k for k in from_txt
                 if k != "months_since_breach" and from_txt[k] != from_docx.get(k)]
    check(not differing, "признаки совпадают с разбором исходного txt",
          "различий нет" if not differing else "различаются: %s" % differing)
    check(predict(from_txt)["probability_pct"] == predict(from_docx)["probability_pct"],
          "оценка вероятности совпадает")

    print("\n[7] Понятные ошибки")
    try:
        extract_text("архив.zip", b"PK\x03\x04" + bytes(range(256)) * 3)
        check(False, "двоичный файл отклоняется")
    except DocumentError as exc:
        check("не поддерживается" in str(exc).lower(),
              "двоичный файл отклоняется с понятным сообщением")
    try:
        extract_text("скан.pdf", b"%PDF-1.4\n" + b"\x00" * 400)
        check(False, "нечитаемый PDF отклоняется")
    except DocumentError as exc:
        check("скан" in str(exc).lower() or "не удалось" in str(exc).lower(),
              "нечитаемый PDF отклоняется с подсказкой")

    print("\n" + "=" * 62)
    if FAILURES:
        print("Провалено проверок: %d" % len(FAILURES))
        for item in FAILURES:
            print("  FAIL " + item)
        return 1
    print("Все проверки форматов пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
