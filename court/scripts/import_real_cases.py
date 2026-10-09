# -*- coding: utf-8 -*-
"""
Импорт реальных размеченных дел в обучающий набор.

Принимает CSV или JSON с делами, размеченными по схеме core/schema.py,
проверяет их и дописывает в data/cases.csv. После импорта достаточно
запустить scripts/train_model.py — отдельного кода для реальных данных
не требуется.

Реальные записи отличаются от синтетических пустым полем true_probability
и колонкой source=real, поэтому их всегда можно отделить и посчитать
метрики отдельно.

Запуск:
    python3 scripts/import_real_cases.py путь/к/файлу.csv
    python3 scripts/import_real_cases.py путь/к/файлу.json --dry-run

Формат JSON — список объектов, CSV — с заголовком. Названия колонок
должны совпадать с именами признаков из core/schema.py.
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.schema import (BINARY_FEATURES, CATEGORIES, FEATURE_BY_NAME,  # noqa: E402
                         FEATURE_NAMES, INSTANCES, PARTY_TYPES)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_CSV = os.path.join(ROOT, "data", "cases.csv")

ALLOWED_VALUES = {
    "dispute_category": set(CATEGORIES),
    "claimant_type": set(PARTY_TYPES),
    "respondent_type": set(PARTY_TYPES),
    "court_instance": set(INSTANCES),
}

RANGES = {
    "claim_amount_kzt": (1_000, 100_000_000_000),
    "months_since_breach": (0, 600),
    "witness_count": (0, 50),
    "evidence_count": (0, 500),
    "doc_completeness": (0.0, 1.0),
    "satisfied_share": (0.0, 1.0),
}


def validate(row, index):
    """Возвращает список ошибок. Пустой список — запись корректна."""
    errors = []

    for name in FEATURE_NAMES:
        if name not in row or row[name] in ("", None):
            errors.append("строка %d: отсутствует признак «%s» (%s)"
                          % (index, name, FEATURE_BY_NAME[name]["label"]))

    for name, allowed in ALLOWED_VALUES.items():
        value = row.get(name)
        if value not in (None, "") and value not in allowed:
            errors.append("строка %d: недопустимое значение «%s» = %r; "
                          "ожидается одно из: %s"
                          % (index, name, value, ", ".join(sorted(allowed))))

    for name in BINARY_FEATURES:
        value = row.get(name)
        if value not in (None, "") and str(value) not in ("0", "1"):
            errors.append("строка %d: признак «%s» должен быть 0 или 1, "
                          "получено %r" % (index, name, value))

    for name, (lo, hi) in RANGES.items():
        if row.get(name) in (None, ""):
            continue
        try:
            value = float(row[name])
        except (TypeError, ValueError):
            errors.append("строка %d: «%s» не число (%r)" % (index, name, row[name]))
            continue
        if not lo <= value <= hi:
            errors.append("строка %d: «%s» = %s вне допустимого диапазона %s–%s"
                          % (index, name, value, lo, hi))

    outcome = str(row.get("outcome_win", ""))
    if outcome not in ("0", "1"):
        errors.append("строка %d: outcome_win должен быть 0 или 1, получено %r"
                      % (index, row.get("outcome_win")))

    # согласованность исхода и доли удовлетворённых требований
    share = row.get("satisfied_share")
    if outcome == "0" and share not in (None, "") and float(share) > 0:
        errors.append("строка %d: иск отклонён, но satisfied_share = %s"
                      % (index, share))
    if outcome == "1" and share not in (None, "") and float(share) == 0:
        errors.append("строка %d: иск удовлетворён, но satisfied_share = 0"
                      % index)

    return errors


def load_rows(path):
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else data.get("cases", [])
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def normalize(row, index):
    share = row.get("satisfied_share")
    share = float(share) if share not in (None, "") else (
        1.0 if str(row.get("outcome_win")) == "1" else 0.0)
    if share >= 0.95:
        label = "satisfied_full"
    elif share > 0:
        label = "satisfied_partial"
    else:
        label = "denied"
    out = {"case_id": row.get("case_id") or "REAL-%05d" % index}
    for name in FEATURE_NAMES:
        out[name] = row.get(name)
    out["outcome_win"] = int(row["outcome_win"])
    out["satisfied_share"] = round(share, 3)
    out["outcome_label"] = row.get("outcome_label") or label
    out["true_probability"] = ""      # у реальных дел её не существует
    out["source"] = "real"
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="CSV или JSON с размеченными делами")
    parser.add_argument("--dry-run", action="store_true",
                        help="только проверить, ничего не записывать")
    args = parser.parse_args()

    rows = load_rows(args.path)
    if not rows:
        print("Файл пуст или не содержит дел.")
        return 1

    errors, valid = [], []
    for i, row in enumerate(rows, 1):
        row_errors = validate(row, i)
        if row_errors:
            errors.extend(row_errors)
        else:
            valid.append(normalize(row, i))

    print("Прочитано дел: %d" % len(rows))
    print("Корректных:    %d" % len(valid))
    print("С ошибками:    %d" % (len(rows) - len(valid)))
    if errors:
        print("\nОшибки (первые 20):")
        for e in errors[:20]:
            print("  " + e)
        if len(errors) > 20:
            print("  … ещё %d" % (len(errors) - 20))

    if args.dry_run:
        print("\nРежим проверки: файл не изменён.")
        return 0 if not errors else 1
    if not valid:
        print("\nНечего импортировать.")
        return 1

    with open(TARGET_CSV, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        existing = list(reader)
        columns = list(reader.fieldnames or [])
    if "source" not in columns:
        columns.append("source")
        for row in existing:
            row.setdefault("source", "synthetic")

    with open(TARGET_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in existing:
            row.setdefault("source", "synthetic")
            writer.writerow({c: row.get(c, "") for c in columns})
        for row in valid:
            writer.writerow({c: row.get(c, "") for c in columns})

    total_real = sum(1 for r in existing if r.get("source") == "real") + len(valid)
    print("\nДобавлено в %s: %d дел." % (os.path.relpath(TARGET_CSV, ROOT), len(valid)))
    print("Всего реальных дел в наборе: %d из %d."
          % (total_real, len(existing) + len(valid)))
    print("\nДалее: python3 scripts/train_model.py")
    if total_real < 300:
        print("\nПредупреждение: реальных дел пока мало. До нескольких сотен "
              "записей модель остаётся демонстрационной, и формулировки "
              "дисклеймеров менять нельзя.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
