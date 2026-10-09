# -*- coding: utf-8 -*-
"""
Извлечение текста из файлов разных форматов.

Реальные материалы дела почти никогда не бывают текстовыми файлами: это
docx, pdf и сканы. Модуль превращает загруженный файл в текст, с которым
дальше работает всё остальное.

Порядок предпочтений для каждого формата — от самого надёжного способа к
запасному. Встроенные разборщики (docx, rtf, простой pdf) написаны на
стандартной библиотеке и работают без интернета и без установки пакетов;
внешние инструменты используются, только если они уже есть в системе.

Что поддерживается:
    .txt, .md          — напрямую
    .docx              — встроенный разбор (zip + XML), надёжно
    .rtf               — встроенный разбор управляющих последовательностей
    .pdf               — pypdf / pdfminer / pdftotext, иначе встроенный
                         разборщик для несложных PDF
    .doc               — textutil (macOS)
    изображения        — tesseract, если установлен
"""
import io
import os
import re
import shutil
import subprocess
import zipfile

TEXT_EXT = {".txt", ".md", ".text", ".csv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

INSTALL_HINT = ("Для разбора этого файла установите один из пакетов:\n"
                "    pip3 install pypdf\n"
                "или сохраните документ как .docx либо .txt.")


class DocumentError(Exception):
    pass


# ---------------------------------------------------------------------------
# Текст
# ---------------------------------------------------------------------------
def _decode(data):
    for encoding in ("utf-8", "utf-8-sig", "cp1251", "koi8-r"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# DOCX — zip-архив с XML внутри, разбирается стандартной библиотекой
# ---------------------------------------------------------------------------
def _from_docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [n for n in ("word/document.xml", "word/document2.xml")
                 if n in archive.namelist()]
        if not names:
            raise DocumentError("В файле .docx не найден основной документ.")
        xml = archive.read(names[0]).decode("utf-8", "replace")

    # переносы строк и абзацы должны сохраниться: на них опирается разбор
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"</w:p>", "\n\n", xml)
    xml = re.sub(r"</w:tr>", "\n", xml)
    xml = re.sub(r"</w:tc>", "\t", xml)

    parts = re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>|(\n+|\t)", xml, re.S)
    out = []
    for text, separator in parts:
        out.append(separator if separator else text)
    text = "".join(out)

    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&quot;", '"'), ("&apos;", "'"), ("&#10;", "\n")):
        text = text.replace(entity, char)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# RTF — снимаем управляющие последовательности
# ---------------------------------------------------------------------------
def _from_rtf(data):
    text = _decode(data)
    text = re.sub(r"\\'([0-9a-fA-F]{2})",
                  lambda m: bytes([int(m.group(1), 16)]).decode("cp1251", "replace"),
                  text)
    text = re.sub(r"\\u(-?\d+)\s?\??",
                  lambda m: chr(int(m.group(1)) % 65536), text)
    text = re.sub(r"\\par[d]?\b", "\n", text)
    text = re.sub(r"\{\\\*.*?\}", "", text, flags=re.S)
    text = re.sub(r"\\[a-zA-Z]+-?\d*\s?", "", text)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _pdf_via_library(data):
    """pypdf или pdfminer, если они установлены."""
    try:
        import pypdf                                    # noqa: PLC0415
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages), "pypdf"
    except ImportError:
        pass
    except Exception:                                    # noqa: BLE001
        pass
    try:
        from pdfminer.high_level import extract_text     # noqa: PLC0415
        return extract_text(io.BytesIO(data)), "pdfminer"
    except ImportError:
        pass
    except Exception:                                    # noqa: BLE001
        pass
    return None, None


def _pdf_via_binary(data, tmp_path):
    """Внешняя утилита pdftotext, если она есть в системе."""
    if not shutil.which("pdftotext"):
        return None, None
    with open(tmp_path, "wb") as fh:
        fh.write(data)
    try:
        result = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8",
                                 tmp_path, "-"],
                                capture_output=True, timeout=60)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.decode("utf-8", "replace"), "pdftotext"
    except (subprocess.SubprocessError, OSError):
        pass
    return None, None


def _parse_tounicode(cmap_text):
    """Таблица соответствия кодов символов юникоду из ToUnicode CMap.

    Без неё кириллица в PDF читается как набор кодов: шрифты почти всегда
    подключаются с собственной кодировкой, а не с WinAnsi.
    """
    mapping = {}
    for block in re.findall(r"beginbfchar(.*?)endbfchar", cmap_text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            try:
                mapping[int(src, 16)] = "".join(
                    chr(int(dst[i:i + 4], 16)) for i in range(0, len(dst), 4))
            except ValueError:
                continue
    for block in re.findall(r"beginbfrange(.*?)endbfrange", cmap_text, re.S):
        for lo, hi, dst in re.findall(
                r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            try:
                start, end, base = int(lo, 16), int(hi, 16), int(dst, 16)
            except ValueError:
                continue
            for offset in range(min(end - start + 1, 65536)):
                mapping[start + offset] = chr(base + offset)
    return mapping


def _pdf_builtin(data):
    """Запасной разборщик PDF на стандартной библиотеке.

    Справляется с текстовыми PDF: распаковывает потоки, читает операторы
    показа текста и, если есть, применяет ToUnicode. Со сканами и сложной
    вёрсткой не работает — для них нужен OCR.
    """
    import zlib                                          # noqa: PLC0415

    streams = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = match.group(1)
        try:
            streams.append(zlib.decompress(raw).decode("latin-1"))
        except zlib.error:
            streams.append(raw.decode("latin-1", "replace"))

    tounicode = {}
    for chunk in streams:
        if "beginbfchar" in chunk or "beginbfrange" in chunk:
            tounicode.update(_parse_tounicode(chunk))

    pieces = []
    for chunk in streams:
        if "Tj" not in chunk and "TJ" not in chunk:
            continue
        for match in re.finditer(r"\((?:[^()\\]|\\.)*\)|<[0-9A-Fa-f\s]+>", chunk):
            token = match.group(0)
            if token.startswith("<"):
                hex_digits = re.sub(r"\s", "", token[1:-1])
                codes = [int(hex_digits[i:i + 4], 16)
                         for i in range(0, len(hex_digits) - 1, 4)]
                pieces.append("".join(tounicode.get(c, "") for c in codes))
            else:
                body = token[1:-1]
                body = re.sub(r"\\([()\\])", r"\1", body)
                if tounicode:
                    pieces.append("".join(
                        tounicode.get(ord(ch), ch) for ch in body))
                else:
                    pieces.append(body.encode("latin-1", "replace")
                                  .decode("cp1251", "replace"))
        pieces.append("\n")

    text = re.sub(r"[ \t]{2,}", " ", "".join(pieces))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _from_pdf(data, tmp_dir):
    text, method = _pdf_via_library(data)
    if text and text.strip():
        return text, method, None

    text, method = _pdf_via_binary(data, os.path.join(tmp_dir, "_in.pdf"))
    if text and text.strip():
        return text, method, None

    text = _pdf_builtin(data)
    letters = sum(1 for ch in text if ch.isalpha())
    if letters >= 40:
        return text, "встроенный разборщик PDF", (
            "PDF разобран встроенным разборщиком без внешних библиотек — "
            "часть форматирования могла потеряться. Проверьте распознанные "
            "данные ниже.")
    raise DocumentError(
        "Не удалось извлечь текст из PDF. Похоже, это скан (изображение) "
        "или файл со сложной вёрсткой.\n" + INSTALL_HINT)


# ---------------------------------------------------------------------------
# Прочие форматы через системные утилиты
# ---------------------------------------------------------------------------
def _from_doc(data, tmp_dir):
    if not shutil.which("textutil"):
        raise DocumentError(
            "Формат .doc (старый Word) требует утилиты textutil, доступной "
            "в macOS. Пересохраните документ в .docx или .txt.")
    path = os.path.join(tmp_dir, "_in.doc")
    with open(path, "wb") as fh:
        fh.write(data)
    result = subprocess.run(["textutil", "-convert", "txt", "-stdout", path],
                            capture_output=True, timeout=60)
    if result.returncode != 0:
        raise DocumentError("Не удалось прочитать файл .doc.")
    return result.stdout.decode("utf-8", "replace"), "textutil"


def _from_image(data, tmp_dir):
    if not shutil.which("tesseract"):
        raise DocumentError(
            "Распознавание текста на изображении требует tesseract "
            "(brew install tesseract tesseract-lang). Либо приложите "
            "документ в текстовом виде.")
    path = os.path.join(tmp_dir, "_in.img")
    with open(path, "wb") as fh:
        fh.write(data)
    result = subprocess.run(["tesseract", path, "-", "-l", "rus+kaz+eng"],
                            capture_output=True, timeout=180)
    if result.returncode != 0:
        raise DocumentError("Не удалось распознать текст на изображении.")
    return result.stdout.decode("utf-8", "replace"), "tesseract (OCR)"


# ---------------------------------------------------------------------------
def extract_text(filename, data, tmp_dir="/tmp"):
    """Возвращает (текст, способ_извлечения, предупреждение)."""
    ext = os.path.splitext(filename or "")[1].lower()

    if ext in TEXT_EXT or not ext:
        return _decode(data), "текстовый файл", None
    if ext == ".docx":
        return _from_docx(data), "встроенный разбор docx", None
    if ext == ".rtf":
        return _from_rtf(data), "встроенный разбор rtf", None
    if ext == ".pdf":
        return _from_pdf(data, tmp_dir)
    if ext == ".doc":
        text, method = _from_doc(data, tmp_dir)
        return text, method, None
    if ext in IMAGE_EXT:
        text, method = _from_image(data, tmp_dir)
        return text, method, (
            "Текст получен распознаванием изображения — возможны ошибки "
            "в цифрах и датах. Проверьте распознанные данные.")

    # Неизвестное расширение: читаем как текст, только если это
    # действительно текст. Проверяем не только наличие букв, но и долю
    # печатных символов — иначе двоичный файл «распознаётся» как текст
    # из мусора, который дало декодирование с заменой.
    text = _decode(data)
    sample = text[:4000]
    printable = sum(1 for ch in sample
                    if ch.isprintable() or ch in "\n\r\t")
    letters = sum(1 for ch in sample if ch.isalpha())
    if sample and letters > 50 and printable / len(sample) > 0.92:
        return text, "текстовый файл", (
            "Формат «%s» не поддерживается напрямую, файл прочитан как "
            "текст." % ext)
    raise DocumentError(
        "Формат «%s» не поддерживается. Приложите документ в форматах "
        "txt, docx, rtf или pdf." % (ext or "без расширения"))


SUPPORTED_HINT = ("Поддерживаются: txt, docx, rtf, pdf. "
                  "Форматы doc и сканы — при наличии системных утилит.")
